# UniXNU-haydn

UniXNU device repository for the **Xiaomi Redmi K40 Pro / K40 Pro+ / Mi 11i**
(`haydn`, Qualcomm SM8350 / Snapdragon 888).

| Repository | Contents |
| --- | --- |
| [UniXNU](https://github.com/UniXNU/UniXNU) | Build tools, component catalog, ARM64 and OS profiles |
| `soc/sm8350` (vendored here) | SM8350 resources, DTSI, config fragment, patches |
| `uefi-haydn` | Mu-Silicium UEFI port — **not published yet**, see `docs/uefi.md` |

Porting record: [`porting.toml`](porting.toml). Hardware facts, with the
source of every number: [`docs/hardware.md`](docs/hardware.md).

## State

**Configuration and hardware inventory only. Nothing has been booted on the
device from this repository yet.**

What exists:

- `board.toml` — board identity, components, kernel config, partition geometry,
  firmware paths, payload and ADT settings.
- `configs/haydn_defconfig` — the kernel configuration for the first milestone.
- `dts/haydn.dts` + `dts/haydn-reserved.dtsi` — the board tree, generated from
  the phone's own live FDT (799,754 bytes) rather than guessed.
- `soc/sm8350/` — the shared SoC layer, with the phone's real addresses.
- `docs/hardware.md` — every address, with the line it came from.

What does not exist yet, in the order it has to be built:

1. **haydn's UEFI volumes** — the firmware package this board builds against
   is currently the venus (Mi 11) SM8350 set. Same SoC, same vendor DXE
   inventory, different board. Replacing it is the first task.
2. **UFS root** — the transport is vendored (`ShengUfs`) but the audited
   `IOBlockStorageDevice` binding is not; the defconfig builds probe-only.
3. **Display** — no DSI/MDSS driver. Only the loader's frame buffer.
4. **Touch** — the FocalTech FTS protocol is understood (see `docs/hardware.md`
   for the bus and pins) but no driver is written.
5. **GPU** — the Adreno 660's registers are mapped; the driver is not here.
6. **Wi-Fi** — QCA6490 over PCIe + MHI. The transport has no implementation
   anywhere in the catalog. See `docs/wifi.md` for what it needs.

## Prerequisites

- A UniXNU checkout beside this repository (`../UniXNU`).
- A `fastboot`-capable host for the device.
- The donor IPSW components under `../UniXNU/out/ipsw/21H461/` (iPad7,1,
  iPadOS 17.7.11, build 21H461), including `kernelcache.decompressed`.
- The phone's own firmware, pulled from the phone with root. This repository
  never carries it: `docs/firmware.md` lists the 289 files and how to get
  each group back.

## Building

Two workflows. `resolve.yml` runs everything that needs nothing but Python:
the five test suites (278 assertions), the four scripts, and the check that
the reserved-memory generator reproduces its own output from two different
inputs.

`build.yml` compiles the UEFI volume. The questions Python cannot answer —
does haydnPkg assemble, which DXE drivers are missing, does the FD link — are
answered there, and the answers are yes: edk2 builds it, 48 images verify, and
`SILICIUM_UEFI.fd` comes out at the full `0x200000`. When the job is green it
publishes two artifacts: the `.fd` and `Mu-haydn.img`, which is the same
volume wrapped for `fastboot boot`.

`docs/uefi.md` records the gates that had to be passed to get there — three of
them are edk2 rules that are not written down anywhere obvious, and each cost a
round trip.

It seeds `Binaries/haydn` from `Binaries/venus` — the same SoC, and the only
set that exists — to get past "binary not found" and reach the errors that
are about haydn rather than about the binaries. **The volume that produces
must not be flashed**: it carries venus's panel and PMIC tables, and a green
build therefore says the package assembles, not that the display comes up.
`docs/install.md` says how to boot it in RAM once that changes.

## What the UEFI build consumes from the phone

The UEFI volume itself is **compiled** — Mu-Silicium plus the Silicium SM8350
support, the way `venusPkg`'s is. What comes from the handset is a handful of
firmware pieces: `devcfg`, `tz`, `aop`, `qupfw`, `uefisecapp`, and the image
volume. `abl` is LK (ELF32 ARM) and `xbl` is the first loader (ELF64); neither
holds a firmware volume, and this phone has no `uefi` partition at all.

`platform/haydnPkg/binaries.toml` records each piece: the partition it came
from, how many bytes of that partition were real, and its SHA-256.
`docs/binaries.md` says what each one does. The files are not in this
repository, and:

```sh
python3 scripts/verify-binaries.py            # checks what is in Binaries/
```

## The ADT

The kernel is handed an ADT, not a DTB: a flat list of nodes with no magic
and no checksum, so a reader that gets the layout wrong drifts through the
rest of the file without ever reporting an error. `scripts/adt.py` is the
reader and writer this repository carries so that a haydn ADT can be
checked without a UniXNU checkout:

```sh
python3 scripts/adt.py check /path/to/kernel.macho.adt
python3 scripts/adt.py dump  /path/to/kernel.macho.adt /reserved-memory
```

`scripts/check-reserved.py` closes the loop: it reads `dts/haydn-reserved.dtsi`
back, builds the ADT a board would publish for those regions, and asserts
the two agree in count, order, address, size and `no-map`.

## Build

Run from a UniXNU checkout:

```sh
./unixnu defconfig haydn_defconfig -D ../UniXNU-haydn
./unixnu fetch -D ../UniXNU-haydn
./unixnu status --json -D ../UniXNU-haydn
./unixnu tree -D ../UniXNU-haydn
./unixnu build kernel -D ../UniXNU-haydn
```

`status` is the first checkpoint: it must resolve the device, the
`ipados-17.7.11-21H461` profile and the vendored `sm8350` SoC source, and
print the output directory.

The kernel step needs a Mach-O capable toolchain. On Linux that is
`scripts/linux/setup-toolchain.py` in the UniXNU checkout; on a machine with
neither, UniXNU's macOS GitHub Actions workflow runs the same steps.

## What is never in this repository

Nothing of Apple's, nothing of Xiaomi's: no IPSW member, no firmware blob, no
extracted vendor image. `docs/firmware.md` says where each one comes from and
the SHA-256 that identifies it; the files stay where they were taken from.

## Licence

BSD-2-Clause-Patent for this repository's own files; the kernel changes are
under the Apple Public Source License 2.0, as their file headers say.