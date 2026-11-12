/*
 * The GPU of haydn: an Adreno 660 at 0x3d00000. See haydn.gpu.h for the
 * register map, the step table and what does and does not transfer from
 * HakiOS's Adreno driver.
 *
 * The three steps here all read. They answer the question the rest of the
 * sequence depends on: is the GPU block where the device tree says it is, and
 * does the fuse say which chip this is? A wrong answer at step 1 means every
 * write that follows would go somewhere else, so nothing writes until these
 * pass.
 *
 * Boot argument: adreno=N runs steps 1..N and stops.
 */

#include <pexpert/pexpert.h>
#include <machine/machine_routines.h>
#include <kern/printf.h>

#include "haydn.gpu.h"

/* XNU has no header a kext can reach for this one. */
extern void delay_for_us(uint32_t us);

/* The QFPROM fuse block the speed bin lives in: qfprom@780000. */
#define QFPROM_PHYS             0x00780000ULL
#define QFPROM_SIZE             0x7000
#define QFPROM_CORRECTED        0x4000
#define QFPROM_SPEED_BIN        0x1e9    /* the byte the vendor's driver reads as gpu speed bin */

/*
 * The GPU control registers this probe reads. The first two are the ones
 * HakiOS reads at its step 2 and 3 and are part of the a6xx family; the offset
 * of the chip id is the same on every Adreno of this generation.
 */
#define KGSL_IDENTIFY_0         0x0000
#define KGSL_IDENTIFY_1         0x0004
#define KGSL_REVISION           0x0008
#define KGSL_RBBM_STATUS        0x0021

/*
 * GPUCC: the 3D core's PLL, the two power switches, and the branches steps 4 and
 * 5 use. Every offset here is this SoC's; see haydn.gpu.h for where they come
 * from and which sibling's numbers are not transferable.
 */
#define GPUCC_PLL0_MODE         0x0000
#define GPUCC_GX_SW_RESET       0x1008
#define GPUCC_GX_GDSCR          0x100c
#define GPUCC_CXO_AON_CBCR      0x1004
#define GPUCC_CB_CBCR           0x1170
#define GPUCC_CXO_CBCR          0x109c
#define GPUCC_AHB_CBCR          0x1078
#define GPUCC_CX_GDSCR          0x106c
#define GPUCC_CX_HW_CTRL        0x1540
#define GPUCC_GX_GMU_CBCR       0x1064
#define GPUCC_CX_GMU_CBCR       0x1098
#define GPUCC_HUB_AON_CBCR      0x1178
#define GPUCC_HUB_CX_INT_CBCR   0x1204
#define GPUCC_SMMU_VOTE_CBCR    0x5000

static uint32_t
haydn_gpu_read32(vm_offset_t base, uint32_t offset)
{
	return *(volatile uint32_t *)(base + offset);
}

static void
haydn_gpu_write32(vm_offset_t base, uint32_t offset, uint32_t value)
{
	*(volatile uint32_t *)(base + offset) = value;
}

/*
 * Step 3: the GPU's own clock controller, as the loader left it. The PLL's
 * lock bit is what says the block is powered: a GPU block that is not clocked
 * reads its registers as zero even when the addresses are right.
 */
static int
haydn_gpu_step3(void)
{
	vm_offset_t gpucc;
	uint32_t pll, gx, cx;

	gpucc = ml_io_map(haydn_gpu_blocks[8].phys, haydn_gpu_blocks[8].size);
	if (gpucc == 0) {
		printf("haydn-gpu: gpucc at 0x%llx did not map\n",
		    (unsigned long long)haydn_gpu_blocks[8].phys);
		return 3;
	}

	pll = haydn_gpu_read32(gpucc, GPUCC_PLL0_MODE);
	gx = haydn_gpu_read32(gpucc, GPUCC_GX_GDSCR);
	cx = haydn_gpu_read32(gpucc, GPUCC_CX_GDSCR);

	printf("haydn-gpu: step 3 gpucc pll0 %08x (locked %d) gx_gdscr %08x cx_gdscr %08x\n",
	    pll, (pll >> 31) & 1, gx, cx);

	/*
	 * A PLL mode register of all ones or of zero means the block is not
	 * clocked: every bit of this register has a meaning, and neither extreme
	 * is one of them. That is the check, not a particular expected value.
	 */
	if (pll == 0xffffffffu || pll == 0) {
		printf("haydn-gpu: gpucc reads %08x - the block is not clocked\n", pll);
		return 3;
	}

	return 0;
}

/*
 * Step 2: the fuses. qfprom@780000 holds the speed bin, and the speed bin is
 * the only thing that says which of the five qcom,gpu-pwrlevels-* tables this
 * handset runs.
 *
 * This is where the driver decides what it is allowed to ask for. The handset
 * reports ten levels topping at 840 MHz, but bins 0, 5 and 7 all match that, so
 * the fuse is read rather than a table guessed.
 */
static int
haydn_gpu_step2(const struct haydn_gpu_bin **bin)
{
	vm_offset_t qfprom;
	uint8_t speed_bin;
	uint32_t i;

	qfprom = ml_io_map(QFPROM_PHYS, QFPROM_SIZE);
	if (qfprom == 0) {
		printf("haydn-gpu: qfprom at 0x%llx did not map\n",
		    (unsigned long long)QFPROM_PHYS);
		return 2;
	}

	speed_bin = *(volatile uint8_t *)(qfprom + QFPROM_CORRECTED + QFPROM_SPEED_BIN);

	printf("haydn-gpu: step 2 speed-bin fuse reads %u\n", speed_bin);

	for (i = 0; i < HAYDN_GPU_BINS; i++) {
		if (haydn_gpu_bins[i].speed_bin == speed_bin) {
			*bin = &haydn_gpu_bins[i];
			printf("haydn-gpu: bin %u: %u levels, top %u MHz, initial pwrlevel %u\n",
			    speed_bin, (*bin)->count,
			    (*bin)->levels[0].hz / 1000000, (*bin)->initial);
			return 0;
		}
	}

	/*
	 * A fuse value with no bin: the tree lists 0, 1, 3, 5 and 7 and this handset
	 * has one of them. Anything else means either the fuse offset is wrong or
	 * the handset is a revision this tree does not describe. Neither is safe to
	 * guess about, so the sequence stops here rather than picking a table.
	 */
	printf("haydn-gpu: step 2: no bin for speed-bin %u (the tree has 0, 1, 3, 5, 7); "
	    "not guessing a table\n", speed_bin);
	return 2;
}
/*
 * Step 1: the block is where the tree says. Read the identification registers
 * and compare the chip id against the one the device tree publishes. A GPU
 * block that answers all ones, or answers with a different chip, is the wrong
 * address -- which is exactly what the UFS PHY mistake taught this repository
 * to check for.
 */
static int
haydn_gpu_step1(void)
{
	vm_offset_t kgsl;
	uint32_t id0, id1, rev;
	uint32_t chipid;

	kgsl = ml_io_map(haydn_gpu_blocks[0].phys, haydn_gpu_blocks[0].size);
	if (kgsl == 0) {
		printf("haydn-gpu: 3d0 at 0x%llx did not map\n",
		    (unsigned long long)haydn_gpu_blocks[0].phys);
		return 1;
	}

	id0 = haydn_gpu_read32(kgsl, KGSL_IDENTIFY_0);
	id1 = haydn_gpu_read32(kgsl, KGSL_IDENTIFY_1);
	rev = haydn_gpu_read32(kgsl, KGSL_REVISION);

	printf("haydn-gpu: step 1 3d0 identify %08x %08x revision %08x\n",
	    id0, id1, rev);

	if (id0 == 0xffffffffu && id1 == 0xffffffffu) {
		printf("haydn-gpu: the block reads all ones - nothing is there\n");
		return 1;
	}

	/* The chip id in the device tree is the authority; the registers only say
	 * whether something answered. */
	chipid = HAYDN_GPU_CHIPID;
	printf("haydn-gpu: device tree says chipid %08x (Adreno 660), "
	    "ubwc %u, bank bit %u, min access %u\n",
	    chipid, HAYDN_GPU_UBWC_MODE, HAYDN_GPU_BANK_BIT, HAYDN_GPU_MIN_ACCESS);

	return 0;
}




/*
 * GMU registers, at 0x3d6a000. a6xx_gmu.xml numbers them in words, so every
 * offset here is four times the number the XML gives; the physical address is
 * 0x3d6a000 plus that.
 *
 * Only three of these are read by step 6; the rest are here because the step
 * prints the block's whole identity in one go, and a register this driver has
 * not named yet cannot be reported.
 */
#define HAYDN_GMU_PHYS          0x03d6a000ULL
#define GMU_WORD(n)             (4u * (n))

#define GMU_CM3_SYSRESET        GMU_WORD(0x5000)   /* 1: the processor is held in reset        */
#define GMU_CM3_BOOT_CONFIG     GMU_WORD(0x5001)
#define GMU_CM3_FW_INIT_RESULT  GMU_WORD(0x501c)   /* 0xbabeface once firmware has started     */
#define GMU_CM3_CFG             GMU_WORD(0x502d)
#define GMU_ALWAYS_ON_COUNTER_L GMU_WORD(0x5088)   /* counts the 19.2 MHz crystal              */
#define GMU_ALWAYS_ON_COUNTER_H GMU_WORD(0x5089)
#define GMU_SPTPRAC_PWR_CLK_STATUS GMU_WORD(0x50d0) /* bit 6: no power, bit 7: no clock       */
#define GMU_RPMH_POWER_STATE    GMU_WORD(0x50ec)
#define GMU_HFI_CTRL_STATUS     GMU_WORD(0x5180)
#define GMU_HFI_VERSION_INFO    GMU_WORD(0x5181)
#define GMU_GENERAL_7           GMU_WORD(0x51cc)
#define GMU_AO_HOST_INTERRUPT_STATUS GMU_WORD(0x9305)
#define GMU_RSCC_CONTROL_ACK    GMU_WORD(0x9308)
#define GMU_AO_GPU_CX_BUSY_STATUS GMU_WORD(0x930c)
#define GMU_AHB_FENCE_STATUS    GMU_WORD(0x9313)

/* The bus interface (GBIF) is in the 3D core's page but in the CX half. */
#define HAYDN_GBIF_PHYS         (0x03d00000ULL + 4u * 0x3c00)
#define GBIF_HALT               (4u * 0x45)
#define GBIF_HALT_ACK           (4u * 0x46)

/*
 * The GMU's RPMh channel: RSCC at 0x3de0000, the third reg of kgsl-3d0
 * (reg-names: kgsl_3d0_reg_memory, cx_dbgc, rscc, isense_cntl, qdss_gfx,
 * rdpm_cx, rdpm_mx - so rscc is 0x3de0000 + 0x10000 as the device tree lists
 * it, and this driver maps the 0x2000 of it that holds the status registers).
 *
 * Through these slots the GMU's firmware raises and lowers the 3D core's rail
 * without this kernel running at all. Reading them says what state that
 * conversation is in; writing them is how the 3D core is asked for its power,
 * and that is step 17, not this one.
 *
 * Offsets are HakiOS's, in words; a6xx_gmu.xml domain A6XX_RSCC.
 */
#define HAYDN_RSCC_PHYS         0x03de0000ULL
#define HAYDN_RSCC_SIZE         0x2000

#define RSCC_DRV_CONFIG         0x00c
#define RSCC_RSC_STATUS0_DRV0   (4u * 0x004)   /* bit 16: handed to the always-on sequencer */
#define RSCC_PDC_SLAVE_ID_DRV0  (4u * 0x00b)
#define RSCC_SEQ_BUSY_DRV0      (4u * 0x101)
#define RSCC_SEQ_MEM_0_DRV0     (4u * 0x180)
#define RSCC_TCS0_DRV0_STATUS   (4u * 0x346)
#define RSCC_ASLEEP             (1u << 16)

/*
 * Four command slots at 0xd00 + 0x2a0 n (Linux's rpmh-rsc.c layout):
 * +0x10 commands whose completion is waited for, +0x14 control, +0x18 idle,
 * +0x1c commands enabled, then 20 bytes a command from +0x30: number,
 * address, data, status.
 */
#define RSCC_SLOTS              0xd00u
#define RSCC_SLOT_SIZE          0x2a0u
#define RSCC_SLOT_COUNT         4u
#define RSCC_SLOT_CMD           (4u * 0xc)   /* commands from the slot's base */
#define RSCC_SLOT_WAIT          0x10
#define RSCC_SLOT_CTRL          0x14
#define RSCC_SLOT_IDLE          0x18
#define RSCC_SLOT_ENABLED       0x1c

/*
 * The SMMU in front of the GPU: kgsl-smmu@3da0000, compatible qcom,qsmmu-v500,
 * reg = <0x3da0000 0x20000 0x3dc2000 0x20>, reg-names "base" and "tcu-base".
 *
 * Note what the two regs mean: the first window ends at 0x3dc0000, and the
 * second one starts at 0x3dc2000. **The TCU and the two TBUs are outside the
 * main window**, so a driver that maps only reg[0] cannot reach them:
 *
 *     smmu      0x3da0000 + 0x20000     the global and context registers
 *     tcu-base  0x3dc2000 + 0x20        the TCU's own page
 *     tbu0      0x3dc5000 + 0x1000      gfx_0_tbu, streams 0x000..0x3ff
 *     tbu1      0x3dc9000 + 0x1000      gfx_1_tbu, streams 0x400..0x7ff
 *     status    0x3dc2200 + 0x8 / 0x3dc2208 + 0x8   each TBU's status page
 *
 * [0x3dc0000, 0x3de0000) covers all of those in one map and stops exactly at
 * RSCC (0x3de0000), so that is what this driver maps.
 *
 * Six streams use it, from qcom,actlr on the SMMU node and the iommus
 * properties of the contexts: 0 (gfx3d_user), 1 (gfx3d_lpac), 2 (gfx3d_secure),
 * 4, 5 (the GMU) and 7.
 *
 * Offsets are Arm SMMU-500's (IHI 0062D.c) global space 0, plus Qualcomm's
 * additions - qcom,qsmmuv500 is not a standard MMU-500 and its registers past
 * the architecture's are the vendor's.
 */
#define HAYDN_SMMU_PHYS         0x03da0000ULL
#define HAYDN_SMMU_SIZE         0x20000
#define HAYDN_SMMU_PERIPH_PHYS  0x03dc0000ULL   /* TCU + both TBUs + their status */
#define HAYDN_SMMU_PERIPH_SIZE  0x20000

/* Global space 0, the architecture's own registers. */
#define SMMU_SCR0               0x000
#define SMMU_IDR0               0x020   /* [7:0] stream match registers              */
#define SMMU_IDR1               0x024   /* [30:28] log2(pages)-1, [7:0] contexts     */
#define SMMU_IDR2               0x028
#define SMMU_IDR7               0x03c
#define SMMU_SGFSR              0x048   /* global fault status                       */

#define SMMU_IDR0_NUMSMRG(idr0) ((idr0) & 0xffu)
#define SMMU_IDR1_NUMCB(idr1)   ((idr1) & 0xffu)

/* A stream match register: bit 31 valid, [30:16] mask, [14:0] stream id. */
#define SMMU_SMR(n)             (0x800u + 4u * (n))
#define SMMU_S2CR(n)            (0xc00u + 4u * (n))
#define SMMU_SMR_VALID          (1u << 31)
#define SMMU_S2CR_TYPE_SHIFT    16      /* 0 translate, 1 bypass, 2 fault */
#define SMMU_S2CR_CBNDX(s2cr)   ((s2cr) & 0xffu)

/* Context banks live in their own pages off the base. */
#define SMMU_CBAR(n)            (4u * (n))
#define SMMU_CB_SCTLR           0x00    /* bit 0: translation on */
#define SMMU_CB_FSR             0x58
/* ---- the pure parts of steps 4 and 5 -------------------------------------- */

/*
 * What the vendor's gdsc_probe writes into a GDSC's control register before it
 * ever enables the switch: hardware control off, software override off, the
 * clock-disable wait set from the node's qcom,clk-dis-wait-val.
 *
 * Only the three fields the vendor touches are changed; everything else in the
 * register is carried through as it was read, because a GDSC's control word
 * holds state this driver does not own.
 */
uint32_t
haydn_gpu_cx_prepare(uint32_t gdscr)
{
	uint32_t v;

	v = gdscr & ~(GDSC_HW_CONTROL | GDSC_SW_OVERRIDE | GDSC_CLK_DIS_WAIT_MASK);
	v |= (uint32_t)GDSC_CX_CLK_DIS_WAIT << GDSC_CLK_DIS_WAIT_SHIFT;

	return v;
}

/*
 * The config word for a root clock generated from the 300 MHz tap of GPLL0.
 *
 * The field in [4:0] is 2 * divider - 1, where divider = 300 MHz / rate. That
 * divider is **not an integer**: the GMU's 200 MHz needs 1.5, and the vendor's
 * frequency table writes exactly that -- `F(200000000, P_GPLL0_OUT_MAIN_DIV, 1.5)`
 * -- which its macro turns into 2 * 1.5 - 1 = 2.
 *
 * So the arithmetic is done against the tap's parent, 600 MHz, where every
 * divider is an integer: 600 / 200 = 3, and 3 - 1 = 2. Doing it as
 * `300e6 / hz` in integers loses the half and the check then rejects 200 MHz,
 * which is the one rate the GMU actually needs.
 *
 * A rate that does not divide 600 MHz exactly returns 0 -- the caller must
 * refuse rather than program a neighbouring rate.
 */
uint32_t
haydn_gpu_rcg_cfg(uint32_t hz)
{
	const uint32_t parent = 600000000u;      /* GPLL0 from which the tap divides */
	uint32_t value;

	if (hz == 0 || hz > 300000000u || parent % hz != 0) {
		return 0;
	}
	value = parent / hz;                     /* 2 * divider, exactly */
	if (value < 1u || value - 1u > 0x1fu) {
		return 0;
	}

	return RCG_HW_CLK_CTRL |
	    ((uint32_t)RCG_SRC_GPLL0_DIV << 8) |
	    (value - 1u);
}

/* A branch reads 1 in bit 31 while it is off; a running branch reads 0 there. */
bool
haydn_gpu_branch_on(uint32_t cbcr)
{
	return (cbcr & CBCR_CLK_OFF) == 0;
}
/* ---- step 4: the CX power switch ----------------------------------------- */

/*
 * Whether the switch reports itself on. Two registers say it, and either is
 * enough: GPUCC_CX_GDSCR's bit 31, or GPUCC_CX_HW_CTRL's, which is where the
 * vendor's driver looks when the switch is under hardware control.
 */
bool
haydn_gpu_gdsc_is_on(uint32_t gdscr, uint32_t hw_ctrl)
{
	return ((gdscr | hw_ctrl) & GDSC_POWER_ON) != 0;
}

/*
 * The decision, before any write. Four outcomes, and three of them are
 * refusals: this is the step where a wrong guess costs a phone that has to be
 * restarted, so every case that is not "off and ours" stops.
 *
 * Order matters. The 3D core having power already is checked first because it
 * is the worst state: the core is somewhere in the middle of something from a
 * previous run, it does not take commands, and there is no way back except a
 * restart. HakiOS saw that once and it hung the whole phone.
 */
int
haydn_gpu_cx_decision(uint32_t gdscr, uint32_t gx)
{
	/* The 3D core kept its power while the rest of the block lost it. */
	if (gx & GDSC_POWER_ON) {
		return HAYDN_CX_CORE_STALE;
	}

	/* The switch is on: an earlier kernel left the block running. */
	if (gdscr & GDSC_POWER_ON) {
		return HAYDN_CX_ALREADY_ON;
	}

	/* Something other than software operates it. */
	if (gdscr & GDSC_HW_CONTROL) {
		return HAYDN_CX_HW_CONTROLLED;
	}

	return HAYDN_CX_OFF;
}

/*
 * Step 4: clear the CX switch's software collapse bit and wait for the switch
 * to say it is on.
 *
 * The rail under it (cx.lvl) is up for as long as the SoC runs at all, so the
 * switch is the only thing between this and a powered GMU. 500 polls of 100 us
 * is the 50 ms the vendor's driver allows; a switch that has not come on by
 * then is not going to.
 */
static int
haydn_gpu_step4(void)
{
	vm_offset_t gpucc;
	uint32_t gdscr, hw_ctrl, gx, prepared;
	int decision;
	int i;

	gpucc = ml_io_map(haydn_gpu_blocks[8].phys, haydn_gpu_blocks[8].size);
	if (gpucc == 0) {
		printf("haydn-gpu: gpucc at 0x%llx did not map\n",
		    (unsigned long long)haydn_gpu_blocks[8].phys);
		return 4;
	}

	gdscr = haydn_gpu_read32(gpucc, GPUCC_CX_GDSCR);
	hw_ctrl = haydn_gpu_read32(gpucc, GPUCC_CX_HW_CTRL);
	gx = haydn_gpu_read32(gpucc, GPUCC_GX_GDSCR);

	printf("haydn-gpu: step 4 before: cx_gdscr %08x hw_ctrl %08x gx_gdscr %08x\n",
	    gdscr, hw_ctrl, gx);

	decision = haydn_gpu_cx_decision(gdscr, gx);
	switch (decision) {
	case HAYDN_CX_CORE_STALE:
		printf("haydn-gpu: step 4: the 3D core has power already, from an earlier "
		    "run. Not usable until the phone is restarted\n");
		return 4;

	case HAYDN_CX_ALREADY_ON:
		/*
		 * An earlier kernel left the block running. HakiOS stops what it left
		 * and starts again; that sequence is the whole shutdown path this
		 * driver does not have. Going on would mean trusting another kernel's
		 * left-over state, so this stops.
		 */
		printf("haydn-gpu: step 4: CX is on already, left by an earlier kernel; "
		    "this driver does not adopt a running block\n");
		return 4;

	case HAYDN_CX_HW_CONTROLLED:
		printf("haydn-gpu: step 4: the switch is under hardware control: not "
		    "software's to operate\n");
		return 4;

	default:
		break;
	}

	/*
	 * The vendor's gdsc_probe configuration first, then the collapse bit: a
	 * switch whose HW_CONTROL or SW_OVERRIDE is still set does not come on
	 * however many times the collapse bit is written.
	 */
	prepared = haydn_gpu_cx_prepare(gdscr);
	haydn_gpu_write32(gpucc, GPUCC_CX_GDSCR, prepared);
	haydn_gpu_write32(gpucc, GPUCC_CX_GDSCR, prepared & ~GDSC_SW_COLLAPSE);

	for (i = 0; i < 500; i++) {
		uint32_t now = haydn_gpu_read32(gpucc, GPUCC_CX_GDSCR);
		uint32_t hw = haydn_gpu_read32(gpucc, GPUCC_CX_HW_CTRL);
		if (haydn_gpu_gdsc_is_on(now, hw)) {
			break;
		}
		delay_for_us(100);
	}

	gdscr = haydn_gpu_read32(gpucc, GPUCC_CX_GDSCR);
	hw_ctrl = haydn_gpu_read32(gpucc, GPUCC_CX_HW_CTRL);
	gx = haydn_gpu_read32(gpucc, GPUCC_GX_GDSCR);

	printf("haydn-gpu: step 4 after:  cx_gdscr %08x hw_ctrl %08x gx_gdscr %08x\n",
	    gdscr, hw_ctrl, gx);

	if (!haydn_gpu_gdsc_is_on(gdscr, hw_ctrl)) {
		printf("haydn-gpu: step 4: CX does not come on\n");
		return 4;
	}

	printf("haydn-gpu: step 4: CX is on (the GMU, the bus interface and the "
	    "GPU's SMMU now have power)\n");

	return 0;
}


/* ---- step 5: the clocks -------------------------------------------------- */

/* Turn a branch on and see it run. `must` says whether its status can be trusted. */
static bool
haydn_gpu_branch_on_now(vm_offset_t base, const char *name, uint32_t cbcr, bool must)
{
	uint32_t was, now;
	int i;

	was = haydn_gpu_read32(base, cbcr);
	if (haydn_gpu_branch_on(was)) {
		return TRUE;
	}
	haydn_gpu_write32(base, cbcr, was | CBCR_ENABLE);

	for (i = 0; i < 10; i++) {
		now = haydn_gpu_read32(base, cbcr);
		if (haydn_gpu_branch_on(now)) {
			return TRUE;
		}
		delay_for_us(1);
	}

	printf("haydn-gpu: %s stays off (%08x)%s\n", name, now,
	    must ? "" : "; its status bit is not one to rely on, going on");

	return !must;
}

/*
 * Set a root clock's source and divider, then command the update and wait for
 * the command bit to clear. The vendor's clk_rcg2 path, in order: force
 * ROOT_EN, wait for ROOT_OFF to clear, write the config, update.
 */
static bool
haydn_gpu_rcg_set(vm_offset_t gpucc, const char *name, uint32_t rcgr, uint32_t hz)
{
	uint32_t cfg, was, cmd;
	int i;

	cfg = haydn_gpu_rcg_cfg(hz);
	if (cfg == 0) {
		printf("haydn-gpu: %s cannot be had from the 300 MHz tap at %u Hz\n",
		    name, hz);
		return FALSE;
	}

	cmd = haydn_gpu_read32(gpucc, rcgr);
	haydn_gpu_write32(gpucc, rcgr, cmd | RCG_ROOT_EN);

	for (i = 0; i < 500; i++) {
		if ((haydn_gpu_read32(gpucc, rcgr) & RCG_ROOT_OFF) == 0) {
			break;
		}
		delay_for_us(1);
	}

	was = haydn_gpu_read32(gpucc, rcgr + 4);
	haydn_gpu_write32(gpucc, rcgr + 4, (was & ~RCG_CFG_MASK) | cfg);
	haydn_gpu_write32(gpucc, rcgr, haydn_gpu_read32(gpucc, rcgr) | RCG_UPDATE);

	for (i = 0; i < 500; i++) {
		if ((haydn_gpu_read32(gpucc, rcgr) & RCG_UPDATE) == 0) {
			haydn_gpu_write32(gpucc, rcgr,
			    haydn_gpu_read32(gpucc, rcgr) & ~RCG_ROOT_EN);
			printf("haydn-gpu: %s at %u Hz (cfg %08x)\n", name,
			    hz, haydn_gpu_read32(gpucc, rcgr + 4));
			return TRUE;
		}
		delay_for_us(1);
	}

	printf("haydn-gpu: %s does not take its new source (command %08x)\n",
	    name, haydn_gpu_read32(gpucc, rcgr));

	return FALSE;
}

/*
 * Steps 4 and 5 in one: power CX, then the clocks that half needs.
 *
 * What runs where, and why it cannot be reordered:
 *
 *   GCC       the 300 MHz tap voted on, then the three bus branches. The GPU
 *             block's register bus is one of these; touching GPUCC before it
 *             runs is what hangs the bus rather than failing.
 *   GPUCC     the GMU's and the hub's root clocks set to 200 and 150 MHz, then
 *             the six branches the GMU and the SMMU sit behind.
 *
 * `must` marks the branches whose status bit is the truth. gpu_cc_ahb's is
 * not: it reads 0 before and after its enable bit is written, on this phone
 * and on its siblings, which is why Linux gives it no bit to check.
 */
static int
haydn_gpu_step5(void)
{
	vm_offset_t gcc, gpucc;
	uint32_t vote;

	gcc = ml_io_map(HAYDN_GCC_PHYS, HAYDN_GCC_SIZE);
	if (gcc == 0) {
		printf("haydn-gpu: gcc at 0x%llx did not map\n",
		    (unsigned long long)HAYDN_GCC_PHYS);
		return 5;
	}
	gpucc = ml_io_map(haydn_gpu_blocks[8].phys, haydn_gpu_blocks[8].size);
	if (gpucc == 0) {
		printf("haydn-gpu: gpucc at 0x%llx did not map\n",
		    (unsigned long long)haydn_gpu_blocks[8].phys);
		return 5;
}

	/* 1. The 300 MHz tap of GPLL0, voted on for the GPU. */
	vote = haydn_gpu_read32(gcc, GCC_PLL_VOTE);
	haydn_gpu_write32(gcc, GCC_PLL_VOTE, vote | GCC_PLL_VOTE_GPLL0_DIV);
	printf("haydn-gpu: step 5 gpll0 vote %08x -> %08x\n",
	    vote, haydn_gpu_read32(gcc, GCC_PLL_VOTE));

	/* 2. The three bus branches in GCC. */
	if (!haydn_gpu_branch_on_now(gcc, "gpu_memnoc_gfx", GCC_GPU_MEMNOC_GFX, FALSE) ||
	    !haydn_gpu_branch_on_now(gcc, "gpu_snoc_dvm_gfx", GCC_GPU_SNOC_DVM_GFX, TRUE) ||
	    !haydn_gpu_branch_on_now(gcc, "ddrss_gpu_axi", GCC_DDRSS_GPU_AXI, FALSE)) {
		return 5;
	}

	/* 3. The GMU's and the hub's rates. */
	if (!haydn_gpu_rcg_set(gpucc, "gmu_clk_src", HAYDN_GMU_RCGR, 200000000u) ||
	    !haydn_gpu_rcg_set(gpucc, "hub_clk_src", HAYDN_HUB_RCGR, 150000000u)) {
		return 5;
	}

	/* 4. The branches the GMU and the SMMU sit behind. */
	if (!haydn_gpu_branch_on_now(gpucc, "cb", GPUCC_CB_CBCR, FALSE) ||
	    !haydn_gpu_branch_on_now(gpucc, "cxo", GPUCC_CXO_CBCR, TRUE) ||
	    !haydn_gpu_branch_on_now(gpucc, "ahb", GPUCC_AHB_CBCR, FALSE) ||
	    !haydn_gpu_branch_on_now(gpucc, "hub_aon", GPUCC_HUB_AON_CBCR, TRUE) ||
	    !haydn_gpu_branch_on_now(gpucc, "hub_cx_int", GPUCC_HUB_CX_INT_CBCR, TRUE) ||
	    !haydn_gpu_branch_on_now(gpucc, "cx_gmu", GPUCC_CX_GMU_CBCR, TRUE) ||
	    !haydn_gpu_branch_on_now(gpucc, "smmu_vote", GPUCC_SMMU_VOTE_CBCR, FALSE)) {
		return 5;
	}

	printf("haydn-gpu: step 5: the GMU runs at 200 MHz, the hub at 150 MHz, "
	    "and the SMMU's clock is voted for\n");

	return 0;
}

/* ---- step 6: the first words from the GPU block --------------------------- */

/*
 * Step 6: read the GMU and the bus interface. Still no writes.
 *
 * This is the step that answers the question the whole sequence rests on: is
 * there a GMU behind that address, and is it the one the device tree says?
 *
 * The tell is the always-on counter. The GMU counts the 19.2 MHz crystal
 * whether or not firmware runs, so reading it twice 10 ms apart and dividing
 * gives a rate: 19.2 MHz means the block is alive and clocked, anything else
 * (zero, or the ceiling) means the map is wrong or the clocks never came on.
 * HakiOS uses the same test on its own board and calls it "THE GPU BLOCK IS
 * ALIVE".
 */
static int
haydn_gpu_step6(void)
{
	vm_offset_t gmu, gbif;
	uint32_t sysreset, fw_init, hfi_ctrl, hfi_ver, cfg, power;
	uint32_t counter_before, counter_after, hz;
	uint64_t started, nanos;

	gmu = ml_io_map(HAYDN_GMU_PHYS, HAYDN_GMU_MAP_SIZE);
	if (gmu == 0) {
		printf("haydn-gpu: the GMU at 0x%llx did not map\n",
		    (unsigned long long)HAYDN_GMU_PHYS);
		return 6;
	}

	sysreset = haydn_gpu_read32(gmu, GMU_CM3_SYSRESET);
	fw_init = haydn_gpu_read32(gmu, GMU_CM3_FW_INIT_RESULT);
	hfi_ctrl = haydn_gpu_read32(gmu, GMU_HFI_CTRL_STATUS);
	hfi_ver = haydn_gpu_read32(gmu, GMU_HFI_VERSION_INFO);
	cfg = haydn_gpu_read32(gmu, GMU_CM3_CFG);
	power = haydn_gpu_read32(gmu, GMU_SPTPRAC_PWR_CLK_STATUS);

	printf("haydn-gpu: step 6 gmu sysreset %08x fw_init %08x cm3_cfg %08x\n",
	    sysreset, fw_init, cfg);
	printf("haydn-gpu: step 6 hfi ctrl %08x version %08x, power %08x "
	    "(3D core: %s power, %s clock)\n",
	    hfi_ctrl, hfi_ver, power,
	    (power & (1u << 6)) ? "no" : "has",
	    (power & (1u << 7)) ? "no" : "has");

	/* The always-on counter, twice, 10 ms apart. */
	started = mach_absolute_time();
	counter_before = haydn_gpu_read32(gmu, GMU_ALWAYS_ON_COUNTER_L);
	IOSleep(10);
	counter_after = haydn_gpu_read32(gmu, GMU_ALWAYS_ON_COUNTER_L);
	absolutetime_to_nanoseconds(mach_absolute_time() - started, &nanos);

	hz = 0;
	if (nanos != 0) {
		hz = (uint32_t)((uint64_t)(counter_after - counter_before) *
		    NSEC_PER_SEC / nanos);
	}

	printf("haydn-gpu: step 6 the GMU's counter ran %u Hz: %s\n", hz,
	    (hz > 18000000 && hz < 20500000) ?
	    "the 19.2 MHz crystal - THE BLOCK IS ALIVE" :
	    "not the crystal - either the map is wrong or the clocks never came on");

	/* The bus interface, in the CX half: readable, and the GMU will need it. */
	gbif = ml_io_map(HAYDN_GBIF_PHYS, 0x1000);
	if (gbif != 0) {
		printf("haydn-gpu: step 6 gbif halt %08x ack %08x\n",
		    haydn_gpu_read32(gbif, GBIF_HALT),
		    haydn_gpu_read32(gbif, GBIF_HALT_ACK));
	}

	/*
	 * The map is right if any register of the block answered with something
	 * other than all ones. A block that is not there reads 0xffffffff on every
	 * offset, which is also what a wrong address looks like.
	 */
	if (sysreset == 0xffffffffu && fw_init == 0xffffffffu && hfi_ver == 0xffffffffu) {
		printf("haydn-gpu: step 6 every GMU register reads all ones - nothing is "
		    "behind 0x%llx\n", (unsigned long long)HAYDN_GMU_PHYS);
		return 6;
	}

	return 0;
}

/* ---- step 7: the GMU's own channel to RPMh -------------------------------- */

/*
 * Step 7: read RSCC. Still no writes.
 *
 * The interesting bit is RSCC_ASLEEP in RSC_STATUS0_DRV0. It says the channel
 * has been handed to the always-on sequencer, which is the state the GMU's
 * firmware wants it in before it starts voting for the 3D core's rail. If it
 * is not asleep, the channel is still under the application processor's
 * control and step 17 would be voting into a channel someone else owns.
 *
 * The four slots are printed even when empty, because "four slots exist and
 * all are idle" and "the block did not answer" look the same otherwise.
 */
static int
haydn_gpu_step7(void)
{
	vm_offset_t rscc;
	uint32_t status, slave, busy, seq0, tcs0, config;
	uint32_t slot;

	rscc = ml_io_map(HAYDN_RSCC_PHYS, HAYDN_RSCC_SIZE);
	if (rscc == 0) {
		printf("haydn-gpu: rscc at 0x%llx did not map\n",
		    (unsigned long long)HAYDN_RSCC_PHYS);
		return 7;
	}

	config = haydn_gpu_read32(rscc, RSCC_DRV_CONFIG);
	status = haydn_gpu_read32(rscc, RSCC_RSC_STATUS0_DRV0);
	slave = haydn_gpu_read32(rscc, RSCC_PDC_SLAVE_ID_DRV0);
	busy = haydn_gpu_read32(rscc, RSCC_SEQ_BUSY_DRV0);
	seq0 = haydn_gpu_read32(rscc, RSCC_SEQ_MEM_0_DRV0);
	tcs0 = haydn_gpu_read32(rscc, RSCC_TCS0_DRV0_STATUS);

	printf("haydn-gpu: step 7 rscc config %08x status %08x slave %08x\n",
	    config, status, slave);
	printf("haydn-gpu: step 7 seq_busy %08x seq_mem0 %08x tcs0 %08x: "
	    "the channel is %s\n",
	    busy, seq0, tcs0,
	    (status & RSCC_ASLEEP) ? "asleep (the always-on sequencer owns it)" :
	    "awake (the application processor still owns it)");

	for (slot = 0; slot < RSCC_SLOT_COUNT; slot++) {
		vm_offset_t at = rscc + RSCC_SLOTS + RSCC_SLOT_SIZE * slot;
		uint32_t wait, ctrl, idle, enabled;
		uint32_t cmd;

		wait = haydn_gpu_read32(at, RSCC_SLOT_WAIT);
		ctrl = haydn_gpu_read32(at, RSCC_SLOT_CTRL);
		idle = haydn_gpu_read32(at, RSCC_SLOT_IDLE);
		enabled = haydn_gpu_read32(at, RSCC_SLOT_ENABLED);

		cmd = haydn_gpu_read32(at, RSCC_SLOT_CMD);

		printf("haydn-gpu: step 7 slot %u: wait %08x ctrl %08x idle %08x "
		    "enabled %08x; first command %08x\n",
		    slot, wait, ctrl, idle, enabled, cmd);
	}

	/*
	 * A block that answered all ones is not there. RSCC's config register is
	 * small and readable at any time, so all ones means a wrong address.
	 */
	if (config == 0xffffffffu && status == 0xffffffffu && busy == 0xffffffffu) {
		printf("haydn-gpu: step 7 every RSCC register reads all ones - nothing is "
		    "behind 0x%llx\n", (unsigned long long)HAYDN_RSCC_PHYS);
		return 7;
	}

	return 0;
}

/* ---- steps 8 and 9: the SMMU ---------------------------------------------- */

/*
 * Step 8: read the SMMU's identification registers.
 *
 * These are the first registers in this whole sequence whose values can be
 * checked against something outside this phone. IDR0's low byte is how many
 * stream match registers the implementation has, IDR1's low byte how many
 * translation contexts. An MMU-500 answers with a number in the tens; a block
 * that is not there answers all ones, which reads as 255 of both.
 *
 * The node carries qcom,skip-init, which is the vendor saying its firmware
 * leaves the stream table as it finds it. So the table is read, never written,
 * and a stream already valid is another boot stage's, not this driver's.
 */
static int
haydn_gpu_step8(void)
{
	vm_offset_t smmu;
	uint32_t scr0, idr0, idr1, idr2, idr7, sgfsr;
	uint32_t num_smr, num_cb;

	smmu = ml_io_map(HAYDN_SMMU_PHYS, HAYDN_SMMU_SIZE);
	if (smmu == 0) {
		printf("haydn-gpu: the SMMU at 0x%llx did not map\n",
		    (unsigned long long)HAYDN_SMMU_PHYS);
		return 8;
	}

	scr0 = haydn_gpu_read32(smmu, SMMU_SCR0);
	idr0 = haydn_gpu_read32(smmu, SMMU_IDR0);
	idr1 = haydn_gpu_read32(smmu, SMMU_IDR1);
	idr2 = haydn_gpu_read32(smmu, SMMU_IDR2);
	idr7 = haydn_gpu_read32(smmu, SMMU_IDR7);
	sgfsr = haydn_gpu_read32(smmu, SMMU_SGFSR);

	num_smr = SMMU_IDR0_NUMSMRG(idr0);
	num_cb = SMMU_IDR1_NUMCB(idr1);

	printf("haydn-gpu: step 8 smmu scr0 %08x idr0 %08x idr1 %08x\n",
	    scr0, idr0, idr1);
	printf("haydn-gpu: step 8 idr2 %08x idr7 %08x sgfsr %08x\n",
	    idr2, idr7, sgfsr);
	printf("haydn-gpu: step 8 %u stream match registers, %u translation "
	    "contexts\n", num_smr, num_cb);

	/*
	 * All ones in the identification registers is the signature of a wrong
	 * address, not of an SMMU with 255 of everything: no MMU-500 has that many
	 * contexts, and a real one reads IDR7 with a product code in it.
	 */
	if (idr0 == 0xffffffffu && idr1 == 0xffffffffu) {
		printf("haydn-gpu: step 8 the identification registers read all ones - "
		    "nothing is behind 0x%llx\n", (unsigned long long)HAYDN_SMMU_PHYS);
		return 8;
	}
	if (num_cb == 0 || num_cb > 64) {
		printf("haydn-gpu: step 8 %u contexts is not a number an MMU-500 reports\n",
		    num_cb);
		return 8;
	}

	return 0;
}

/*
 * Step 9: read the stream table.
 *
 * Every stream ID the device tree mentions is looked up: 0, 1, 2, 4, 5 and 7
 * (qcom,actlr on the SMMU node, and the iommus of gfx3d_user, gfx3d_lpac,
 * gfx3d_secure and the GMU). For each, the matching SMR and the S2CR it points
 * at say whether the stream is already translating, bypassing, or faulting.
 *
 * Nothing is written. qcom,skip-init means the boot stage before this one owns
 * this table, and the useful answer here is what it left.
 */
static int
haydn_gpu_step9(void)
{
	static const uint32_t streams[] = { 0, 1, 2, 4, 5, 7 };
	vm_offset_t smmu;
	uint32_t idr0, num_smr;
	uint32_t n, found = 0;

	smmu = ml_io_map(HAYDN_SMMU_PHYS, HAYDN_SMMU_SIZE);
	if (smmu == 0) {
		return 9;
	}

	idr0 = haydn_gpu_read32(smmu, SMMU_IDR0);
	num_smr = SMMU_IDR0_NUMSMRG(idr0);
	if (num_smr > 128u) {
		num_smr = 128u;
	}

	for (n = 0; n < num_smr; n++) {
		uint32_t smr = haydn_gpu_read32(smmu, SMMU_SMR(n));
		uint32_t s2cr, sid, type;
		uint32_t k;

		if ((smr & SMMU_SMR_VALID) == 0) {
			continue;
		}
		sid = smr & 0x7fffu;
		s2cr = haydn_gpu_read32(smmu, SMMU_S2CR(n));
		type = (s2cr >> SMMU_S2CR_TYPE_SHIFT) & 3u;

		for (k = 0; k < sizeof(streams) / sizeof(streams[0]); k++) {
			if (streams[k] != sid) {
				continue;
			}
			found++;
			printf("haydn-gpu: step 9 stream %u: smr %08x s2cr %08x -> "
			    "context %u, %s\n",
			    sid, smr, s2cr, SMMU_S2CR_CBNDX(s2cr),
			    type == 0 ? "translating" :
			    type == 1 ? "bypassing" : "faulting");
		}
	}

	printf("haydn-gpu: step 9 %u of the %u streams the tree names are in the "
	    "table\n", found, (unsigned)(sizeof(streams) / sizeof(streams[0])));

	/* A table with no valid entry at all is the normal state before a kernel
	 * sets it up, so it is reported and not treated as a failure. */
	return 0;
}
int
haydn_gpu_probe(void)
{
	uint32_t wanted = 0;
	const struct haydn_gpu_bin *bin = NULL;
	int result;

	if (!PE_parse_boot_argn("adreno", &wanted, sizeof(wanted)) || wanted == 0) {
		return 0;
	}
	if (wanted > HAYDN_GPU_STEPS) {
		wanted = (uint32_t)HAYDN_GPU_STEPS;
	}

	printf("haydn-gpu: steps 1..%u of %u; this driver implements %u\n",
	    wanted, (unsigned)HAYDN_GPU_STEPS, (unsigned)HAYDN_GPU_STEPS_DONE);

	if ((result = haydn_gpu_step1()) != 0) {
		return result;
	}
	if (wanted < 2) {
		return 0;
	}
	if ((result = haydn_gpu_step2(&bin)) != 0) {
		return result;
	}
	if (wanted < 3) {
		return 0;
	}
	if ((result = haydn_gpu_step3()) != 0) {
		return result;
	}
	if (wanted < 4) {
		return 0;
	}
	if ((result = haydn_gpu_step4()) != 0) {
		return result;
	}
	if (wanted < 5) {
		return 0;
	}
	if ((result = haydn_gpu_step5()) != 0) {
		return result;
	}
	if (wanted < 6) {
		return 0;
	}
	if ((result = haydn_gpu_step6()) != 0) {
		return result;
	}
	if (wanted < 7) {
		return 0;
	}
	if ((result = haydn_gpu_step7()) != 0) {
		return result;
	}
	if (wanted < 8) {
		return 0;
	}
	if ((result = haydn_gpu_step8()) != 0) {
		return result;
	}
	if (wanted < 9) {
		return 0;
	}
	if ((result = haydn_gpu_step9()) != 0) {
		return result;
	}

	if (wanted > HAYDN_GPU_STEPS_DONE) {
		printf("haydn-gpu: step %u is not implemented in this driver\n",
		    (unsigned)HAYDN_GPU_STEPS_DONE + 1);
	}

	printf("haydn-gpu: steps 1 to %u done; the block is powered\n",
	    (unsigned)HAYDN_GPU_STEPS_DONE);

	return 0;
}
