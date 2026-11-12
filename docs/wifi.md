# Wi-Fi: QCA6490 over PCIe + MHI

This board's radio is the piece with no working precedent anywhere in the
catalog. This page records what it is, what the nearest existing code does,
and what has to be written.

## The part

The device tree names the node `qcom,cnss-qca6490@b0000000`; the vendor config
directory is `/vendor/etc/wifi/qca6750/`. Both names are the WCN6855 family.
Its Linux driver is **ath11k**.

Two transports exist inside ath11k and they are not interchangeable:

| Transport | Files | Chips | How it reaches the chip |
| --- | --- | --- | --- |
| AHB / SNOC | `ahb.c` | WCN6750, WCN6855 on some designs | The application processor maps the radio's window registers directly. `ath11k_ahb_get_window_start_wcn6750()` picks one of three fixed windows. |
| PCIe / MHI | `pci.c`, `mhi.c` | QCA6390, QCA6490, WCN6855 | A PCIe function and a Modem Host Interface ring set carry the firmware and every WMI message. |

haydn is the second row: the radio sits behind `pcie@1c00000`, the platform
listing shows `0000:01:00.0`, and the device tree carries MHI parameters
(30 channels, 10000 ms, 32768-byte buffers, `mhi,m2-no-db-access`).

## What can be borrowed, and what cannot

HakiOS's Wi-Fi stack (`oosexgang/hakios-xnu-kernel`, `drivers/wifi/`, 4100
lines of `hakios.wifi.c` plus six more files) is the nearest prior art. It is
split cleanly enough to say exactly where the seam is.

### Reusable unchanged

| Piece | File | Why it transfers |
| --- | --- | --- |
| LinuxKPI bridge | `wifi/lx/` + `tools/mk-ath11k.sh` | Compiles unmodified ath11k sources against Linux interfaces XNU does not have. Nothing in it depends on the transport. |
| QMI / WLFW exchange | `hakios.wlfw.c` | The service handshake with the radio firmware: indications, capabilities both ways, the regulatory database, the board data file. Pure datagrams above the transport. |
| QMI over QRTR | `hakios.qmi.c`, `hakios.qrtr.c` | The IPC router path. SM8350 has QRTR (`soc:qrtr-haven`) at the same place. |
| Apple80211 surface | `hakios.apple80211.c` | What Darwin's `wifid` talks to. Independent of how bytes reach the radio. |

### Must be written

| Piece | Why |
| --- | --- |
| PCIe enumeration and window setup | `pcie@1c00000` needs its parf/phy/dm_core/elbi/iatu/conf windows mapped, its GDSC voted, and its reset released. No XNU code does this for an SM8350. |
| MHI ring set | 30 channels, 32768-byte buffers. `mhi_pci_probe` in Linux is the sequence to follow: `mhi_init`, `mhi_prepare_for_power_up`, `mhi_sync_power_up`, then the channel callbacks. |
| LinuxKPI additions | `pci_alloc_irq_vectors`, `pci_enable_device`, `pci_set_master`, `dma_map_single` / `dma_map_page`, and the MSI plumbing under them. XNU's IOKit has analogues; the names do not. |
| BDF assembly | 147 `bdwlan.eXX` segments of 59,868 bytes have to be joined in order. HakiOS handles 10 for a different chip; the count and the order are this board's. |

## The numbers this board needs

All from `docs/hardware.md`, which cites the device tree line for each.

```
PCIe
  parf      0x1c00000 + 0x3000
  phy       0x1c06000 + 0x2000
  dm_core   0x60000000 + 0xf1d
  elbi      0x60000f20 + 0xa8
  iatu      0x60001000 + 0x1000
  conf      0x60100000 + 0x100000
  ranges    IO 0x60200000 + 0x100000; MEM 0x60300000 + 0x3d00000
  perst     GPIO 94        wake   GPIO 96
  smmu-sid-base  0x1c00    iommu-map 0x00->0x1c00, 0x100->0x1c01
  tbu       0x151a1000

cnss (the radio)
  compatible      qcom,cnss-qca6490
  smmu iova ipa   0xb0000000 + 0x10000
  tcs cmd         0xb2e5510 + 0x690
  wlan-en GPIO 64  bt-en GPIO 65  sw-ctrl GPIO 153
  mhi max-channels 30   timeout 10000   buffer-len 32768   m2-no-db-access
```

## Staging

This is P7 in the plan and it cannot start before P1: a kernel that cannot
mount its root will not run a network stack either. The order inside P7:

1. **PCIe enumeration only.** Map the six windows, release the reset, and read
   the function's config space to confirm vendor `0x17cb`, device `0x1103`.
   Stop there and log.
2. **MHI rings.** Bring the MHI host up and confirm the device reports its
   channels. Still no firmware, still no network.
3. **Firmware load.** Assemble the BDF, hand `amss.bin` / `bdwlan` / `regdb`
   through MHI, and wait for the chip's ready indication.
4. **WMI.** Speak the WLFW service. HakiOS's `wlfw.c` is the reference for
   every message.
5. **Apple80211.** Only now does `wifid` see an interface at all.

Each step has its own log line that says which one failed.

## Why it is worth doing anyway

The transport above the MHI rings is generic ath11k, and the LinuxKPI bridge
already compiles it. What is missing is the PCIe half underneath. That is a
bounded amount of code, all of it traceable to Linux's `drivers/net/wireless/
ath/ath11k/pci.c` and `drivers/bus/mhi/`, and all of it testable without
Apple's user space: enumerate the bus and print the device's identity, then
the rings, then one message.
