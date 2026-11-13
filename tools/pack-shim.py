#!/usr/bin/env python3
"""Pack the shim + an XNU payload into a boot image this ABL accepts.

Same layout sweet uses:

    mkbootimg --header_version 2 --pagesize 4096 --base 0 \
      --kernel_offset 0x8000 --ramdisk_offset 0x1000000 --tags_offset 0x100 \
      --dtb_offset 0x1f00000 --dtb <phone DTB> \
      --kernel Image --ramdisk payload.bin -o shim-boot-haydn.img

ABL hands the ramdisk to the shim as /chosen linux,initrd-start/end, and the
shim reads the SWEETXNU payload out of it. mkbootimg itself is not installed on
this host, so the header is written here; the field offsets are the v2 header.

    tools/pack-shim.py Image payload.bin docs/haydn-fdt.dtb -o out/shim-boot.img
"""
import argparse
import os
import struct

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

OS_VERSION = (17 << 16) | (0 << 8)          # 17.0.0
OS_PATCH_LEVEL = (2035 << 16) | 6           # 2035-06


def pack(kernel, ramdisk, dtb, page=4096,
         kernel_offset=0x8000, ramdisk_offset=0x1000000,
         tags_offset=0x100, dtb_offset=0x1f00000, cmdline="console=null",
         name="haydn-shim"):
    hdr = bytearray(b"ANDROID!")
    hdr += struct.pack("<I", len(kernel))
    hdr += struct.pack("<I", kernel_offset)
    hdr += struct.pack("<I", len(ramdisk))
    hdr += struct.pack("<I", ramdisk_offset)
    hdr += struct.pack("<I", 0)                      # second_size
    hdr += struct.pack("<I", 0)                      # second_addr
    hdr += struct.pack("<I", tags_offset)
    hdr += struct.pack("<I", page)
    hdr += struct.pack("<I", 2)                      # header_version
    hdr += struct.pack("<I", OS_VERSION)
    nm = name.encode()[:15]
    hdr += nm + b"\0" * (16 - len(nm))
    cm = cmdline.encode()[:511]
    hdr += cm + b"\0" * (512 - len(cm))
    hdr += b"\0" * 32                                # id fields  -> offset 608
    hdr += b"\0" * 1024                              # extra_cmdline -> 1632
    hdr += struct.pack("<IQI", 0, 0, 1660)           # recovery_dtbo, header_size
    hdr += struct.pack("<IQ", len(dtb), dtb_offset)  # dtb_size, dtb_addr

    rnd = lambda n: (n + page - 1) // page * page    # noqa: E731
    body = kernel + b"\0" * (rnd(len(kernel)) - len(kernel))
    body += ramdisk + b"\0" * (rnd(len(ramdisk)) - len(ramdisk))
    body += dtb + b"\0" * (rnd(len(dtb)) - len(dtb))
    return bytes(hdr) + b"\0" * (rnd(len(hdr)) - len(hdr)) + body


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("kernel", help="the shim Image (flat binary, linked at 0)")
    ap.add_argument("ramdisk", help="the XNU payload built by tools/mkpayload.py")
    ap.add_argument("dtb", nargs="?", default=os.path.join(REPO, "docs", "haydn-fdt.dtb"))
    ap.add_argument("-o", "--out", default=os.path.join(REPO, "out", "shim-boot-haydn.img"))
    args = ap.parse_args()

    kernel = open(args.kernel, "rb").read()
    ramdisk = open(args.ramdisk, "rb").read()
    dtb = open(args.dtb, "rb").read() if os.path.exists(args.dtb) else b""

    img = pack(kernel, ramdisk, dtb)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    open(args.out, "wb").write(img)

    ks, ram_off, page, ver = (struct.unpack_from("<I", img, o)[0]
                              for o in (8, 20, 36, 40))
    dtb_size = struct.unpack_from("<I", img, 1648)[0]
    print("%s: %d bytes" % (args.out, len(img)))
    print("  kernel %d, ramdisk %d at +0x%x, dtb %d" % (ks, len(ramdisk), ram_off, dtb_size))
    print("  header v%d, page %d" % (ver, page))


if __name__ == "__main__":
    main()
