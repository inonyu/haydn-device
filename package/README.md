# Package

The drivers this board writes for itself. Everything in the catalog is shared;
these four are haydn's.

| File | Lines | What | State |
| --- | --- | --- | --- |
| `pcie/haydn.pcie.{h,c}` | 88 + 181 | The PCIe root complex: six windows mapped, the radio's identity read from config space | Written, not built, not run |
| `touch/haydn.touch.{h,c}` | 116 + 226 | The FocalTech screen on SPI11: FTS 5.x framing, CRC, the 15-bit report decode | Written, not built; decode is tested |
| `storage/haydn.ufs.{h,c}` | 255 + 377 | The UFS host controller and the loader's page: read-only probe, the whitelist that refuses every write, and the request/answer protocol | Written, not built; whitelist and protocol are tested |
| `gpu/haydn.gpu.{h,c}` | 291 + 1041 | The Adreno 660: the register map, the 22-step table, and steps 1 to 9 (through the SMMU's identification and stream table) | Written, not built; addresses, the decision tables and both map sizes are tested |
| `conf` | — | Makes each a configuration symbol | — |

None has been compiled, because this repository has no build yet (see the
root README). None has been run, because nothing has been run on the phone
from this repository.

## What the tests cover, and why those three

| Test | Covers | Caught |
| --- | --- | --- |
| `tests/touch-format.py` | The FTS report layout and the CRC | A 12-bit reading of a 15-bit field: every touch decoded to the wrong place, silently |
| `tests/ufs-whitelist.py` | The command whitelist and the CDB builders | — (written after the fact, so it pins the rule down rather than catching a bug) |
| `tests/gpu-addresses.py` | The register map, the two speed tables, the GMU's window | Nothing yet, but it pins down that the GMU's reg covers two other blocks, which is a rule the driver has to obey |
| `tests/loader-page.py` | The loader's shared page: attach, the sequence protocol, stale answers, timeouts, the buffer bound | A simulator of both sides; the failure modes it covers are all silent on hardware |

## The holes, and why they are holes

Each driver stops at the boundary of what XNU can be asked to do without a
component behind it, rather than containing a guess:

- **PCIe** maps and reads. It does not vote a clock, cut a reset, or train a
  link: those go through the GDSC and the TLMM, and the TLMM's base is not in
  the base device tree. `HAYDN_TLMM_BASE` is `0` with a comment saying so.
- **Touch** decodes and scales. It does not perform the SPI transfer:
  `haydn_touch_spi_transfer()` is declared and not defined, for whatever binds
  the driver to `QcomGeniSpi`.
- **Storage** does two things and stops at the second: it probes the
  controller, and it reads through the loader's page. It does not put a command
  list into the controller, because that needs memory the loader offers and a
  list-lifecycle the loader has to agree to.
- **GPU** does seven steps. Steps 1-3 read; step 4 powers CX; step 5 brings its
  clocks up; steps 6 and 7 read the GMU and the RPMh channel it will vote
  through. It stops before step 8: from there the sequence needs the GMU's
  firmware and a TrustZone path this kernel does not have, and the next register
  written is inside the GMU's own memory.

An unresolved symbol at link time is a better record of a missing piece than
a plausible-looking register write.
