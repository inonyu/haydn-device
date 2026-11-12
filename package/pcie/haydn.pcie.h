/*
 * The PCIe root complex of haydn (SM8350): the bus the Wi-Fi radio sits on.
 *
 * Nothing here allocates, starts a device, or talks to the radio. It maps the
 * six windows the device tree gives this controller, cuts its reset, reads the
 * link status, and enumerates the first function it finds so that the result
 * can be compared with what Android reports:
 *
 *     /sys/bus/pci/devices/0000:01:00.0  ->  vendor 0x17cb device 0x1103
 *
 * If that identity does not come back, the windows, the reset, the clock votes
 * or the PHY are wrong, and there is no point writing an MHI layer above it.
 *
 * Every address below is from the phone's own device tree
 * (qcom,pcie@1c00000, see docs/hardware.md); nothing is from a sibling board.
 *
 * Boot argument: pcie_probe=1. Without it nothing is touched.
 */
#ifndef HAYDN_PCIE_H
#define HAYDN_PCIE_H

#include <sys/types.h>

/* The six windows the device tree names, with the names it gives them. */
struct haydn_pcie_window {
	const char *name;
	uint64_t    phys;
	uint32_t    size;
};

/*
 * reg = <0x1c00000 0x3000 0x1c06000 0x2000 0x60000000 0xf1d
 *        0x60000f20 0xa8 0x60001000 0x1000 0x60100000 0x100000>;
 * reg-names = "parf", "phy", "dm_core", "elbi", "iatu", "conf";
 */
static const struct haydn_pcie_window haydn_pcie_windows[] = {
	{ "parf",    0x0000000001c00000ULL, 0x3000     },
	{ "phy",     0x0000000001c06000ULL, 0x2000     },
	{ "dm_core", 0x0000000060000000ULL, 0xf1d      },
	{ "elbi",    0x0000000060000f20ULL, 0xa8       },
	{ "iatu",    0x0000000060001000ULL, 0x1000     },
	{ "conf",    0x0000000060100000ULL, 0x100000   },
};

#define HAYDN_PCIE_WINDOWS  (sizeof(haydn_pcie_windows) / sizeof(haydn_pcie_windows[0]))

/* The radio's own identity, as Android reports it. */
#define HAYDN_WIFI_VENDOR   0x17cb
#define HAYDN_WIFI_DEVICE   0x1103

/* Where in the config window the standard header lives. */
#define HAYDN_PCI_VENDOR_ID     0x00
#define HAYDN_PCI_DEVICE_ID     0x02
#define HAYDN_PCI_COMMAND       0x04
#define HAYDN_PCI_STATUS        0x06
#define HAYDN_PCI_CLASS_REV     0x08
#define HAYDN_PCI_HEADER_TYPE   0x0e

/* Status bits worth reporting before anything is written. */
#define HAYDN_PCI_STATUS_CAP_LIST   0x0010
#define HAYDN_PCI_STATUS_LINK_66MHZ 0x0020

/*
 * What the probe found. Zero on success; anything else is the step that
 * stopped, numbered so a log line says which one without prose:
 *
 *   1  no boot argument
 *   2  a window could not be mapped
 *   3  the config window reads all ones (the bus is not there)
 *   4  a function answered, but it is not the radio
 *   5  the radio answered, but its header is not a normal endpoint
 */
struct haydn_pcie_result {
	uint16_t vendor;
	uint16_t device;
	uint16_t status;
	uint8_t  class_rev[4];
	uint8_t  header_type;
	int     bus;
	int     slot;
	int     function;
};

/* Run the probe if pcie_probe=1. Returns 0 when the radio answered. */
int haydn_pcie_probe(struct haydn_pcie_result *out);

#endif /* HAYDN_PCIE_H */
