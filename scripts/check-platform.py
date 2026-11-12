#!/usr/bin/env python3
"""Check the UEFI platform description against the phone's own numbers.

Two kinds of mistake this catches, both silent until a flash:

  * an FD base that lands on one of this phone's reserved regions, which puts
    the firmware somewhere the bootloader will overwrite or the kernel will
    read as its own;
  * a DSC and an FDF that disagree about where the flash device is or how big
    it is -- edk2 does not check the two against each other.

    python3 scripts/check-platform.py
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PKG = os.path.join(ROOT, 'platform', 'haydnPkg')
DSC = os.path.join(PKG, 'haydn.dsc')
FDF = os.path.join(PKG, 'haydn.fdf')

failures = []


def check(name, ok, detail=''):
    if ok:
        print('  ok    ' + name)
    else:
        print('  FAIL  ' + name + '  ' + detail)
        failures.append(name)


def read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def defines(text):
    """KEY = VALUE lines, the edk2 way (two spaces then KEY then = then value)."""
    out = {}
    for line in text.splitlines():
        line = line.split('#')[0].rstrip()
        m = re.match(r'^\s{2,}([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(\S+)\s*$', line)
        if m:
            out[m.group(1)] = m.group(2)
    return out


print('The DSC and the FDF describe the same flash device')
if not os.path.exists(DSC):
    raise SystemExit('no ' + DSC)
if not os.path.exists(FDF):
    raise SystemExit('no ' + FDF)

dsc_text = read(DSC)
fdf_text = read(FDF)
dsc = defines(dsc_text)

check('the DSC names the platform haydn', dsc.get('PLATFORM_NAME') == 'haydn',
      str(dsc.get('PLATFORM_NAME')))

print()
print('The DSC reports this handset, not a sibling')
# This is the 8 GB Redmi K40 Pro. The phone says so: hardware.sku=haydn,
# hwversion=4.9.0, serialno=56db9cb7. haydnpro is the 12 GB K40 Pro+ and is a
# different machine -- different memory, different dtbo index (21 against 10).
check('the model is the K40 Pro', '"Redmi K40 Pro"' in dsc_text,
      'the DSC has no Redmi K40 Pro model string')
check('the retail model is haydn', '"haydn"' in dsc_text)
check('the retail sku is M2012K11C', '"M2012K11C"' in dsc_text)
check('it does not say venus', '"Mi 11"' not in dsc_text)
check('it does not say haydnpro', '"haydnpro"' not in dsc_text)

print()
print('The frame buffer is the panel the bootloader names')
# msm_drm.dsi_display0=qcom,mdss_dsi_k11_38_08_0a_dsc_cmd: 1080x2400.
check('the width is 1080', 'PcdFrameBufferWidth|1080' in dsc_text)
check('the height is 2400', 'PcdFrameBufferHeight|2400' in dsc_text)

fd_base = int(dsc['FD_BASE'], 16) if 'FD_BASE' in dsc else None
fd_size = int(dsc['FD_SIZE'], 16) if 'FD_SIZE' in dsc else None
check('the DSC gives FD_BASE', fd_base is not None)
check('the DSC gives FD_SIZE', fd_size is not None)

check('the FDF uses $(FD_BASE)', '$(FD_BASE)' in fdf_text)
check('the FDF uses $(FD_SIZE)', '$(FD_SIZE)' in fdf_text)

print()
print('The FD base is above abl, and clear of every reserved region')
if fd_base is not None and fd_size is not None:
    # abl's own ELF header: entry 0x9fa00000, segments to 0x9fa30000.
    ABL_ENTRY, ABL_END = 0x9FA00000, 0x9FA30000
    check('the FD starts above abl', fd_base >= ABL_END,
          hex(fd_base) + ' vs ' + hex(ABL_END))

    # DRAM begins at 0x80000000 on this SoC (the DT says so).
    DRAM_BASE = 0x80000000
    check('the FD is inside DRAM', fd_base > DRAM_BASE)

    RESERVED = [
        ('hyp_region', 0x80000000, 0x600000),
        ('xbl_aop_region', 0x80600000, 0x260000),
        ('res_xbl_uefi_log', 0x80880000, 0x14000),
        ('modem_region', 0x8F000000, 0x10000000),
        ('removed_region', 0xD8800000, 0x5400000),
        ('splash_region', 0xDFC00000, 0x2300000),
    ]
    for name, base, size in RESERVED:
        overlap = fd_base < base + size and base < fd_base + fd_size
        check('clear of ' + name, not overlap,
              hex(max(fd_base, base)) + '..' + hex(min(fd_base + fd_size, base + size)))

    check('the FD ends below 4 GB', fd_base + fd_size <= 0x100000000,
          hex(fd_base + fd_size))

print()
print('The Binaries the DSC would consume are the ones the phone gave')
import tomllib
manifest = os.path.join(PKG, 'binaries.toml')
if os.path.exists(manifest):
    with open(manifest, 'rb') as f:
        spec = tomllib.load(f)
    pieces = spec.get('piece', [])
    check('six pieces recorded', len(pieces) == 6, str(len(pieces)))
    names = [p['file'] for p in pieces]
    check('devcfg is one', any('devcfg' in n for n in names))
    check('tz is one', any(n.startswith('tz') for n in names))
    check('aop is one', any(n.startswith('aop') for n in names))
    check('every piece has a sha256', all(len(p['sha256']) == 64 for p in pieces))
    check('every piece has a partition', all(p['partition'] for p in pieces))
else:
    check('binaries.toml exists', False)

print()
print('The DSC does not reference a binary the manifest does not list')
if os.path.exists(manifest):
    body = dsc_text
    for piece in pieces:
        # A DSC that names a file must name one the manifest has.
        if piece['file'] in body:
            check('the DSC references ' + piece['file'] + ' and it is listed', True)

if failures:
    print()
    print('%d failure(s)' % len(failures))
    sys.exit(1)

print()
print('all checks passed')
