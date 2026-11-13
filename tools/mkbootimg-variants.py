#!/usr/bin/env python3
"""Repackage a Silicium boot image at every header version / page size.

The payload (BootShim + UEFI FD, gzip) is unchanged; only the ANDROID! header
is rewritten. This exists because the haydn ABL refused the v1/2048-byte image
the build used to emit with

    Failed to load/authenticate boot image: Load Error

and the only way to separate "wrong header" from "this path is blocked" is to
try the shapes one at a time.

    tools/mkbootimg-variants.py Mu-haydn.img -o out/bootimg-variants
"""
import argparse
import os
import struct

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)


def read_image(path):
    data = open(path, "rb").read()
    if data[:8] != b"ANDROID!":
        raise SystemExit("%s: not an Android boot image (%r)" % (path, data[:8]))
    ks, ka, rs, ra, ss, sa, ta, ps, ver, osv = struct.unpack_from("<10I", data, 8)
    if ver >= 3:
        kernel_off = 4096
    else:
        rnd = lambda n: (n + ps - 1) // ps * ps        # noqa: E731
        kernel_off = rnd(1632 if ver == 0 else 1648 if ver == 1 else 1660)
    return data, kernel_off, ks, ka, rs, ra, ss, sa, ta, osv


def build_v012(kernel, ks, ka, rs, ra, ss, sa, ta, osv, version, page):
    hdr = struct.pack("<8s10I", b"ANDROID!", ks, ka, rs, ra, ss, sa, ta,
                      page, version, osv).ljust(1632, b"\0")
    if version >= 1:
        hdr += struct.pack("<IQI", 0, 0, 1648 if version == 1 else 1660)
        if version == 2:
            hdr += struct.pack("<IQ", 0, 0)            # dtb_size, dtb_addr
    return _assemble(hdr, kernel, page)


def build_v34(kernel, ks, osv, version, page):
    header_size = 1580 if version == 3 else 1584
    hdr = bytearray(b"ANDROID!")
    hdr += struct.pack("<I", ks)
    hdr += struct.pack("<I", 0)                        # ramdisk_size
    hdr += struct.pack("<I", osv)
    hdr += struct.pack("<I", header_size)
    hdr += struct.pack("<4I", 0, 0, 0, 0)              # reserved
    hdr += struct.pack("<I", version)
    hdr += b"\0" * 1536                                # cmdline
    if version == 4:
        hdr += struct.pack("<I", 0)                    # signature_size
    assert len(hdr) == header_size, len(hdr)
    return _assemble(bytes(hdr), kernel, page)


def _assemble(hdr, kernel, page):
    rnd = lambda n: (n + page - 1) // page * page      # noqa: E731
    return hdr + b"\0" * (rnd(len(hdr)) - len(hdr)) + kernel + b"\0" * (rnd(len(kernel)) - len(kernel))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("image", nargs="?",
                    default=os.path.join(REPO, "out", "Mu-haydn.img"))
    ap.add_argument("-o", "--outdir",
                    default=os.path.join(REPO, "out", "bootimg-variants"))
    args = ap.parse_args()

    data, kernel_off, ks, ka, rs, ra, ss, sa, ta, osv = read_image(args.image)
    kernel = data[kernel_off:kernel_off + ks]
    os.makedirs(args.outdir, exist_ok=True)
    print("%s: kernel_size=%d (offset %d), ramdisk_size=%d" %
          (os.path.basename(args.image), ks, kernel_off, rs))

    made = []
    for version in (0, 1, 2):
        for page in (2048, 4096):
            img = build_v012(kernel, ks, ka, rs, ra, ss, sa, ta, osv, version, page)
            name = "boot-v%d-p%d.img" % (version, page)
            open(os.path.join(args.outdir, name), "wb").write(img)
            made.append((name, len(img)))
    for version in (3, 4):
        for page in (2048, 4096):
            img = build_v34(kernel, ks, osv, version, page)
            name = "boot-v%d-p%d.img" % (version, page)
            open(os.path.join(args.outdir, name), "wb").write(img)
            made.append((name, len(img)))

    for name, size in made:
        print("  %-20s %9d bytes" % (name, size))


if __name__ == "__main__":
    main()
