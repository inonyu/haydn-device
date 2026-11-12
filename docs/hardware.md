# haydn hardware record

Every line here was read from the phone itself on 2026-11-12. The sources are
named per row so a reader can check them:

- **fdt** — `/sys/firmware/fdt`, 799,754 bytes, pulled with root and kept as
  `firmware/ALL/meta/haydn-fdt.dtb`; decompiled to `haydn-fdt.dts` (33,702 lines).
- **live** — `/sys/bus/platform/devices` and `/sys/bus/pci/devices` on the
  running phone.
- **prop** — `getprop` on the running phone.
- **dd** — a direct read of the partition.

## Identity

| Item | Value | Source |
| --- | --- | --- |
| Model | Redmi K40 Pro / `M2012K11C` | prop `ro.product.model` |
| Codename | `haydn` | prop `ro.product.device` |
| SoC | SM8350 (lahaina), Snapdragon 888 | prop `ro.soc.model` |
| Android | 13, MIUI V14.0.5.0.TKKCNXM | prop `ro.build.version.release` |
| Kernel | `5.4.147-qgki-gc59a695f9a4d` | `uname -a` |
| Boot loader | unlocked — `verifiedbootstate=orange`, `flash.locked=0` | prop `ro.boot.*` |
| RAM | 7,471,256 kB (~8 GB, 7.47 GiB usable) | `/proc/meminfo` |

## CPU

| Cluster | Cores | Max clock |
| --- | --- | --- |
| E (A55) | 4, MPIDR 0x000/0x100/0x200/0x300 | 1,804,800 kHz |
| P (A78) | 3, MPIDR 0x400/0x500/0x600 | 2,419,200 kHz |
| Prime (X1) | 1, MPIDR 0x700 | 2,841,600 kHz |

`Features:` from `/proc/cpuinfo` has **no `apa`/`api`/`pac`**: this SoC has no
pointer authentication, so the arm64e OS profiles (iPadOS 26 and 27) cannot
run here. The arm64 profile `ipados-17.7.11-21H461` is the one this board uses.

`qcom,cpufreq-hw-epss` at `0x18591000`, `0x18592000`, `0x18593000` (three freq
domains), SPI 0x1e / 0x1f / 0x13. — fdt

## GPU — Adreno 660v2

| Block | Address | Size | Source |
| --- | --- | --- | --- |
| 3D core | `0x3d00000` | `0x40000` | fdt `qcom,kgsl-3d0@3d00000` |
| CX DBGC | `0x3d61000` | `0x800` | fdt |
| RSCC | `0x3de0000` | `0x10000` | fdt |
| ISENSE | `0x3d8b000` | `0x2000` | fdt |
| QDSS GFX | `0x6900000` | `0x80000` | fdt |
| RDPM CX / MX | `0x634000` / `0x636000` | `0x1000` | fdt |
| GMU | `0x3d6a000` | `0x34000` | fdt + live |
| GMU PDC | `0xb290000` | `0x10000` | fdt |
| GPUCC | `0x3d90000` | `0x9000` | fdt + live |
| KGSL SMMU | `0x3da0000` | `0x20000` | fdt + live |
| SMMU TBU 0 | `0x3dc5000` | — | fdt `gfx_0_tbu` |
| SMMU TBU 1 | `0x3dc9000` | — | fdt `gfx_1_tbu` |

- `qcom,chipid = <0x06060001>` — the A660 id, not the 642L's.
- `qcom,ubwc-mode = <4>`, `highest-bank-bit = <0x10>`, `min-access-length = <0x20>`.
- Interrupts: GPU `SPI 0x12c`, HFI `0x130`, GMU `0x131`.
- SMMU contexts: `gfx3d_user`, `gfx3d_lpac`, `gfx3d_secure`.
- Thermal zones the vendor names for it: `gpuss-0-usr`, `gpuss-1-usr`.

### Frequency levels — measured, not from the tree

**The phone is the authority here, not the device tree.** Reading the running
handset settles a question the tree leaves open:

    /sys/class/kgsl/kgsl-3d0/gpu_available_frequencies
    840 778 738 676 608 540 491 443 379 315        (MHz)

Read three times on 2026-11-12, identical each time. The handset was at 315 MHz
when read (its idle level); its design maximum is 840.

The tree carries two `qcom,gpu-pwrlevel` tables — the vendor's DDR7 and DDR8
options — and neither is this handset's:

| Table | Levels (MHz) | Not on this phone |
| --- | --- | --- |
| DDR7 | 855, 818, 738, 676, 540, 443, 350 | 855, 818, 350 |
| DDR8 | 900, 840, 778, 738, 676, 540, 491, 443, 379, 315 | 900 |

And the phone has one level neither table has: **608 MHz**.

So a driver that chooses a table from the device tree chooses wrong. The
measured ten are what `package/gpu/haydn.gpu.h` carries.

The Adreno 642L of an SC7280 tops out at 550 MHz. This board reaches 840, so
HakiOS's `adreno_speed` table (1: 315, 2: 450, 3: 550) does not apply.

### Why the 642L driver is still the right starting point

`gpucc = 0x03d90000`, `gmu = 0x03d6a000` and `smmu = 0x03da0000` in HakiOS's
`hakios.adreno.c` are the same three addresses this board reports. Those are
the delivery units, the GPU's own clock controller and its SMMU: the register
offsets that driver walks are offsets within those blocks, so the block-level
code transfers unchanged. What does not transfer is anything keyed to the
chip: the speed table above, the fuse offsets, and the CX/GX GDSC layout.

## Storage

| Block | Address | Size | Source |
| --- | --- | --- | --- |
| UFS host | `0x1d84000` | `0x3000` | fdt `ufshc@1d84000` |
| UFS ICE | `0x1d88000` | `0x8000` | fdt |
| UFS ICE HWKM | `0x1d90000` | `0x9000` | fdt |
| **UFS PHY** | **`0x1d87000`** | **`0xe10`** | fdt + live `1d87000.ufsphy_mem` |

- `compatible = "qcom,ufs-phy-qmp-v4-lahaina"`, two lanes per direction.
- Interrupt: `SPI 0x109`.

> **This is a correction.** The earlier haydn porting record carried
> `UFS PHY = 0x1d80000`, which is not this board's PHY. Bring-up against that
> address watches the wrong registers and stalls at the first step. The live
> tree and the live platform listing both say `0x1d87000`.

### userdata geometry (dd + blockdev)

| Field | Value |
| --- | --- |
| Device | `/dev/block/sda34` |
| Bytes | 241,906,462,720 (225.3 GiB) |
| 512-byte sectors | 472,473,560 |
| 4096-byte LBA | 59,059,195 |
| First / last LBA (4K) | 2,785,280 / 61,844,474 |

`last - first + 1 = 59,059,195`, which matches the byte count exactly. The
earlier porting record's numbers were right; only its PHY address was wrong.

## Display

| Block | Address | Size | Source |
| --- | --- | --- | --- |
| MDP | `0xae00000` | `0x84000` | fdt `qcom,mdss_mdp@ae00000` |
| VBIF | `0xaeb0000` | `0x2008` | fdt |
| REGDMA | `0xaeac000` | `0x800` | fdt |
| DSI0 ctrl | `0xae94000` | — | fdt |
| DSI0 PHY | `0xae94400` | — | fdt |
| DSI1 ctrl | `0xae96000` | — | fdt |
| DSI1 PHY | `0xae96400` | — | fdt |

- Interrupt: `SPI 0x53`. Six CTLs (`0x16000`..`0x1b000`), six mixers
  (`0x45000`..`0x4a000`), four DSPPs (`0x55000`, `0x57000`, `0x59000`, `0x5b000`).
- Panel: `qcom,mdss_dsi_k11_38_08_0a_dsc_cmd`, 1080x2400, DSC compressed,
  HDR10, 60 / 90 / 120 Hz.
- Backlight: `/sys/class/backlight/panel0-backlight`.
- There is **no** `/dev/graphics/`: the only frame buffer available before a
  native display driver exists is the one the boot loader leaves at
  `0xdfc00000` (reserved as `splash_region`).

## Touch — FocalTech over SPI

| Item | Value | Source |
| --- | --- | --- |
| Bus | `spi@a8c000` (GENI SPI11) | fdt |
| Node | `focaltech@0`, `compatible = "focaltech,fts"` | fdt |
| SPI clock | `0x5b8d80` = 6,000,000 Hz | fdt |
| Reset GPIO | `<&tlmm 0x16 0x00>` = GPIO 22 | fdt |
| IRQ GPIO | `<&tlmm 0x17 0x2008>` = GPIO 23, falling edge | fdt |
| Max touches | 10 | fdt |
| Display coords | 8640 x 19200 (1080x2400 at 8x) | fdt |

The live kernel module list confirms the same part: `focaltech_touch.ko`, and
`/sys/bus/spi/devices/spi1.0` is bound to `fts_ts`.

## Wi-Fi — QCA6490 (WCN6855 family) over PCIe + MHI

The device tree names the node `qcom,cnss-qca6490@b0000000`; the vendor
config directory is `qca6750`. Both are the WCN6855 family, whose Linux driver
is **ath11k**. The live `lsmod` shows `qca_cld3_wlan` + `cnss2` + `icnss2`.

| Item | Value | Source |
| --- | --- | --- |
| Compatible | `qcom,cnss-qca6490` | fdt |
| SMMU IOVA IPA | `0xb0000000` + `0x10000` | fdt |
| TCS cmd | `0xb2e5510` + `0x690` | fdt |
| wlan-en GPIO | GPIO 64 | fdt |
| bt-en GPIO | GPIO 65 | fdt |
| sw-ctrl GPIO | GPIO 153 | fdt |
| **MHI max channels** | **30** (`0x1e`) | fdt |
| **MHI timeout** | **10,000** ms (`0x2710`) | fdt |
| **MHI buffer length** | **32,768** (`0x8000`) | fdt |
| M2 no DB access | yes | fdt |
| Ramdump size | 4.33 MB (`0x420000`) | fdt |

### PCIe controller (the radio's bus)

| Window | Address | Size |
| --- | --- | --- |
| parf | `0x1c00000` | `0x3000` |
| phy | `0x1c06000` | `0x2000` |
| dm_core | `0x60000000` | `0xf1d` |
| elbi | `0x60000f20` | `0xa8` |
| iatu | `0x60001000` | `0x1000` |
| conf | `0x60100000` | `0x100000` |

- `ranges`: IO `0x60200000` + `0x100000`; MEM `0x60300000` + `0x3d00000`.
- `perst-gpio` GPIO 94, `wake-gpio` GPIO 96.
- `qcom,smmu-sid-base = <0x1c00>`; `iommu-map 0x00 -> 0x1c00, 0x100 -> 0x1c01`.
- TBU at `0x151a1000` (`anoc_1_pcie_tbu`).

### Firmware files

| Group | Where | Count |
| --- | --- | --- |
| BDF segments `bdwlan.e01..e93`, `e96`, `ee1`, `elf` | `/vendor/firmware_mnt/image/` | 147 |
| `WCNSS_qcom_cfg.ini` | `/vendor/etc/wifi/qca6750/` | 1 |

Each `bdwlan.eXX` segment is exactly 59,868 bytes. The BDF has to be
reassembled in order before ath11k will take it.

> **This is where the borrowed driver breaks.** HakiOS's `hakios.wlfw.c`
> downloads the board data file in **10** pieces for the WCN6750 over AHB.
> haydn has **147** pieces and reaches the radio over **PCIe + MHI**
> (`-DCONFIG_ATH11K_AHB` in HakiOS's `mk-ath11k.sh` selects the other
> transport). The QMI/WLFW exchange above the transport is reused unchanged;
> the transport below it is new work. See `docs/wifi.md`.

## Power, thermal, audio

- PMIC: `qcom,pm8350` (12 nodes) + `qcom,pmk8350` (4 nodes) — fdt.
- Thermal: **65** zones on the live phone. The vendor names include
  `gpuss-0-usr`, `gpuss-1-usr`, `ddr-usr`, `cpuss-0-usr`, `cpuss-1-usr`,
  `cpu-0-0-usr` .. `cpu-1-7-usr`, `nspss-0-usr` .. `nspss-2-usr`,
  `aoss-0-usr`, `aoss-1-usr`, `video-usr`, `mdmss-0-usr` .. `mdmss-2-usr`,
  `pop-mem-step`. HakiOS's `hakios.thermal.c` handles 27 for an SC7280; the
  table here has to be rebuilt, not reused.
- Power supplies the live kernel exposes: `battery`, `usb`, and `wireless`.
- Audio: `wcd938x` (13 nodes) + `cs35l41` (4 nodes) + bolero + SoundWire — fdt.
  ADSP firmware is 29 segments, 19.97 MB, largest `adsp.b20` at 12.06 MB.
- Haptics: `swr_haptics` over SoundWire (not an I2C part).

## Sensors

61 hardware sensors on the live phone. The parts and their buses:

| Part | Sensor | Driver |
| --- | --- | --- |
| `lsm6dso` (STMicro) | accelerometer, gyroscope | SSC |
| `ak0991x` (AKM) | magnetometer | SSC |
| `tcs3701` (ams) | ambient light, proximity | SSC |
| `bmp285` (Bosch) | barometer | SSC |

None of them has a path to XNU yet, and the SSC (sensor DSP) firmware is what
stands between here and one.

## What is still missing

These are inputs a port needs that this phone does not hand over without more
work. Each is a task, not an unknown:

1. **haydn's own UEFI volume set.** `Binaries/haydn` currently holds the venus
   (Mi 11) SM8350 set. Extracting the haydn XBL/UEFI volumes from a factory
   image and rebuilding `haydnPkg` from them is the first firmware task.
2. **The panel's DSI timing.** It lives in the `dtbo` partition
   (`androidboot.dtbo_idx=21`), not in the base tree; the base tree only names
   the panel. `dtbo_a` needs root to read.
3. **The BDF's assembly order.** 147 segments have to be joined the way the
   vendor's loader joins them; the vendor's own code (`cnss2`) does it at
   runtime and is not documented.
