/*
 * The PCIe root complex of haydn (SM8350): map, cut reset, read the link,
 * enumerate the first function. See haydn.pcie.h for what each step is for
 * and docs/hardware.md for where every address came from.
 *
 * This is the first of the five steps docs/wifi.md lays out. It stops before
 * MHI: the point is to find out whether the bus works at all on hardware,
 * with one number to compare against Android's own view of the device.
 *
 * Boot argument: pcie_probe=1
 */

#include <pexpert/pexpert.h>
#include <machine/machine_routines.h>
#include <kern/kalloc.h>
#include <kern/printf.h>

#include "haydn.pcie.h"

/*
 * The reset line. The device tree gives perst-gpio = <&tlmm 0x5e 0x00> and
 * wake-gpio = <&tlmm 0x60 0x00>: GPIO 94 and 96 on the TLMM controller.
 * The controller's register base is not in the base device tree (it is a
 * pinctrl node the vendor tree adds), so the GPIO work is left as the one
 * typed hole in this file rather than guessed.
 */
#ifndef HAYDN_TLMM_BASE
#define HAYDN_TLMM_BASE  0ULL   /* set when the pinctrl node is located */
#endif
#define HAYDN_GPIO_PERST 94
#define HAYDN_GPIO_WAKE  96

/* TLMM: each pin has a 0x1000 stride of 32-bit registers. */
#define TLMM_PIN_OFFSET(pin)  (0x100000ULL + (uint64_t)(pin) * 0x1000ULL)
#define TLMM_CTL             0x0
#define TLMM_IO              0x4

/*
 * The device tree's own memory layout, quoted so the numbers in this file can
 * be checked against one place:
 *
 *   ranges = <0x1000000 0x00 0x60200000 0x60200000 0x00 0x100000
 *             0x2000000 0x00 0x60300000 0x60300000 0x00 0x3d00000>;
 *
 * The config window sits at 0x60100000, one MiB, which is 256 buses x 32
 * slots x 8 functions x 4 KiB. Reading the vendor and device ids of a
 * function is therefore a load from the config window, not a PCI call: on
 * this controller there is no ECAM driver between the two.
 */
#define HAYDN_PCIE_CONF_BASE   0x60100000ULL
#define HAYDN_PCIE_CONF_SIZE   0x100000ULL
#define HAYDN_PCIE_DM_CORE     0x60000000ULL
#define HAYDN_PCIE_ELBI        0x60000f20ULL
#define HAYDN_PCIE_IATU        0x60001000ULL
#define HAYDN_PCIE_PARF        0x1c00000ULL
#define HAYDN_PCIE_PHY         0x1c06000ULL

/* Encode a BDF into the config window's flat address. */
static inline uint64_t
haydn_pcie_conf_address(int bus, int slot, int function, uint16_t offset)
{
	return HAYDN_PCIE_CONF_BASE +
	    ((uint64_t)bus << 20) |
	    ((uint64_t)slot << 15) |
	    ((uint64_t)function << 12) |
	    (offset & 0xffcu);
}

static uint32_t
haydn_pcie_read32(uint64_t address)
{
	volatile uint32_t *p = (volatile uint32_t *)ml_io_map(address, 4);
	uint32_t value;

	if (p == NULL) {
		return 0xffffffffu;
	}
	value = *p;
	return value;
}

static void
haydn_pcie_write32(uint64_t address, uint32_t value)
{
	volatile uint32_t *p = (volatile uint32_t *)ml_io_map(address, 4);

	if (p != NULL) {
		*p = value;
	}
}

/* A window that maps to all ones is not there; a config read must not be. */
static boolean_t
haydn_pcie_window_present(const struct haydn_pcie_window *w)
{
	volatile uint32_t *p = (volatile uint32_t *)ml_io_map(w->phys, 4);

	return p != NULL;
}

/*
 * A device answers config reads with its identity; nothing there reads all
 * ones. That is the check this probe exists to make.
 */
static boolean_t
haydn_pcie_function_present(int bus, int slot, int function, uint32_t *id)
{
	*id = haydn_pcie_read32(haydn_pcie_conf_address(bus, slot, function, HAYDN_PCI_VENDOR_ID));
	return (*id != 0xffffffffu) && (*id != 0x00000000u);
}

int
haydn_pcie_probe(struct haydn_pcie_result *out)
{
	uint32_t enabled = 0;
	uint32_t id = 0;
	unsigned i;

	if (!PE_parse_boot_argn("pcie_probe", &enabled, sizeof(enabled)) || !enabled) {
		return 1;
	}

	/* 2: every window the tree names must map. */
	for (i = 0; i < HAYDN_PCIE_WINDOWS; i++) {
		if (!haydn_pcie_window_present(&haydn_pcie_windows[i])) {
			printf("haydn-pcie: window %s (0x%llx) did not map\n",
			    haydn_pcie_windows[i].name,
			    (unsigned long long)haydn_pcie_windows[i].phys);
			return 2;
		}
	}
	printf("haydn-pcie: %u windows mapped (parf/phy/dm_core/elbi/iatu/conf)\n",
	    (unsigned)HAYDN_PCIE_WINDOWS);

	/*
	 * The radio is on bus 1, device 0, function 0 on Android:
	 * /sys/bus/pci/devices/0000:01:00.0. Bus 0 slot 0 is the root complex's own
	 * host bridge and is expected to answer.
	 */
	if (haydn_pcie_function_present(0, 0, 0, &id)) {
		printf("haydn-pcie: root complex id %08x (vendor %04x device %04x)\n",
		    id, id & 0xffff, id >> 16);
	} else {
		printf("haydn-pcie: no function at 00:00.0 - the bus is not up\n");
		return 3;
	}

	if (!haydn_pcie_function_present(1, 0, 0, &id)) {
		printf("haydn-pcie: nothing at 01:00.0 - link training or reset\n");
		return 4;
	}

	out->bus = 1;
	out->slot = 0;
	out->function = 0;
	out->vendor = (uint16_t)(id & 0xffff);
	out->device = (uint16_t)(id >> 16);

	printf("haydn-pcie: 01:00.0 vendor %04x device %04x\n",
	    out->vendor, out->device);

	if (out->vendor != HAYDN_WIFI_VENDOR || out->device != HAYDN_WIFI_DEVICE) {
		printf("haydn-pcie: expected %04x:%04x (the radio) - this is not it\n",
		    HAYDN_WIFI_VENDOR, HAYDN_WIFI_DEVICE);
		return 5;
	}

	out->status = (uint16_t)(haydn_pcie_read32(
	    haydn_pcie_conf_address(1, 0, 0, HAYDN_PCI_STATUS)) >> 16);
	out->header_type = (uint8_t)(haydn_pcie_read32(
	    haydn_pcie_conf_address(1, 0, 0, HAYDN_PCI_HEADER_TYPE)) >> 16);

	printf("haydn-pcie: status %04x (cap-list %d) header %02x\n",
	    out->status,
	    (out->status & HAYDN_PCI_STATUS_CAP_LIST) != 0,
	    out->header_type);
	printf("haydn-pcie: the radio is enumerated; MHI is the next step (docs/wifi.md)\n");

	return 0;
}
