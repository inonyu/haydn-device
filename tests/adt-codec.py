#!/usr/bin/env python3
"""The ADT codec, round-tripped and checked against the device tree.

An ADT has no magic and no checksum: a reader that gets the layout wrong reads
the next node's header as a property and drifts through the rest of the file
without ever reporting an error. So the codec is exercised here on trees of
known shape, including the shape this board actually produces.

    python3 tests/adt-codec.py
"""

import struct
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
from adt import Node, parse, dump                       # noqa: E402

failures = []


def check(name, ok, detail=''):
    if ok:
        print('  ok    ' + name)
    else:
        print('  FAIL  ' + name + '  ' + detail)
        failures.append(name)


def P(name, value):
    return (name, value)


def region(name, addr, size, no_map=True):
    props = [P('name', name.encode() + b'\0')]
    if no_map:
        props.append(P('no-map', b''))
    props.append(P('reg', struct.pack('<IIII', addr >> 32, addr & 0xffffffff,
                                       size >> 32, size & 0xffffffff)))
    return Node(name, props, [])


print('A minimal tree round-trips')
root = Node('/', [P('name', b'/\0')], [])
blob = dump(root)
back = parse(blob)
check('root name', back.name == '/')
check('no children', back.children == [])
check('the bytes come back the same', dump(back) == blob)

print()
print('Properties of every width and alignment')
leaf = Node('leaf', [
    P('name', b'leaf\0'),
    P('empty', b''),
    P('one', b'A'),
    P('three', b'abc'),
    P('four', b'abcd'),
    P('five', b'abcde'),
    P('word', struct.pack('<I', 0xdeadbeef)),
], [])
blob = dump(Node('/', [P('name', b'/\0')], [leaf]))
back = parse(blob)
got = back.children[0]
check('empty survives', got.get('empty') == b'')
check('one byte survives', got.get('one') == b'A')
check('three bytes survive', got.get('three') == b'abc')
check('four bytes survive', got.get('four') == b'abcd')
check('five bytes survive', got.get('five') == b'abcde')
check('a word survives', got.u32('word') == 0xdeadbeef)
check('padding is there', len(blob) % 4 == 0)

print()
print('reg pairs are 64-bit address and size')
big = region('big', 0x200000000, 0x180000000)
back = parse(dump(Node('/', [P('name', b'/\0')], [big]))).children[0]
check('a 33-bit address round-trips', back.reg_pairs() == [(0x200000000, 0x180000000)],
      str(back.reg_pairs()))

print()
print('The tree this board generates: 21 regions, 607.7 MB')
REGIONS = [
    ('hyp_region', 0x80000000, 0x600000),
    ('xbl_aop_region', 0x80600000, 0x260000),
    ('cmd_db', 0x80860000, 0x20000),
    ('xbl_uefi_log', 0x80880000, 0x14000),
    ('smem_region', 0x80900000, 0x200000),
    ('cpucp_fw', 0x80b00000, 0x100000),
    ('cdsp_secure_heap', 0x80c00000, 0x4600000),
    ('pil_camera', 0x85200000, 0x500000),
    ('pil_video', 0x85700000, 0x500000),
    ('pil_cvp', 0x85c00000, 0x500000),
    ('pil_adsp', 0x86100000, 0x3900000),
    ('pil_slpi', 0x89a00000, 0x2f00000),
    ('pil_cdsp', 0x8c900000, 0x1e00000),
    ('pil_ipa_fw', 0x8e700000, 0x10000),
    ('pil_ipa_gsi', 0x8e710000, 0xa000),
    ('pil_gpu', 0x8e71a000, 0x2000),
    ('pil_spss', 0x8e800000, 0x100000),
    ('modem_region', 0x8f000000, 0x10000000),
    ('removed_region', 0xd8800000, 0x5400000),
    ('splash_region', 0xdfc00000, 0x2300000),
    ('dfps_data_region', 0xe1f00000, 0x100000),
]

rm = Node('reserved-memory', [
    P('name', b'reserved-memory\0'),
    P('#address-cells', struct.pack('<I', 2)),
    P('#size-cells', struct.pack('<I', 2)),
], [region(n, a, s) for n, a, s in REGIONS])

tree = Node('/', [P('name', b'/\0')], [
    Node('chosen', [P('name', b'chosen\0')], []),
    rm,
])
back = parse(dump(tree))
back_rm = [c for c in back.children if c.name == 'reserved-memory'][0]
check('21 regions survive', len(back_rm.children) == 21, str(len(back_rm.children)))
total_from_tree = sum(s for _, s in [pair for n in back_rm.children for pair in n.reg_pairs()])
total_from_list = sum(s for _, _, s in REGIONS)
check('the total is the same', total_from_tree == total_from_list,
      '%d vs %d' % (total_from_tree, total_from_list))
check('the total is 607.7 MB', round(total_from_tree / 1048576.0, 1) == 607.7,
      str(round(total_from_tree / 1048576.0, 1)))

order_ok = all(
    back_rm.children[i].reg_pairs()[0][0] == REGIONS[i][1]
    for i in range(len(REGIONS))
)
check('the order is preserved', order_ok)

print()
print('Malformed input is refused, not drifted through')
good = dump(tree)

truncated = good[:-8]
try:
    parse(truncated)
    check('a truncated ADT is refused', False)
except SystemExit:
    check('a truncated ADT is refused', True)

extra = good + b'JUNKJUNK'
try:
    parse(extra)
    check('trailing bytes are refused', False)
except SystemExit:
    check('trailing bytes are refused', True)

bad_first = bytearray(good)
bad_first[8:40] = b'x' * 32          # the first property's key is no longer 'name'
try:
    parse(bytes(bad_first))
    check('a node without a leading name is refused', False)
except SystemExit:
    check('a node without a leading name is refused', True)

print()
print('A property name longer than 31 bytes cannot be written')
too_long = Node('x', [P('name', b'x\0'), P('a' * 32, b'')], [])
try:
    dump(too_long)
    check('a 32-byte key is refused', False)
except SystemExit:
    check('a 32-byte key is refused', True)

if failures:
    print('%d failure(s)' % len(failures))
    sys.exit(1)
print('all checks passed')
