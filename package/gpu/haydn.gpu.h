/*
 * The GPU of haydn: an Adreno 660 (chipid 0x06060001) at 0x3d00000.
 *
 * This file is the register map and the step table, not a driver. What it is
 * for is the same thing HakiOS's hakios.adreno.c is for on its own board: a
 * list of the things that have to happen, in order, each with the address it
 * happens at, so that bring-up is a matter of walking the list and watching
 * which step stops.
 *
 * Every address is from the phone's own device tree (qcom,kgsl-3d0@3d00000,
 * qcom,gmu@3d69000, qcom,gpucc@3d90000, kgsl-smmu@3da0000); see
 * docs/hardware.md.
 *
 * What transfers from HakiOS's driver, and what does not:
 *
 *   transfers    the delivery-unit and SMMU offsets. That driver's gpucc,
 *                gmu and smmu blocks are 0x3d90000, 0x3d6a000 and 0x3da0000:
 *                the same three addresses this board reports. The register
 *                offsets it walks are offsets within those blocks.
 *
 *   does not     anything keyed to the chip: the speed table (an Adreno 642L
 *                tops out at 550 MHz, this one at 855 to 900), the QFPROM
 *                fuse offsets, and the CX/GX GDSC layout.
 *
 * Boot argument: adreno=N runs steps 1..N and stops.
 */
#ifndef HAYDN_GPU_H
#define HAYDN_GPU_H

#include <sys/types.h>

/* ---- This board's blocks ------------------------------------------------- */

struct haydn_gpu_block {
	const char *name;
	uint64_t    phys;
	uint32_t    size;
};

/*
 * reg = <0x3d00000 0x40000 0x3d61000 0x800 0x3de0000 0x10000 0x3d8b000 0x2000
 *        0x6900000 0x80000 0x634000 0x1000 0x636000 0x1000>;
 * reg-names = "kgsl_3d0_reg_memory", "cx_dbgc", "rscc", "isense_cntl",
 *             "qdss_gfx", "rdpm_cx", "rdpm_mx";
 */
static const struct haydn_gpu_block haydn_gpu_blocks[] = {
	{ "3d0",      0x0000000003d00000ULL, 0x40000 },
	{ "cx_dbgc",  0x0000000003d61000ULL, 0x800   },
	{ "rscc",     0x0000000003de0000ULL, 0x10000 },
	{ "isense",   0x0000000003d8b000ULL, 0x2000  },
	{ "qdss",     0x0000000006900000ULL, 0x80000 },
	{ "rdpm_cx",  0x0000000000634000ULL, 0x1000  },
	{ "rdpm_mx",  0x0000000000636000ULL, 0x1000  },
	{ "gmu",      0x0000000003d6a000ULL, 0x34000 },
	{ "gpucc",    0x0000000003d90000ULL, 0x9000  },
	{ "smmu",     0x0000000003da0000ULL, 0x20000 },
};

#define HAYDN_GPU_BLOCKS  (sizeof(haydn_gpu_blocks) / sizeof(haydn_gpu_blocks[0]))

/*
 * The GMU's reg says 0x3d6a000 + 0x34000, which runs to 0x3d9e000 and covers
 * two blocks other nodes claim separately: isense at 0x3d8b000 and gpucc at
 * 0x3d90000. The phone's tree says exactly that; it is not a transcription
 * error, and it is why this node is declared with a window larger than the
 * registers it holds.
 *
 * The rule for the driver: map the GMU at its base and no further than its own
 * registers reach. Mapping its declared extent would overlap the other two, and
 * on a kernel that maps device memory once per address, the second mapping
 * either fails or returns a different virtual address than the first for the
 * same physical page.
 *
 * **How far the registers actually reach.** a6xx_gmu.xml gives every offset in
 * words; the highest this driver needs is GMU_AHB_FENCE_STATUS at word 0x9313,
 * which is byte offset 0x24c4c. An earlier draft of this file said 0x10000,
 * which would have cut the map off just below GMU_CM3_SYSRESET (offset
 * 0x14000) -- the very first register step 6 reads. So:
 *
 *     0x3d6a000 + 0x26000 = 0x3d90000      (gpucc's base, not included)
 *
 * 0x26000 is the largest size that does not touch gpucc, and it holds every
 * register through 0x3d8ec4c. It does cover isense's declared range
 * (0x3d8b000..0x3d8d000), but no GMU register lives there, so the mapping is
 * redundant rather than wrong. tests/gpu-addresses.py checks both facts.
 */
#define HAYDN_GMU_MAP_SIZE  0x26000

/*
 * GCC, the global clock controller at 0x100000 (0x1f0000). The GPU's bus clocks
 * live in it, not in GPUCC, so step 5 touches two blocks.
 *
 * These five offsets are **this SoC's**, from gpucc-lahaina / gcc-lahaina as the
 * SM8350 vendor kernel ships them, and cross-checked against UniXNU-venus's
 * Adreno660 GpuPowerBoard.h, which was derived from a Surface Duo 2 (also
 * lahaina, also an Adreno 660). A sibling port's SM8550 numbers differ — its
 * gpu_cc_ahb is 0x911c against 0x1078 here — so these are not transferable.
 */
#define HAYDN_GCC_PHYS          0x00100000ULL
#define HAYDN_GCC_SIZE          0x001f0000

/* Offsets into GCC. */
#define GCC_GPU_CFG_AHB         0x71004
#define GCC_GPU_MEMNOC_GFX      0x7100c
#define GCC_GPU_SNOC_DVM_GFX    0x71018
#define GCC_DDRSS_GPU_AXI       0x71154
#define GCC_PLL_VOTE            0x52000
#define GCC_PLL_VOTE_GPLL0      (1u << 15)   /* gcc_gpu_gpll0_clk_src, 600 MHz */
#define GCC_PLL_VOTE_GPLL0_DIV  (1u << 16)   /* gcc_gpu_gpll0_div_clk_src, 300 MHz */

/* The GMU's PDC block, the second reg of qcom,gmu@3d69000. */
#define HAYDN_GMU_PDC_PHYS      0xb290000ULL
#define HAYDN_GMU_PDC_SIZE      0x10000

/* The two TBUs in front of the GPU's SMMU. */
#define HAYDN_GPU_TBU0_PHYS     0x3dc5000ULL
#define HAYDN_GPU_TBU1_PHYS     0x3dc9000ULL

/* ---- This chip ----------------------------------------------------------- */

/* qcom,chipid in the device tree: the Adreno 660, not a 642L. */
#define HAYDN_GPU_CHIPID        0x06060001u

#define HAYDN_GPU_UBWC_MODE     4
#define HAYDN_GPU_BANK_BIT      0x10
#define HAYDN_GPU_MIN_ACCESS    0x20

/* Interrupts, SPI. */
#define HAYDN_GPU_IRQ           0x12c
#define HAYDN_GMU_HFI_IRQ       0x130
#define HAYDN_GMU_IRQ           0x131

/*
 * The speed bins. The device tree does not carry one table; it carries five,
 * and which one a handset uses is decided by its fuses.
 *
 * Read out of the live firmware tree (/sys/firmware/fdt, 799,754 bytes) at
 * /soc/qcom,kgsl-3d0@3d00000/qcom,gpu-pwrlevel-bins:
 *
 *   bin                    qcom,speed-bin  initial   levels  top    table (MHz)
 *   qcom,gpu-pwrlevels-0   0               9         10      840    840 778 738 676 608 540 491 443 379 315
 *   qcom,gpu-pwrlevels-1   1               10        11      900    900 840 778 738 676 608 540 491 443 379 315
 *   qcom,gpu-pwrlevels-2   3               10        11      900    900 840 778 738 676 608 540 491 443 379 315
 *   qcom,gpu-pwrlevels-3   5               9         10      840    840 778 738 676 608 540 491 443 379 315
 *   qcom,gpu-pwrlevels-4   7               9         10      840    840 778 738 676 608 540 491 443 379 315
 *
 * And the handset says which of them it is running:
 *
 *   /sys/class/kgsl/kgsl-3d0/gpu_available_frequencies
 *   840 778 738 676 608 540 491 443 379 315
 *   /sys/class/kgsl/kgsl-3d0/devfreq/max_freq     -> 840000000
 *   /sys/class/kgsl/kgsl-3d0/devfreq/min_freq     -> 315000000
 *
 * So this handset is one of bins 0, 3 or 4 - three bins, all ten levels, all
 * topping at 840. Which of the three cannot be told from any table: it is read
 * from a QFPROM fuse (qcom,speed-bin), and that is what step 2 of the driver is
 * for. This driver therefore does not choose a table at all until it has read
 * the fuse; a wrong choice would ask for a clock the silicon is not binned for.
 *
 * The Adreno 642L of an SC7280 tops out at 550 MHz, so HakiOS's adreno_speed
 * table (1: 315, 2: 450, 3: 550) does not apply either.
 */
struct haydn_gpu_level {
	uint32_t hz;
	uint32_t level;        /* qcom,level: the RPMh/DDR vote paired with it */
};

struct haydn_gpu_bin {
	uint32_t       speed_bin;   /* qcom,speed-bin: what the fuse has to read */
	uint32_t       initial;     /* qcom,initial-pwrlevel */
	uint32_t       count;
	const struct haydn_gpu_level *levels;
};

/* The ten levels of bins 0, 3 and 4, with the levels the live tree pairs them. */
static const struct haydn_gpu_level haydn_gpu_levels_840[] = {
	{ 840000000, 0x1a0 }, { 778000000, 0x180 }, { 738000000, 0x140 },
	{ 676000000, 0x100 }, { 608000000, 0x0e0 }, { 540000000, 0x0c0 },
	{ 491000000, 0x090 }, { 443000000, 0x080 }, { 379000000, 0x050 },
	{ 315000000, 0x040 },
};

/* The eleven levels of bins 1 and 2. */
static const struct haydn_gpu_level haydn_gpu_levels_900[] = {
	{ 900000000, 0x1b0 }, { 840000000, 0x1a0 }, { 778000000, 0x180 },
	{ 738000000, 0x140 }, { 676000000, 0x100 }, { 608000000, 0x0e0 },
	{ 540000000, 0x0c0 }, { 491000000, 0x090 }, { 443000000, 0x080 },
	{ 379000000, 0x050 }, { 315000000, 0x040 },
};

static const struct haydn_gpu_bin haydn_gpu_bins[] = {
	{ 0,  9, 10, haydn_gpu_levels_840 },
	{ 1, 10, 11, haydn_gpu_levels_900 },
	{ 3, 10, 11, haydn_gpu_levels_900 },
	{ 5,  9, 10, haydn_gpu_levels_840 },
	{ 7,  9, 10, haydn_gpu_levels_840 },
};

#define HAYDN_GPU_BINS  (sizeof(haydn_gpu_bins) / sizeof(haydn_gpu_bins[0]))

/* What this handset reports: ten levels, 840 at the top. */
#define HAYDN_GPU_LEVELS_MAX_MHZ  840
/*
 * The level 0x1b0 of bin 1's top is a guess this driver does not make: bins 1 and
 * 2 do not exist on this handset (its top is 840), so their table is written out
 * for completeness and must not be used until a fuse says so.
 */

/* ---- The steps ----------------------------------------------------------- */

/*
 * One per thing that has to happen, in the order HakiOS found it works. A step
 * says what it is about to touch before it touches it and what it found after;
 * a step that does not find what it needs ends the sequence rather than going
 * on blind.
 *
 * This board's driver implements 1 to 3: they read, they touch no register, and
 * they answer the question the whole sequence depends on -- is the GPU block
 * where the device tree says, and does the fuse say which chip this is. Steps 4
 * and up write.
 */
struct haydn_gpu_step {
	int         number;
	const char *what;
	bool        writes;
};

static const struct haydn_gpu_step haydn_gpu_steps[] = {
	{  1, "read what feeds the GPU from outside: its clocks in gcc, its RPMh supplies", false },
	{  2, "read the fuses that say which GPU this is",                              false },
	{  3, "read the GPU's own clock controller as the loader left it",              false },
	{  4, "write the CX power switch on (the GMU, bus interface and SMMU half)",     true  },
	{  5, "write the clocks of that half on and measure them",                       true  },
	{  6, "read the first words of the GMU and the bus interface",                  false },
	{  7, "read the GMU's own channel to RPMh",                                    false },
	{  8, "read the SMMU in front of the GPU: its ID registers",                    false },
	{  9, "read that SMMU's first translation context",                            false },
	{ 10, "write two words into the GMU's memory and read them back",              true  },
	{ 11, "ask TrustZone whether it takes calls from this kernel",                  false },
	{ 12, "ask TrustZone to check the zap shader's signature",                     false },
	{ 13, "write the GMU's page tables and its SMMU context",                      true  },
	{ 14, "write the GMU firmware into its memory",                                 true  },
	{ 15, "write the GMU's configuration and let its processor out of reset",      true  },
	{ 16, "write the GMU's link to RPMh and start its HFI queues",                 true  },
	{ 17, "ask the GMU to power the 3D core",                                       true  },
	{ 18, "write the 3D core's translation context, ring and microcode",           true  },
	{ 19, "ask TrustZone to load the zap shader",                                   false },
	{ 20, "write the 3D core's registers and start its command processor",         true  },
	{ 21, "command the 3D core out of secure mode",                                 true  },
	{ 22, "command a picture and show it on the panel",                             true  },
};

#define HAYDN_GPU_STEPS  (sizeof(haydn_gpu_steps) / sizeof(haydn_gpu_steps[0]))

/*
 * Which steps this driver implements. Steps 1 to 3 read; step 4 powers CX and
 * step 5 brings its clocks up; step 6 reads the GMU for the first time.
 */
#define HAYDN_GPU_STEPS_DONE   9

/*
 * Walk steps 1..N. Returns 0 when every one of them found what it needed;
 * otherwise the number of the step that stopped.
 *
 * Step 4 is the first write: it clears the CX power switch's software collapse
 * bit and waits for the switch to report itself on. tests/gpu-addresses.py
 * carries the decision table this function implements.
 */
int haydn_gpu_probe(void);

/*
 * What step 4 decides, as a pure function of two register reads, so the table
 * can be tested without a GPU.
 *
 *   gdscr  the value read from GPUCC_CX_GDSCR before anything is written
 *   gx     the value read from GPUCC_GX_GDSCR
 *
 * The result says what to do; the constants are below.
 */
#define HAYDN_CX_OFF            0   /* switch off and safe to turn on         */
#define HAYDN_CX_ALREADY_ON     1   /* on already: an earlier kernel left it  */
#define HAYDN_CX_HW_CONTROLLED  2   /* not software's to operate              */
#define HAYDN_CX_CORE_STALE     3   /* the 3D core has power from an earlier run */

int haydn_gpu_cx_decision(uint32_t gdscr, uint32_t gx);

/* TRUE when a GDSCR reads as "the switch is on". */
bool haydn_gpu_gdsc_is_on(uint32_t gdscr, uint32_t hw_ctrl);

#endif /* HAYDN_GPU_H */
