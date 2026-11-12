# AGENTS.md — haydn

Read before changing anything here.

## What this repository is

A UniXNU device repository: board facts, kernel configuration and device tree
for the Xiaomi Redmi K40 Pro (`haydn`, SM8350). It does not carry firmware or
anything of Apple's.

## The rule that matters most

**Every hardware address in this repository must be traceable to the phone.**
`docs/hardware.md` names the source of each one: a line in `haydn-fdt.dts`, a
live `/sys/bus/platform/devices` entry, or a `getprop`. An address that came
from a sibling board, a wiki or a guess is a bug even when it happens to work.

The UFS PHY is the cautionary example: this board's is `0x1d87000`, and an
earlier record carried `0x1d80000` from somewhere else. The driver built
against the wrong address does not fail loudly — it touches registers that
belong to another block.

## Ownership paths

| Path | Owner |
| --- | --- |
| `board.toml`, `feeds.toml`, `configs/` | board identity and kernel settings |
| `dts/haydn.dts` | the board's own tree |
| `dts/haydn-reserved.dtsi` | **generated**; edit `scripts/gen-reserved.py`, not this |
| `soc/sm8350/` | shared SoC layer; a change here affects every SM8350 board |
| `docs/` | the record; keep it ahead of the code |

## When something stops working

The porting record (`porting.toml`) is the first place to look: it says, per
area, what was actually observed and what is still only recorded. `evidence =
[]` on an area means nothing there has been run on hardware.
