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

### Still missing

The `Binaries/` files themselves. They are Qualcomm's and the phone's; this
repository carries the manifest and the checker, not the bytes.

The loader is the same either way: `fastboot boot`, everything in RAM, a
reboot returns the phone to Android.
