# UEFI for haydn

The firmware package this board builds against does not exist yet. This page
records what is there now, why, and what replaces it.

## What is there now

`board.toml` points at `Platforms/Xiaomi/haydnPkg/haydn.dsc`, and that package
is a copy of `venusPkg` — the Xiaomi Mi 11 (M2011K2C, SM8350). The two phones
share the SoC and the same vendor DXE inventory, so it is the right template,
and the wrong board.

The upstream tree already carries these Xiaomi platforms as of 2026-11-12:

```
alioth  annibale  cepheus  citrus  equuleus  fog  garnet  ginkgo  ingres
lancelot  laurel_sprout  lavender  lime  lisa  marble  miatoll  muyu  nabu
nitrogen  nuwa  onyx  peridot  phoenix  pipa  polaris  renoir  spes  stone
surya  sweet_k6a  tapas  vayu  venus  veux  vili  willow
```

`haydn` is not among them.

## Why the venus set cannot stay

A board's DXE set carries its own memory map, its own GPIO and PMIC tables,
and its own panel init. Values lifted from a sibling board put the firmware
heap somewhere this phone does not have memory, and drive a panel this phone
does not have. The earlier haydn porting record says the same thing about its
own baseline: *"Binaries/haydn is a copy of the venus SM8350 set"*, listed as
a limit, not a choice.

Two consequences worth stating plainly:

1. Nothing built from this repository can be trusted to reach the frame
   buffer on haydn until the volumes are replaced.
2. The replacement inputs are all obtainable: the phone is unlocked, root is
   available, and the XBL/UEFI volumes can be read from a factory image or
   from the phone's own partitions.

## What replaces it

`platform/haydnPkg/` now holds it:

| File | What |
| --- | --- |
| `haydn.dsc` | The platform description: packages, libraries, FD base and size |
| `haydn.fdf` | What goes into the flash device |
| `binaries.toml` | The six firmware pieces this phone gave, with hashes |

Generated from `venusPkg`'s equivalents with the board facts replaced. The
UEFI implementation is shared on purpose. `docs/binaries.md` says what the
six pieces are; `scripts/verify-binaries.py` checks whichever of them are
put in `Binaries/`.

### The FD base

`0x9FD00000`, and it is not venus's number borrowed. SM8350's `abl` is an
ELF32 ARM image whose own header says it occupies
`[0x9fa00000, 0x9fa30000)` with its entry at `0x9fa00000`. Three megabytes
past that is free on any board of this family.

`scripts/check-platform.py` checks the 64 MiB window that starts there
against this phone's DRAM base (`0x80000000`) and its six reserved regions —
`hyp_region`, `xbl_aop_region`, `res_xbl_uefi_log`, `modem_region`,
`removed_region`, `splash_region` — and against the DSC and the FDF agreeing
with each other, which edk2 does not check.

## The build loop

The package is compiled by `.github/workflows/build.yml` on Ubuntu 24.04: clone
Mu-Silicium, drop this package into `Platforms/Xiaomi/haydnPkg`, seed
`Binaries/` from the venus set, run `build_uefi.py -d haydn -r DEBUG`. The
seeded volume must not be flashed — it carries venus's panel and PMIC tables —
and the workflow says so where it does it.

No AArch64 UEFI compiler exists on the Windows host this repository was written
on, so CI is the only place the build has ever run. Each run answers one
question, and the ones answered so far are recorded here because each cost a
round trip:

| Run | Stopped at | What it proved |
| --- | --- | --- |
| 1 | `The Device Build Script isn't Present in "Platforms/Xiaomi/haydnPkg"` | `build_uefi.py` requires a `DeviceBuild.py` inside every device package |
| 2 | `TypeError` in `DebugMacroCheckBuildPlugin.do_pre_build` | `Edk2Path.GetContainingPackage()` finds packages by `*.dec`, and haydnPkg had none |
| 3–4 | `error 1001: Module type [SEC] is not supported by library instance [.../UefiDebugLibStdErr.inf]` | a bare `[LibraryClasses]` in the DSC applies to every module type, SEC included |
| 5 | reached the compiler for the first time | the package assembles once only its own libraries are named |
| 6–7 | edk2 green, then `The Device DTB is Missing in "Resources/DTBs"` | the volume links: 48 images verified, `SILICIUM_UEFI.fd` at the full `0x200000` with FVMAIN at 99%. Only the packaging step was left |
| 8–13 | `The Device DTB is Missing in "Resources/DTBs"` until `append_dtb` was turned off | the DTB that was being asked for is a *kernel* DTB; what this repository carries is the bootloader's FDT, and appending that would hand the kernel a second, vendor-shaped tree |

### Three things about edk2 that are not written down anywhere obvious

1. **`DeviceBuild.py` is mandatory.** `get_device_package_path()` finds the
   package by globbing `*/<device>Pkg` and `*/*/<device>Pkg` under `Platforms/`,
   then refuses to continue unless `<device>Pkg/DeviceBuild.py` exists. Every
   board in the tree ships one; haydnPkg's is vili's structure with the name
   and the scopes changed.

2. **`<device>.dec` is the package marker.** Zero bytes is fine and normal —
   `venus.dec`, `vili.dec` and `nabu.dec` are all empty. The file exists so
   `GetContainingPackage()` can walk up from the DSC and name the package; with
   no `.dec` it returns `None` and edk2's own pre-build plugins crash on it.

3. **`[LibraryClasses]` is not per-section.** `[LibraryClasses.common.SEC` and
   `[LibraryClasses.AARCH64]` narrow the type; a plain `[LibraryClasses]` does
   not, so anything listed there is forced on SEC as well. The two packages
   that build (venus, vili) name only their own two libraries and inherit
   everything else from `LahainaPkg.dsc.inc`.

### The patch series has to carry what it names

`soc/sm8350/patches/xnu/series` names `sheng-platform-power.patch`, and
`unixnu status` refuses a series whose entries are missing:

```
soc/sm8350/patches/xnu/series:6: patch missing:
  .../soc/sm8350/patches/xnu/sheng-platform-power.patch
```

A bare entry resolves against the series' own directory, so the 352-byte hook
is vendored beside it rather than referenced across repositories. It calls
`sheng_pmgr_run()` from `bsd_init` when `XNU_SHENG_PMGR` is set, and both this
board's defconfig and `soc/sm8350/configs/sm8350.config` set it — the patch and
the config that needs it travel together.

### Still missing

The `Binaries/` files themselves. They are Qualcomm's and the phone's; this
repository carries the manifest and the checker, not the bytes.

The loader is the same either way: `fastboot boot`, everything in RAM, a
reboot returns the phone to Android.