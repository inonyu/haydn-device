#!/usr/bin/env python3
"""The UFS whitelist and the CDB builders, tested without a controller.

The whitelist is the one thing in the storage driver whose failure would be
silent and dangerous: a command that writes, let through, changes the phone.
So it is written as a pure function of five bytes and driven from here.

    python3 tests/ufs-whitelist.py
"""

import sys

# From package/storage/haydn.ufs.h
UPIU_FLAG_READ = 0x40
UPIU_FLAG_WRITE = 0x20
LUN_WELL_KNOWN = 0x80

DD_NONE, DD_OUT, DD_IN = 0, 1, 2      # UTRD_DD_* >> 25

SCSI_TEST_UNIT_READY = 0x00
SCSI_REQUEST_SENSE = 0x03
SCSI_INQUIRY = 0x12
SCSI_READ_CAPACITY10 = 0x25
SCSI_READ10 = 0x28
SCSI_READ16 = 0x88
SCSI_READ_CAPACITY16 = 0x9E
SCSI_WRITE10 = 0x2A
SCSI_WRITE16 = 0x8A
SCSI_UNMAP = 0x42
SCSI_FORMAT_UNIT = 0x04
SCSI_SYNC_CACHE = 0x35


def permitted(opcode, lun, upiu_flags, direction):
    """haydn_ufs_permitted(), kept in step with the driver."""
    if upiu_flags & UPIU_FLAG_WRITE:
        return False
    if direction == DD_OUT:
        return False
    if lun & LUN_WELL_KNOWN:
        return False

    if opcode in (SCSI_READ10, SCSI_READ16):
        return bool(upiu_flags & UPIU_FLAG_READ) and direction == DD_IN
    if opcode in (SCSI_TEST_UNIT_READY, SCSI_REQUEST_SENSE, SCSI_INQUIRY,
                  SCSI_READ_CAPACITY10, SCSI_READ_CAPACITY16):
        return direction != DD_OUT
    return False


def build_read10(lba, blocks):
    """haydn_ufs_build_read10(): a 16-byte CDB."""
    cdb = bytearray(16)
    cdb[0] = SCSI_READ10
    cdb[2] = (lba >> 24) & 0xFF
    cdb[3] = (lba >> 16) & 0xFF
    cdb[4] = (lba >> 8) & 0xFF
    cdb[5] = lba & 0xFF
    cdb[7] = (blocks >> 8) & 0xFF
    cdb[8] = blocks & 0xFF
    return bytes(cdb)


failures = []


def check(name, ok, detail=''):
    if ok:
        print(f'  ok    {name}')
    else:
        print(f'  FAIL  {name}  {detail}')
        failures.append(name)


print('Commands the driver builds must pass')
check('READ(10) LUN 0, IN', permitted(SCSI_READ10, 0, UPIU_FLAG_READ, DD_IN))
check('READ(16) LUN 0, IN', permitted(SCSI_READ16, 0, UPIU_FLAG_READ, DD_IN))
check('TEST UNIT READY', permitted(SCSI_TEST_UNIT_READY, 0, 0, DD_NONE))
check('INQUIRY', permitted(SCSI_INQUIRY, 0, 0, DD_IN))
check('READ CAPACITY(10)', permitted(SCSI_READ_CAPACITY10, 0, 0, DD_IN))
check('READ CAPACITY(16)', permitted(SCSI_READ_CAPACITY16, 0, 0, DD_IN))
check('REQUEST SENSE', permitted(SCSI_REQUEST_SENSE, 0, 0, DD_IN))

print()
print('Every way of writing must be refused')
check('WRITE(10)', not permitted(SCSI_WRITE10, 0, UPIU_FLAG_WRITE, DD_OUT))
check('WRITE(16)', not permitted(SCSI_WRITE16, 0, UPIU_FLAG_WRITE, DD_OUT))
check('UNMAP', not permitted(SCSI_UNMAP, 0, UPIU_FLAG_WRITE, DD_OUT))
check('FORMAT UNIT', not permitted(SCSI_FORMAT_UNIT, 0, UPIU_FLAG_WRITE, DD_OUT))
check('SYNC CACHE', not permitted(SCSI_SYNC_CACHE, 0, 0, DD_NONE))

print()
print('A read that lies about itself must be refused')
check('READ(10) with the write flag',
      not permitted(SCSI_READ10, 0, UPIU_FLAG_WRITE, DD_IN))
check('READ(10) with direction OUT',
      not permitted(SCSI_READ10, 0, UPIU_FLAG_READ, DD_OUT))
check('READ(10) with no READ flag',
      not permitted(SCSI_READ10, 0, 0, DD_IN))

print()
print('Well-known logical units must be refused')
for name, lun in [('REPORT LUNS', 0x80 | 2), ('BOOT', 0x80 | 0x30),
                  ('RPMB', 0x80 | 0x44), ('UFS DEVICE', 0x80 | 0x50)]:
    check(f'READ(10) to {name}',
          not permitted(SCSI_READ10, lun, UPIU_FLAG_READ, DD_IN), hex(lun))

print()
print('Anything not on the list must be refused')
for opcode, name in [(0xFF, 'vendor'), (0x7F, 'variable length'),
                     (0xA0, 'report luns CDB'), (0x1B, 'start stop unit')]:
    check(f'opcode {name}', not permitted(opcode, 0, 0, DD_NONE))

print()
print('READ(10) CDB layout')
cdb = build_read10(0x12345678, 0x0102)
check('length is 16 bytes', len(cdb) == 16)
check('opcode is 0x28', cdb[0] == SCSI_READ10)
check('LBA big endian at 2..5', cdb[2:6] == bytes([0x12, 0x34, 0x56, 0x78]), cdb[2:6].hex())
check('blocks big endian at 7..8', cdb[7:9] == bytes([0x01, 0x02]), cdb[7:9].hex())
check('the rest is zero', cdb[1] == 0 and cdb[6] == 0 and cdb[9:] == bytes(7))

print()
print('The board\'s own numbers')
UFSHC_PHYS, UFSHC_SIZE = 0x1D84000, 0x3000
PHY_PHYS, PHY_SIZE = 0x1D87000, 0xE10
check('controller inside its region', UFSHC_SIZE == 0x3000)
check('PHY is the corrected address', PHY_PHYS == 0x1D87000, hex(PHY_PHYS))
check('PHY is not the wrong one', PHY_PHYS != 0x1D80000)
check('PHY fits its declared size', PHY_SIZE == 0xE10)
# The PHY begins exactly where the controller's register block ends:
# 0x1d84000 + 0x3000 = 0x1d87000. Adjacent, not merely nearby, which is what
# the live platform listing shows (1d84000.ufshc followed by 1d87000.ufsphy_mem).
check('PHY begins where the controller ends',
      PHY_PHYS == UFSHC_PHYS + UFSHC_SIZE,
      hex(PHY_PHYS) + ' vs ' + hex(UFSHC_PHYS + UFSHC_SIZE))
check('the two regions do not overlap', PHY_PHYS >= UFSHC_PHYS + UFSHC_SIZE)

if failures:
    print(f'{len(failures)} failure(s)')
    sys.exit(1)
print('all checks passed')
