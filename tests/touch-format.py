#!/usr/bin/env python3
"""The report format and the CRC, tested without a compiler or a phone.

Both are pure functions of bytes, so both can be checked here. This file
exists because an earlier draft of the driver read the FTS coordinate fields
as 12-bit values: it compiled, it looked right, and it decoded every touch to
the wrong place. The 15-bit layout is what the header documents and what this
test pins down.

    python3 tests/touch-format.py
"""

import sys

# From package/touch/haydn.touch.h
REPORT_X = 8640
REPORT_Y = 19200
MAX_TOUCHES = 10
REPORT_LEN = 2 + 6 * MAX_TOUCHES

EVENT_DOWN, EVENT_UP, EVENT_CONTACT = 0, 1, 2


def crc16_mcrf4xx(data: bytes) -> int:
    """Polynomial 0x8408 reflected, initial 0xffff: what fts_crc() computes."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc >> 1) ^ 0x8408) if (crc & 1) else (crc >> 1)
            crc &= 0xFFFF
    return crc


def build_point(x: int, y: int, finger_id: int, event: int) -> bytes:
    """Pack one point the way the chip does: 15 bits per axis."""
    return bytes([
        ((event & 0x3) << 6) | ((x >> 11) & 0x0F),      # E_XH
        (x >> 3) & 0xFF,                                 # XL
        ((finger_id & 0x0F) << 4) | ((y >> 11) & 0x0F),  # ID_YH
        (y >> 3) & 0xFF,                                 # YL
        ((x & 0x7) << 5) | ((y & 0x7) << 2),             # PRE
        0x10,                                            # AREA
    ])


def decode_point(t: bytes):
    """The arithmetic in haydn_touch_decode(), kept in step with the driver."""
    finger_id = (t[2] >> 4) & 0x0F
    event = (t[0] >> 6) & 0x3
    x = ((t[0] & 0x0F) << 11) | (t[1] << 3) | (t[4] >> 5)
    y = ((t[2] & 0x0F) << 11) | (t[3] << 3) | ((t[4] & 0x1C) >> 2)
    return x, y, finger_id, event


def normalise(value: int, extent: int) -> int:
    """What the driver publishes: 0..65535 across the report space."""
    value = min(value, extent - 1)
    return (value * 65535) // (extent - 1)


failures = []


def check(name: str, ok: bool, detail: str = '') -> None:
    if ok:
        print(f'  ok    {name}')
    else:
        print(f'  FAIL  {name}  {detail}')
        failures.append(name)


print('CRC-16 (MCRF4XX: poly 0x8408 reflected, init 0xffff)')
check("'123456789' is 0x6f91", crc16_mcrf4xx(b'123456789') == 0x6F91,
      hex(crc16_mcrf4xx(b'123456789')))
check('empty is 0xffff', crc16_mcrf4xx(b'') == 0xFFFF)

print()
print('A 12-bit reading cannot hold either axis')
check('15 bits reach 32767, past 8640', 0x7FFF > REPORT_X)
check('15 bits reach 32767, past 19200', 0x7FFF > REPORT_Y)
check('12 bits top out at 4095, below both', 0xFFF < REPORT_X and 0xFFF < REPORT_Y)

print()
print('15-bit round trip')
cases = [
    (0, 0, 0, EVENT_DOWN),
    (4320, 9600, 0, EVENT_DOWN),
    (1080, 2400, 1, EVENT_CONTACT),
    (8639, 19199, 3, EVENT_CONTACT),
    (12345, 6789, 4, EVENT_DOWN),
    (32767, 32767, 5, EVENT_CONTACT),
]
for x, y, finger, event in cases:
    packed = build_point(x, y, finger, event)
    got = decode_point(packed)
    check(f'({x}, {y}) id {finger} -> {packed.hex()}',
          got == (x, y, finger, event), str(got))

print()
print('Normalisation to the platform digitizer space')
check('centre of x', normalise(REPORT_X // 2, REPORT_X) == 32771,
      str(normalise(REPORT_X // 2, REPORT_X)))
check('left edge', normalise(0, REPORT_X) == 0)
check('right edge', normalise(REPORT_X - 1, REPORT_X) == 65535)
check('past the edge clamps', normalise(REPORT_X + 100, REPORT_X) == 65535)

print()
print('Report header')
check('report length is 2 + 6*10', REPORT_LEN == 62)
all_ones = bytes([0x00, 0xFF, 0xFF, 0xFF])
check('all-ones header is not a report',
      all_ones[1] == 0xFF and all_ones[2] == 0xFF and all_ones[3] == 0xFF)

if failures:
    print(f'{len(failures)} failure(s)')
    sys.exit(1)
print('all checks passed')
