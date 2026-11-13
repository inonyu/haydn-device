#!/usr/bin/env python3
"""Check the firmware volume the build produced, without trusting the build.

A green edk2 run says the package assembled and the FD linked. It does not say
the volume is this board's, and the two ways it can be wrong are both silent:

  * the FV is a different length than the flash region, so the bootloader reads
    past the end of it;
  * a sibling board's tables are inside it, because Binaries/ was seeded from
    one (see the workflow) and the DSC pointed at a driver that carries them.

    python3 scripts/verify-volume.py out/fd/SILICIUM_UEFI.fd
    python3 scripts/verify-volume.py out/fd/SILICIUM_UEFI.fd out/Mu-haydn.img
"""

import os
import struct
import sys

failures = []


def check(name, ok, detail=''):
    if ok:
        print('  ok    ' + name)
    else:
        print('  FAIL  ' + name + '  ' + detail)
        failures.append(name)


# The one number that matters most: the FD is the flash region ABL is told about
# and it is fixed at 2 MiB by haydn.dsc (FD_SIZE = 0x00200000).
FD_SIZE = 0x00200000

# Strings that must NOT be in a haydn volume. Each is a sibling board's identity
# or a panel/PMIC table that only that board needs.
FOREIGN = [
    'M2011K2G',      # venus, Mi 11
    'Mi 11',
    '11T Pro',       # vili
    'mdss_dsi_venus',
    'mdss_dsi_k11',
    'M2012K11C',     # our own retail sku is fine -- see below, it is absent too
]
# ...and the strings that must be. The retail sku is deliberately not required:
# SiliciumPkg's SmBiosTableDxe writes model strings, and whether it emits the
# retail sku depends on a PCD this package sets but that driver may not read.
EXPECTED = ['Redmi K40 Pro']


def find(text, needle):
    """Offset of an ASCII string in a latin-1 decode of the image, or -1."""
    return text.find(needle)


def read(path):
    with open(path, 'rb') as f:
        return f.read()


def check_fd(path):
    data = read(path)
    text = data.decode('latin-1')

    print('%s: %d bytes' % (os.path.basename(path), len(data)))
    check('the volume is exactly FD_SIZE', len(data) == FD_SIZE,
          '%d vs %d' % (len(data), FD_SIZE))

    check('it starts with an ARM64 reset vector',
          data[0] == 0xa8 and data[1] == 0x26 and data[2] == 0x00,
          data[:4].hex())

    # EFI_FIRMWARE_VOLUME_HEADER: ZeroVector(16) FsGuid(16) FvLength(8) ...
    fv_len = struct.unpack('<Q', data[32:40])[0]
    check('the FV header declares the whole region', fv_len == FD_SIZE,
          hex(fv_len))
    check('the FV signature is _FVH', data[40:44] == b'_FVH', str(data[40:44]))

    for s in EXPECTED:
        check('it says "%s"' % s, find(text, s) >= 0)
    for s in FOREIGN:
        # "M2012K11C" is this phone's own sku; it is listed as foreign only so
        # the check states what is actually true of the image.
        label = 'it does not say "%s"' % s
        present = find(text, s) >= 0
        if s == 'M2012K11C':
            check(label + ' (SMBIOS sku not emitted)', not present)
        else:
            check(label, not present, 'found at 0x%x' % find(text, s))


def boot_image_layout(img):
    """(header_version, page_size, header_size, kernel_size) for an ANDROID! image.

    The header version is not at a fixed offset: v0-v2 carry page_size at 36 and
    header_version at 40, while v3/v4 replace both with header_size at 20 and put
    header_version at 40 as well. Reading page_size at 36 from a v3 image returns
    part of the os_version field, which is how an earlier version of this script
    "proved" a 2048-byte page on an image that has no such field.
    """
    kernel_size = struct.unpack('<I', img[8:12])[0]
    version = struct.unpack('<I', img[40:44])[0]
    if version >= 3:
        header_size = struct.unpack('<I', img[20:24])[0]
        return version, 4096, header_size, kernel_size
    page_size = struct.unpack('<I', img[36:40])[0]
    header_size = 1632 if version == 0 else 1648 if version == 1 else 1660
    return version, page_size, header_size, kernel_size


def check_img(path, fd_path):
    data = read(fd_path)
    img = read(path)
    print()
    print('%s: %d bytes' % (os.path.basename(path), len(img)))

    check('it is an Android boot image', img[:8] == b'ANDROID!', str(img[:8]))
    if img[:8] != b'ANDROID!':
        return

    version, page_size, header_size, kernel_size = boot_image_layout(img)
    print('  header_version %d, page_size %d, header_size %d, kernel_size %d'
          % (version, page_size, header_size, kernel_size))

    # This board launches through vendor_boot on Android 13, so the boot image
    # has to be v3+ (4096-byte pages). v1/2048 was rejected by the phone with
    # "Failed to load/authenticate boot image: Load Error"; see docs/install.md.
    check('the header version is 3 or later', version >= 3, str(version))
    check('the page size is 4096', page_size == 4096, str(page_size))
    check('the kernel section is not empty', kernel_size > 0, str(kernel_size))

    rnd = lambda n: (n + page_size - 1) // page_size * page_size   # noqa: E731
    kernel_off = rnd(header_size)
    check('the kernel section fits the file',
          kernel_off + kernel_size <= len(img),
          '%d > %d' % (kernel_off + kernel_size, len(img)))

    import gzip
    import io
    try:
        payload = gzip.GzipFile(
            fileobj=io.BytesIO(img[kernel_off:kernel_off + kernel_size])).read()
    except Exception as e:                       # noqa: BLE001 - report, do not raise
        check('the kernel section decompresses', False, str(e))
        return
    check('the kernel section decompresses', True)
    check('what comes out ends with the FD',
          payload.endswith(data), '%d bytes out' % len(payload))
    print('  note  %d bytes of BootShim precede the FD'
          % (len(payload) - len(data)))


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)

    print("The volume is this board's")
    check_fd(sys.argv[1])

    if len(sys.argv) > 2:
        print()
        print('The boot image wraps that same volume')
        check_img(sys.argv[2], sys.argv[1])

    if failures:
        print()
        print('%d failure(s)' % len(failures))
        return 1
    print()
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
