/*
 * The storage of haydn: the UFS host controller at 0x1d84000, read only.
 * See haydn.ufs.h for what is this board's and what is every controller's.
 *
 * The structure follows HakiOS's hakios.ufshc.c, which drives an SM7325
 * controller the same way: the register block is the UFSHCI standard, so the
 * probing code transfers; what does not transfer is the memory the loader
 * offers and the PHY's address, both of which are this board's.
 *
 * This file is the second of the two storage paths (the loader's page is the
 * first). It stops at "the controller answered and said what it is": no list
 * is put in, no command is issued, nothing is read from the flash. That is the
 * checkpoint that decides whether the addresses in docs/hardware.md are right,
 * and it costs nothing to reach.
 *
 * Boot argument: ufs_probe=1
 */

#include <pexpert/pexpert.h>
#include <machine/machine_routines.h>
#include <kern/clock.h>
#include <kern/printf.h>
#include <libkern/libkern.h>
#include <sys/errno.h>
#include <mach/vm_param.h>

#include "haydn.ufs.h"

/*
 * XNU does not declare these three in a header a kext can reach; every port
 * that maps a device register declares them itself, with the same signatures.
 */
extern vm_offset_t ml_io_map(vm_offset_t phys_addr, vm_size_t size);
extern vm_offset_t ml_io_map_unmappable(vm_offset_t phys_addr, vm_size_t size, unsigned int flags);
extern void FlushPoC_DcacheRegion(vm_offset_t va, size_t length);
extern void IOSleep(unsigned int milliseconds);

/*
 * The whitelist. Every command this driver issues goes through it before it is
 * written into a slot, and what the slot then holds is read back and checked
 * again before the doorbell rings.
 *
 * Three things are checked, the way HakiOS's ufshc_permitted() checks them:
 * the SCSI operation, the data direction, and the unit. A command that says
 * write, carries the UPIU write flag, or addresses a well-known logical unit
 * is refused here rather than caught later.
 */
bool
haydn_ufs_permitted(const struct haydn_ufs_command *cmd)
{
	if (cmd == NULL) {
		return FALSE;
	}

	/* Never a write: not the UPIU's flag, not the descriptor's direction. */
	if (cmd->upiu_flags & UPIU_FLAG_WRITE) {
		return FALSE;
	}
	if (cmd->direction == UTRD_DD_OUT >> 25) {
		return FALSE;
	}

	/* Never a well-known unit (REPORT LUNS, BOOT, RPMB, the device). */
	if (cmd->lun & LUN_WELL_KNOWN) {
		return FALSE;
	}

	/* Only the operations this driver builds, and nothing else. */
	switch (cmd->opcode) {
	case SCSI_READ10:
	case SCSI_READ16:
		/* A read must say so and must be a transfer from the device. */
		return (cmd->upiu_flags & UPIU_FLAG_READ) != 0 &&
		    cmd->direction == (UTRD_DD_IN >> 25);
	case SCSI_TEST_UNIT_READY:
	case SCSI_REQUEST_SENSE:
	case SCSI_INQUIRY:
	case SCSI_READ_CAPACITY10:
	case SCSI_READ_CAPACITY16:
		/* No data, or a transfer from the device; never to it. */
		return cmd->direction != (UTRD_DD_OUT >> 25);
	default:
		return FALSE;
	}
}

/*
 * READ(10) for 4096-byte blocks. The CDB's length field is in blocks and the
 * controller compares it against the UPIU's expected transfer length, so both
 * are built from the same argument.
 */
void
haydn_ufs_build_read10(uint8_t cdb[16], uint64_t lba, uint32_t blocks)
{
	int i;

	for (i = 0; i < 16; i++) {
		cdb[i] = 0;
	}
	cdb[0] = SCSI_READ10;
	/* LBA in bytes 2..5, big endian: READ(10) carries 32 bits of it. */
	cdb[2] = (uint8_t)(lba >> 24);
	cdb[3] = (uint8_t)(lba >> 16);
	cdb[4] = (uint8_t)(lba >> 8);
	cdb[5] = (uint8_t)(lba);
	/* Transfer length in bytes 7..8, big endian, in blocks. */
	cdb[7] = (uint8_t)(blocks >> 8);
	cdb[8] = (uint8_t)(blocks);
}

void
haydn_ufs_build_read_capacity10(uint8_t cdb[16])
{
	int i;

	for (i = 0; i < 16; i++) {
		cdb[i] = 0;
	}
	cdb[0] = SCSI_READ_CAPACITY10;
}

static uint32_t
haydn_ufs_read32(vm_offset_t hc, uint32_t offset)
{
	return *(volatile uint32_t *)(hc + offset);
}

/*
 * Probe: map the register block and say what the controller reports about
 * itself. This is where a wrong address shows up first, and where a PHY that
 * was never brought up shows as a controller that is present but not ready.
 *
 * Error codes, so a log line names the step:
 *
 *   1  no ufs_probe=1
 *   2  the register block did not map
 *   3  HCS does not report the controller present
 *   4  HCS reports it present but the request list is not ready
 *   5  the version register reads as nothing (all ones or zero)
 */
int
haydn_ufs_probe(void)
{
	uint32_t enabled = 0;
	vm_offset_t hc;
	uint32_t cap, ver, hcs;
	uint32_t nutrs;

	if (!PE_parse_boot_argn("ufs_probe", &enabled, sizeof(enabled)) || !enabled) {
		return 1;
	}

	hc = ml_io_map(HAYDN_UFSHC_PHYS, HAYDN_UFSHC_SIZE);
	if (hc == 0) {
		printf("haydn-ufs: 0x%llx did not map\n",
		    (unsigned long long)HAYDN_UFSHC_PHYS);
		return 2;
	}

	cap = haydn_ufs_read32(hc, UFSHC_CAP);
	ver = haydn_ufs_read32(hc, UFSHC_VER);
	hcs = haydn_ufs_read32(hc, UFSHC_HCS);

	printf("haydn-ufs: cap %08x ver %08x hcs %08x\n", cap, ver, hcs);

	if ((hcs & HCS_DP) == 0) {
		printf("haydn-ufs: the controller does not report itself present\n");
		return 3;
	}

	if (ver == 0xffffffffu || ver == 0) {
		printf("haydn-ufs: version reads %08x - the block is not there\n", ver);
		return 5;
	}

	nutrs = CAP_NUTRS(cap);
	printf("haydn-ufs: UFSHCI %u.%u, %u request slots, 64-bit lists %s\n",
	    (ver >> 8) & 0xff, ver & 0xff, nutrs,
	    (cap & CAP_64AS) ? "yes" : "no");

	if ((hcs & HCS_UTRLRDY) == 0) {
		printf("haydn-ufs: present, but the request list is not ready "
		    "(the PHY at 0x%llx is not up?)\n",
		    (unsigned long long)HAYDN_UFS_PHY_PHYS);
		return 4;
	}

	printf("haydn-ufs: present and ready - PHY 0x%llx + 0x%x\n",
	    (unsigned long long)HAYDN_UFS_PHY_PHYS, HAYDN_UFS_PHY_SIZE);

	return 0;
}

/* ---- Talking to the loader ------------------------------------------------ */

static volatile struct haydn_ufs_page *haydn_ufs_the_page;
static uint8_t *haydn_ufs_the_buffer;
static struct haydn_ufs_inventory haydn_ufs_inv;
static bool haydn_ufs_is_dead;
static uint32_t haydn_ufs_seq;
static uint64_t haydn_ufs_requests, haydn_ufs_errors, haydn_ufs_bytes;

static void
haydn_ufs_barrier(void)
{
	__asm__ volatile ("dmb sy" ::: "memory");
}

int
haydn_ufs_attach(void)
{
	uint64_t pa = 0;
	vm_offset_t base;

	if (!PE_parse_boot_argn("ufs_shared_pa", &pa, sizeof(pa)) || pa == 0) {
		printf("haydn-ufs: no ufs_shared_pa= - the loader was not asked for storage\n");
		return 1;
	}

	/*
	 * Map the page uncached and then the buffer cacheable. Copying out of an
	 * uncached mapping costs more than the read itself; HakiOS measured 870 MB/s
	 * on the uncached path against the storage's own throughput.
	 */
	base = ml_io_map_unmappable((vm_offset_t)(pa & ~(uint64_t)(HAYDN_UFS_PAGE - 1)),
	    (uint32_t)(((pa & (HAYDN_UFS_PAGE - 1)) + sizeof(struct haydn_ufs_page) +
	    HAYDN_UFS_PAGE - 1) & ~(uint64_t)(HAYDN_UFS_PAGE - 1)),
	    VM_WIMG_WCOMB);
	if (base == 0) {
		printf("haydn-ufs: the loader's page at 0x%llx did not map\n",
		    (unsigned long long)pa);
		return 2;
	}
	haydn_ufs_the_page = (volatile struct haydn_ufs_page *)(base + (pa & (HAYDN_UFS_PAGE - 1)));

	/* Step 1: is this a page this kernel knows? */
	if (haydn_ufs_the_page->magic != BLOCK_MAGIC ||
	    haydn_ufs_the_page->version != BLOCK_VERSION ||
	    haydn_ufs_the_page->size != sizeof(struct haydn_ufs_page) ||
	    haydn_ufs_the_page->parts > BLOCK_MAX_PARTS) {
		printf("haydn-ufs: the page at 0x%llx is not one this kernel knows "
		    "(magic %llx, version %u, size %u)\n",
		    (unsigned long long)pa,
		    (unsigned long long)haydn_ufs_the_page->magic,
		    haydn_ufs_the_page->version,
		    haydn_ufs_the_page->size);
		haydn_ufs_the_page = NULL;
		return 3;
	}

	/* Step 2: the inventory, copied out so the driver does not read the page for it. */
	haydn_ufs_inv.parts = haydn_ufs_the_page->parts;
	haydn_ufs_inv.buffer_size = haydn_ufs_the_page->buffer_size;
	haydn_ufs_inv.buffer_pa = haydn_ufs_the_page->buffer_pa;
	haydn_ufs_inv.write_part_plus_one = haydn_ufs_the_page->write_part_plus_one;
	haydn_ufs_inv.write_first = haydn_ufs_the_page->write_first;

	if (haydn_ufs_inv.buffer_size == 0) {
		printf("haydn-ufs: the page offers no data buffer\n");
		haydn_ufs_the_page = NULL;
		return 4;
	}

	/* The buffer, cacheable. */
	{
		uint64_t bpa = haydn_ufs_inv.buffer_pa;
		vm_offset_t bb = ml_io_map_unmappable(
		    (vm_offset_t)(bpa & ~(uint64_t)(HAYDN_UFS_PAGE - 1)),
		    ((bpa & (HAYDN_UFS_PAGE - 1)) + haydn_ufs_inv.buffer_size +
		    HAYDN_UFS_PAGE - 1) & ~(uint64_t)(HAYDN_UFS_PAGE - 1),
		    VM_WIMG_DEFAULT);

		if (bb == 0) {
			printf("haydn-ufs: the data buffer at 0x%llx did not map\n",
			    (unsigned long long)bpa);
			haydn_ufs_the_page = NULL;
			return 5;
		}
		haydn_ufs_the_buffer = (uint8_t *)(bb + (bpa & (HAYDN_UFS_PAGE - 1)));
	}

	/* A loader that served an earlier kernel counts on from where it was. */
	haydn_ufs_seq = haydn_ufs_the_page->answer.answered;

	printf("haydn-ufs: %u partitions through the loader's page at 0x%llx, "
	    "%u KB buffer\n",
	    haydn_ufs_inv.parts, (unsigned long long)pa,
	    haydn_ufs_inv.buffer_size >> 10);

	return 0;
}

const struct haydn_ufs_inventory *
haydn_ufs_inventory(void)
{
	return haydn_ufs_the_page != NULL ? &haydn_ufs_inv : NULL;
}

bool
haydn_ufs_dead(void)
{
	return haydn_ufs_is_dead;
}

/*
 * Ask, then wait. The loop looks often at first (an answer to a small request
 * comes in tens of microseconds) and then sleeps a millisecond at a time; a
 * request that goes unanswered past the timeout marks the storage dead rather
 * than hanging the kernel on a loader that is gone.
 */
int
haydn_ufs_read(uint32_t part, uint64_t lba, uint64_t count, void *dst)
{
	uint64_t bytes, started, waited_ms = 0;
	uint32_t seq;
	int64_t status;

	if (haydn_ufs_the_page == NULL || haydn_ufs_is_dead) {
		return EIO;
	}
	if (part >= haydn_ufs_inv.parts || dst == NULL) {
		return EINVAL;
	}

	bytes = count * HAYDN_UFS_BLOCK;
	if (bytes == 0 || bytes > haydn_ufs_inv.buffer_size) {
		return EINVAL;
	}

	seq = ++haydn_ufs_seq;
	haydn_ufs_the_page->ask.part = part;
	haydn_ufs_the_page->ask.lba = lba;
	haydn_ufs_the_page->ask.count = count;
	haydn_ufs_the_page->ask.op = BLOCK_OP_READ;
	haydn_ufs_barrier();
	haydn_ufs_the_page->ask.request = seq;
	haydn_ufs_barrier();

	started = mach_absolute_time();
	while (haydn_ufs_the_page->answer.answered != seq) {
		uint64_t us;

		absolutetime_to_nanoseconds(mach_absolute_time() - started, &us);
		if (us / 1000 < 2000) {
			__builtin_arm_yield();
			continue;
		}
		IOSleep(1);
		if (++waited_ms > HAYDN_UFS_TIMEOUT_MS) {
			printf("haydn-ufs: no answer to request %u in %u s - the storage is off "
			    "from now on\n", seq, HAYDN_UFS_TIMEOUT_MS / 1000);
			haydn_ufs_is_dead = true;
			haydn_ufs_errors++;
			return EIO;
		}
	}
	haydn_ufs_barrier();

	status = haydn_ufs_the_page->answer.status;
	if (status != 0) {
		printf("haydn-ufs: partition %u blocks %llu..%llu: the loader answered %lld\n",
		    part, (unsigned long long)lba,
		    (unsigned long long)(lba + count - 1), (long long)status);
		haydn_ufs_errors++;
		return EIO;
	}

	/* The buffer holds it now; this side's lines of it go before the copy out. */
	FlushPoC_DcacheRegion((vm_offset_t)haydn_ufs_the_buffer, (size_t)bytes);
	memcpy(dst, haydn_ufs_the_buffer, (size_t)bytes);

	haydn_ufs_requests++;
	haydn_ufs_bytes += bytes;

	return 0;
}
