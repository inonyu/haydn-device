#!/usr/bin/env python3
"""Wrap an existing boot image payload with the phone's own DTB, sweet-style.

sweet's shim-boot.img is loaded by a Qualcomm ABL, and this is its recipe:

    mkbootimg --header_version 2 --pagesize 4096 --base 0 \
      --kernel_offset 0x8000 --ramdisk_offset 0x1000000 --tags_offset 0x100 \
      --dtb_offset 0x1f00000 --dtb boot_unpacked/dtb \
      --os_version 17.0.0 --os_patch_level 2035-06 --cmdline "console=null"

The haydn artifact has none of those fields set: v1, 2048-byte pages, no DTB,
empty cmdline. This builds the same payload under that recipe, and a couple of
one-variable-at-a-time neighbours, so a refusal can be attributed.

    tools/mkbootimg-dtb.py Mu-haydn.img docs/haydn-fdt.dtb -o out/bootimg-variants
"""
import argparse
import os
import struct

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

OS_VERSION = (17 << 16) | (0 << 8)              # 17.0.0
OS_PATCH_LEVEL = (2035 << 16) | 6               # 2035-06


def payload_of(path):
    data = open(path, "rb").read()
    if data[:8] != b"ANDROID!":
        raise SystemExit("%s: not an Android boot image" % path)
    ks = struct.unpack_from("<I", data, 8)[0]
    ver = struct.unpack_from("<I", data, 40)[0]
    off = 4096 if ver >= 3 else 2048
    return data[off:off + ks]


def build(kernel, dtb, version, page, cmdline, os_version, os_patch,
          kernel_offset=0x8000, ramdisk_offset=0x1000000,
          tags_offset=0x100, dtb_offset=0x1f00000):
    ks = len(kernel)
    ramdisk = b"\0" if version < 3 else b""      # ABL dislikes a zero-size ramdisk
    hdr = bytearray(b"ANDROID!")
    hdr += struct.pack("<I", ks)
    hdr += struct.pack("<I", kernel_offset)
    hdr += struct.pack("<I", len(ramdisk))
    hdr += struct.pack("<I", ramdisk_offset)
    hdr += struct.pack("<I", 0)                  # second_size
    hdr += struct.pack("<I", 0)                  # second_addr
    hdr += struct.pack("<I", tags_offset)
    hdr += struct.pack("<I", page)
    hdr += struct.pack("<I", version)
    hdr += struct.pack("<I", os_version)
    hdr += b"\0" * 16                            # name
    cm = cmdline.encode()[:511]
    hdr += cm + b"\0" * (512 - len(cm))
    hdr += b"\0" * 32                            # id fields
    hdr += b"\0" * 1024                          # extra_cmdline
    if version >= 1:
        hdr += struct.pack("<IQI", 0, 0, 1648 if version == 1 else 1660)
    if version >= 2:
        hdr += struct.pack("<IQ", len(dtb), dtb_offset if dtb else 0)
    rnd = lambda n: (n + page - 1) // page * page       # noqa: E731
    body = kernel + b"\0" * (rnd(ks) - ks)
    if ramdisk:
        body += ramdisk + b"\0" * (rnd(len(ramdisk)) - len(ramdisk))
    if version >= 2 and dtb:
        body += dtb + b"\0" * (rnd(len(dtb)) - len(dtb))
    return bytes(hdr) + b"\0" * (rnd(len(hdr)) - len(hdr)) + body


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("image", nargs="?",
                    default=os.path.join(REPO, "out", "Mu-haydn.img"))
    ap.add_argument("dtb", nargs="?", default=os.path.join(REPO, "docs", "haydn-fdt.dtb"))
    ap.add_argument("-o", "--outdir",
                    default=os.path.join(REPO, "out", "bootimg-variants"))
    args = ap.parse_args()

    kernel = payload_of(args.image)
    dtb = open(args.dtb, "rb").read() if os.path.exists(args.dtb) else b""
    os.makedirs(args.outdir, exist_ok=True)
    print("payload %d bytes, dtb %d bytes (%s)" %
          (len(kernel), len(dtb), os.path.basename(args.dtb)))

    cases = [
        ("boot-sweetstyle.img",      2, 4096, True,  "console=null"),
        ("boot-sweetstyle-nodtb.img", 2, 4096, False, "console=null"),
        ("boot-v1-p2048-dtb.img",    1, 2048, True,  ""),
        ("boot-v0-p2048-dtb.img",    0, 2048, True,  ""),
    ]
    for name, version, page, use_dtb, cmdline in cases:
        img = build(kernel, dtb if use_dtb else b"", version, page, cmdline,
                    OS_VERSION, OS_PATCH_LEVEL)
        open(os.path.join(args.outdir, name), "wb").write(img)
        print("  %-28s %9d bytes  v%d p%d%s" %
              (name, len(img), version, page, " +dtb" if use_dtb else ""))


if __name__ == "__main__":
    main()
