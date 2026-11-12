/*
 * The storage of haydn: the UFS host controller at 0x1d84000, read only.
 *
 * Two paths, and this file describes both:
 *
 *   1. through the loader. UEFI never exits on this port, so Qualcomm's own
 *      UFSDxe has already brought the controller, its PHY, its clocks and its
 *      power up and stays resident. The loader publishes a page describing
 *      every GPT partition, a request/answer pair and a data buffer; the
 *      kernel writes "partition, LBA, count" and the loader reads it with
 *      that driver. This kernel never touches the controller.
 *
 *   2. this kernel's own list. The controller takes 32 requests at once and
 *      UFSDxe's list has room for one, so for the length of a run this kernel
 *      can point UTRLBA at a list of its own. Still read only.
 *
 * The register block is the UFSHCI standard (JESD223) and is the same on
 * every UFS controller. What is this board's is the address and the PHY:
 *
 *   ufshc@1d84000   reg = <0x1d84000 0x3000 0x1d88000 0x8000 0x1d90000 0x9000>
 *            names    ufs_mem / ufs_ice / ufs_ice_hwkm, interrupt SPI 0x109
 *   ufsphy_mem@1d87000  reg = <0x1d87000 0xe10>
 *            compatible qcom,ufs-phy-qmp-v4-lahaina, two lanes per direction
 *
 * The PHY address is the correction this board's earlier record got wrong:
 * it carried 0x1d80000, which is not this controller's PHY. See
 * docs/hardware.md.
 *
 * Boot arguments:
 *   ufs=1        read through the loader only
 *   ufs=2        the same, and publish the partitions as block devices
 *   ufs_native=1 drive the controller from this kernel
 */
#ifndef HAYDN_UFS_H
#define HAYDN_UFS_H

#include <sys/types.h>

/* ---- What is this board's ------------------------------------------------- */

#define HAYDN_UFSHC_PHYS        0x1d84000ULL
#define HAYDN_UFSHC_SIZE        0x3000
#define HAYDN_UFS_ICE_PHYS      0x1d88000ULL
#define HAYDN_UFS_ICE_SIZE      0x8000
#define HAYDN_UFS_HWKM_PHYS     0x1d90000ULL
#define HAYDN_UFS_HWKM_SIZE     0x9000

/* The correction: this board's PHY, and its size, from the live tree. */
#define HAYDN_UFS_PHY_PHYS      0x1d87000ULL
#define HAYDN_UFS_PHY_SIZE      0xe10

#define HAYDN_UFS_IRQ           0x109    /* SPI */

/* ---- What is every UFS controller's (UFSHCI, JESD223) --------------------- */

#define UFSHC_CAP               0x00
#define UFSHC_VER               0x08
#define UFSHC_HCDDID            0x10
#define UFSHC_HCPMID            0x14
#define UFSHC_AHIT              0x18
#define UFSHC_IS                0x20
#define UFSHC_IE                0x24
#define UFSHC_HCS               0x30
#define UFSHC_HCE               0x34
#define UFSHC_UTRIACR           0x4c
#define UFSHC_UTRLBA            0x50
#define UFSHC_UTRLBAU           0x54
#define UFSHC_UTRLDBR           0x58
#define UFSHC_UTRLCLR           0x5c
#define UFSHC_UTRLRSR           0x60
#define UFSHC_UTRLCNR           0x64
#define UFSHC_UTMRLBA           0x70
#define UFSHC_UTMRLBAU          0x74
#define UFSHC_UTMRLDBR          0x78
#define UFSHC_UTMRLRSR          0x80

/* CAP: how many request slots, and whether the list address is split in two. */
#define CAP_NUTRS(c)            (((c) & 0x1fu) + 1u)
#define CAP_64AS                (1u << 24)

/* HCS: the controller is present, and its list is ready. */
#define HCS_DP                  (1u << 0)
#define HCS_UTRLRDY             (1u << 1)

/* IS: the errors that mean stop, not retry (UE, DFES, UTPES, HCFES, SBFES). */
#define IS_FATAL                ((1u << 2) | (1u << 11) | (1u << 12) | (1u << 16) | (1u << 17))

/* ---- Request descriptor: command type and data direction ------------------ */

#define UTRD_CT_MASK            0xf0000000u
#define UTRD_CT_UFS             (1u << 28)
#define UTRD_DD_MASK            (3u << 25)
#define UTRD_DD_NONE            (0u << 25)
#define UTRD_DD_OUT             (1u << 25)   /* host to device: never issued here */
#define UTRD_DD_IN              (2u << 25)

#define OCS_SUCCESS             0x0
#define OCS_INVALID             0xf

/* ---- UPIU ---------------------------------------------------------------- */

#define UPIU_COMMAND            0x01
#define UPIU_RESPONSE           0x21
#define UPIU_FLAG_READ          0x40
#define UPIU_FLAG_WRITE         0x20   /* refused, always */
#define LUN_WELL_KNOWN          0x80   /* REPORT LUNS, BOOT, RPMB: refused */

/* ---- SCSI operations this driver issues, and nothing else ---------------- */

#define SCSI_READ10             0x28
#define SCSI_READ16             0x88
#define SCSI_INQUIRY            0x12
#define SCSI_TEST_UNIT_READY    0x00
#define SCSI_READ_CAPACITY10    0x25
#define SCSI_READ_CAPACITY16    0x9e
#define SCSI_REQUEST_SENSE      0x03

#define HAYDN_UFS_BLOCK         4096u

/* ---- The loader's shared page -------------------------------------------- */

#define BLOCK_MAGIC             0x4b434f4c42574452ULL   /* "RDWBLOCK" */
#define BLOCK_VERSION           3
#define BLOCK_MAX_PARTS         160
#define BLOCK_OP_READ           0u
#define BLOCK_OP_WRITE          1u   /* refused by this driver */

struct haydn_ufs_part {
	char     name[36];
	uint32_t block_size;
	uint64_t blocks;
	uint64_t start_lba;
	uint16_t unit;
	uint8_t  lun;
	uint8_t  flags;
	uint32_t reserved;
};

struct haydn_ufs_page {
	uint64_t magic;
	uint32_t version;
	uint32_t size;
	uint32_t parts;
	uint32_t buffer_size;
	uint64_t buffer_pa;
	uint32_t write_part_plus_one;
	uint32_t write_caps;
	uint64_t write_first;
	struct {
		volatile uint32_t request;
		uint32_t part;
		uint64_t lba;
		uint64_t count;
		uint32_t op;
		uint32_t reserved;
	} ask __attribute__((aligned(128)));
	struct {
		volatile uint32_t answered;
		uint32_t reserved;
		int64_t status;
		uint64_t served, failed, bytes, ticks;
	} answer __attribute__((aligned(128)));
	struct haydn_ufs_part part[BLOCK_MAX_PARTS] __attribute__((aligned(128)));
};

/*
 * A controller command, checked before it is ever written into a slot. The
 * check is a pure function so tests/ufs-whitelist.py can drive it: every
 * command this driver can build must pass, and every command that would write
 * must be refused.
 */
struct haydn_ufs_command {
	uint8_t  opcode;          /* the SCSI operation in the CDB */
	uint8_t  lun;             /* the logical unit */
	uint8_t  upiu_flags;      /* UPIU flags byte */
	uint8_t  direction;       /* UTRD_DD_NONE / _IN / _OUT, unshifted */
	uint8_t  cdb_length;      /* how many CDB bytes are used */
};

/* TRUE when the command is a read, a probe, or a sense: never a write. */
bool haydn_ufs_permitted(const struct haydn_ufs_command *cmd);

/* Build a READ(10) CDB for `blocks` blocks at `lba`, 4096-byte blocks. */
void haydn_ufs_build_read10(uint8_t cdb[16], uint64_t lba, uint32_t blocks);

/* Build a READ CAPACITY(10) CDB. */
void haydn_ufs_build_read_capacity10(uint8_t cdb[16]);

/* Probe the controller and read its identity. Returns 0 when it answered. */
int haydn_ufs_probe(void);

/* ---- Talking to the loader ------------------------------------------------- */

/*
 * The loader offers the page one of two ways: it publishes its physical address
 * on the boot command line (ufs_shared_pa=), or it is found by scanning the
 * region the loader says it reserved. HakiOS's driver takes the first and
 * HakiOS's loader writes it; this one does the same, and falls back to nothing:
 * a board that has not been given the address says so once and reads no
 * storage.
 *
 * The page is mapped write-combining (VM_WIMG_WCOMB): the kernel writes only
 * the request's cache lines and the loader only the answer's, so neither ever
 * overwrites the other's. The data buffer is mapped cacheable, because copying
 * out of an uncached mapping costs more than the read itself.
 *
 * The protocol, in the order it happens:
 *
 *   1. read magic/version/size/parts. A page that is not one this kernel knows
 *      is refused once and nothing more is asked of the loader.
 *   2. the parts table says, per partition: name, block_size, blocks,
 *      start_lba, unit, lun. A whole logical unit carries BLOCK_PART_UNIT.
 *   3. to read: fill ask.part / ask.lba / ask.count / ask.op, barrier, then
 *      ask.request = ++seq. The loader answers by setting answer.answered = seq
 *      and answer.status. The kernel never writes answer, the loader never
 *      writes ask.
 *   4. the data lands in the loader's buffer at buffer_pa, which this side then
 *      invalidates and copies out.
 *
 * A request that is not answered within HAYDN_UFS_TIMEOUT_MS marks the storage
 * dead: after that nothing more is asked of a loader that is gone or stuck.
 */

#define HAYDN_UFS_PAGE         0x4000u
#define HAYDN_UFS_TIMEOUT_MS   20000u

/* What the page says, copied out once so the driver does not depend on the map. */
struct haydn_ufs_inventory {
	uint32_t parts;
	uint32_t buffer_size;
	uint64_t buffer_pa;
	uint32_t write_part_plus_one;   /* 0: this loader takes no writes */
	uint64_t write_first;
};

/*
 * Map and validate the page. Returns 0 when it is one this kernel knows and the
 * inventory was copied out; otherwise the reason, in the log, once.
 */
int haydn_ufs_attach(void);

/* The inventory, once attached. */
const struct haydn_ufs_inventory *haydn_ufs_inventory(void);

/*
 * Ask the loader for blocks [lba, lba+count) of partition part, into dst.
 * Returns 0, or EIO after saying why once.
 */
int haydn_ufs_read(uint32_t part, uint64_t lba, uint64_t count, void *dst);

/* True once a request went unanswered and the storage was given up on. */
bool haydn_ufs_dead(void);

#endif /* HAYDN_UFS_H */
