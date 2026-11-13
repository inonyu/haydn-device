#!/bin/bash
# Build the haydn shim and wrap it in a boot image the ABL will take.
#
# This is sweet's shim retargeted to this board: the frame buffer, the virtual
# timer INTID and the IMEM restart reason are all haydn's, and the physical
# timer is never armed (QHEE owns CNTP_* on this SoC, so an EL1 write traps).
#
# The image is v2 at 4096-byte pages with the phone's own DTB appended, which is
# the shape that produced "Booting OKAY" on this bootloader.
set -euo pipefail
cd "$(dirname "$0")"

CROSS="${CROSS:-aarch64-linux-gnu-}"
CC="${CROSS}gcc"
OBJCOPY="${CROSS}objcopy"
NM="${CROSS}nm"
READELF="${CROSS}readelf"

CFLAGS="-O2 -ffreestanding -nostdlib -fno-pic -mgeneral-regs-only -mstrict-align -fno-stack-protector -Wall -Wextra"

mkdir -p out
for f in start.S shim.c console.c mmu.c fdt.c loader.c ufs.c; do
  $CC $CFLAGS -c "$f" -o "out/${f%.*}.o"
done

# The image runs wherever ABL puts it with no relocation pass: only the
# header's image_size (start.o, linked at 0) may be an absolute address.
abs=$($READELF -r out/shim.o out/console.o out/mmu.o out/fdt.o out/loader.o out/ufs.o | grep -c ABS64 || true)
[ "$abs" = 0 ] || { echo "error: $abs absolute relocations in C objects" >&2; exit 1; }

$CC $CFLAGS -static -T shim.ld -Wl,--build-id=none -Wl,--no-warn-rwx-segments -Wl,-N \
  out/start.o out/shim.o out/console.o out/mmu.o out/fdt.o out/loader.o out/ufs.o -o out/shim.elf

$OBJCOPY -O binary out/shim.elf out/Image
# ABL copies the file; pad to image_size so .bss/stacks exist as zeroed bytes.
size=$($NM out/shim.elf | awk '$3=="_end"{print strtonum("0x"$1)}')
truncate -s "$size" out/Image

# Ramdisk: the xnu payload built by tools/mkpayload.py, or a minimal newc cpio.
if [ -n "${1:-}" ]; then
  cp "$1" out/ramdisk.bin
else
  (cd out && rm -rf rd && mkdir rd && cd rd && find . | cpio -o -H newc --quiet | gzip -9 > ../ramdisk.bin)
fi

DTB="${2:-../docs/haydn-fdt.dtb}"

mkbootimg --header_version 2 --pagesize 4096 --base 0 \
  --kernel_offset 0x8000 --ramdisk_offset 0x1000000 --tags_offset 0x100 \
  --dtb_offset 0x1f00000 --dtb "$DTB" \
  --os_version 17.0.0 --os_patch_level 2035-06 \
  --cmdline "console=null" \
  --kernel out/Image --ramdisk out/ramdisk.bin \
  -o out/shim-boot-haydn.img

ls -l out/Image out/shim-boot-haydn.img
