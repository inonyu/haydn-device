#!/usr/bin/env python3
"""NOP out the physical-timer write that traps on this SoC.

haydn's QHEE keeps the physical timer (CNTP_*_EL0) to itself. At EL1 a write
to it is UNDEF, and XNU has exactly one such write:

    _fiq_context_init + 0x14:   MSR CNTP_CTL_EL0, x8
                                pc 0xfffffe0007492348, word 0xd51be228

which is what the phone panicked on 2026-11-14 ("Undefined kernel instruction:
pc=0xfffffe0007492348 instr=d51be228"). The virtual timer is untouched and is
what the ADT advertises (virtual-timer-intid 27), so replacing that one word
with a NOP leaves the kernel's timer path intact.

The address is found by scanning, not hard-coded, so a rebuild at a different
link base still patches the right instruction.

    tools/nop-cntp.py KERNEL OUT
"""
import struct
import sys

NOP = 0xD503201F
# (op0, op1, CRn, CRm, op2) for the physical timer's writable registers.
TIMER = {(3, 3, 14, 2, 0): "CNTP_TVAL_EL0",
         (3, 3, 14, 2, 1): "CNTP_CTL_EL0",
         (3, 3, 14, 3, 3): "CNTP_CVAL_EL0"}


def segments(b):
    _, _, _, _, ncmds, _, _, _ = struct.unpack_from("<8I", b, 0)
    out = []
    off = 32
    for _ in range(ncmds):
        cmd, size = struct.unpack_from("<II", b, off)
        if cmd == 0x19:                       # LC_SEGMENT_64
            name = b[off + 8:off + 24].split(b"\0")[0].decode()
            va, vs, fo, fs = struct.unpack_from("<4Q", b, off + 24)
            out.append((name, va, vs, fo, fs))
        off += size
    return out


def find_writes(b, segs):
    """Every MSR to a physical-timer sysreg, as (file offset, va, word, name)."""
    hits = []
    for name, va, vs, fo, fs in segs:
        blob = b[fo:fo + fs]
        for i in range(0, len(blob) - 3, 4):
            w = struct.unpack_from("<I", blob, i)[0]
            if (w >> 20) != 0xD51:            # MSR (register), not MRS
                continue
            o0 = (w >> 19) & 1
            op1 = (w >> 16) & 7
            crn = (w >> 12) & 0xF
            crm = (w >> 8) & 0xF
            op2 = (w >> 5) & 7
            key = (2 + o0, op1, crn, crm, op2)
            if key in TIMER:
                hits.append((fo + i, va + i, w, TIMER[key]))
    return hits


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    src, dst = sys.argv[1], sys.argv[2]
    b = bytearray(open(src, "rb").read())
    hits = find_writes(bytes(b), segments(bytes(b)))
    if not hits:
        sys.exit("no physical-timer writes found in %s" % src)
    for fo, va, w, name in hits:
        print("  %016x  %08x  %-14s -> NOP" % (va, w, name))
        struct.pack_into("<I", b, fo, NOP)
    open(dst, "wb").write(b)
    left = find_writes(bytes(b), segments(bytes(b)))
    print("%d write(s) patched, %d left, %s" % (len(hits), len(left), dst))
    if left:
        sys.exit("still trapped")


if __name__ == "__main__":
    main()
