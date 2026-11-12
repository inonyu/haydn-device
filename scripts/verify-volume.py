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


def check_img(path, fd_path):
    data = read(fd_path)
    img = read(path)
    print()
    print('%s: %d bytes' % (os.path.basename(path), len(img)))

    check('it is an Android boot image', img[:8] == b'ANDROID!', str(img[:8]))
    kernel_size = struct.unpack('<I', img[8:12])[0]
    page_size = struct.unpack('<I', img[36:40])[0]
    check('the page size is 2048', page_size == 2048, str(page_size))
    check('the kernel section is not empty', kernel_size > 0, str(kernel_size))
    check('the kernel section fits the file', 2048 + kernel_size <= len(img))

    import gzip
    import io
    try:
        payload = gzip.GzipFile(fileobj=io.BytesIO(img[2048:2048 + kernel_size])).read()
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
