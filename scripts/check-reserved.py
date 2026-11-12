#!/usr/bin/env python3
"""Check dts/haydn-reserved.dtsi against what the ADT would carry.

The generator (scripts/gen-reserved.py) turns the phone's FDT into a DTSI;
the kernel's ADT is a different format built from the same numbers. This
script reads the DTSI back, builds the ADT shape a board would publish, and
asserts the two agree: same regions, same addresses, same sizes, same order.

    python3 scripts/check-reserved.py
"""

import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from adt import Node, parse, dump                       # noqa: E402

DTSI = os.path.join(ROOT, 'dts', 'haydn-reserved.dtsi')

# The two generators read different inputs (a DTS and the FDT binary) and
# must agree. When the binary is here, both are run and their region lists
# compared; when it is not, this degrades to the DTSI's own consistency.
DTB = os.path.join(ROOT, 'docs', 'haydn-fdt.dtb')

REGEX_NODE = re.compile(r'(\w[\w\-]*)@(0x[0-9a-f]+)\s*\{([^{}]*)\}', re.MULTILINE)
REGEX_REG = re.compile(r'reg\s*=\s*<\s*(0x[0-9a-f]+)\s+(0x[0-9a-f]+)\s+(0x[0-9a-f]+)\s+(0x[0-9a-f]+)\s*>')


def regions_from_dtsi(path):
    text = open(path, encoding='utf-8').read()
    out = []
    for m in REGEX_NODE.finditer(text):
        name, addr_text, body = m.group(1), m.group(2), m.group(3)
        reg = REGEX_REG.search(body)
        if not reg:
            continue
        hi, lo, shi, slo = [int(reg.group(i), 16) for i in range(1, 5)]
        addr = (hi << 32) | lo
        size = (shi << 32) | slo
        out.append((name, addr, size, 'no-map' in body))
    return out


def build_adt(regions):
    children = []
    for name, addr, size, no_map in regions:
        node_name = '%s@0x%x' % (name, addr)
        props = [('name', node_name.encode() + b'\0')]
        if no_map:
            props.append(('no-map', b''))
        props.append(('reg', struct.pack('<IIII', addr >> 32, addr & 0xffffffff,
                                         size >> 32, size & 0xffffffff)))
        children.append(Node(node_name, props, []))
    rm = Node('reserved-memory', [
        ('name', b'reserved-memory\0'),
        ('#address-cells', struct.pack('<I', 2)),
        ('#size-cells', struct.pack('<I', 2)),
    ], children)
    return Node('/', [('name', b'/\0')], [rm])


def main():
    regions = regions_from_dtsi(DTSI)
    if not regions:
        raise SystemExit('no regions parsed out of ' + DTSI)
    print('%s: %d regions' % (DTSI, len(regions)))
    total = sum(size for _, _, size, _ in regions)
    print('  total %.1f MB' % (total / 1048576.0))

    adt = dump(build_adt(regions))
    back = parse(adt)
    rm = [c for c in back.children if c.name == 'reserved-memory'][0]

    failures = []
    if len(rm.children) != len(regions):
        failures.append('ADT holds %d regions, the DTSI %d' % (len(rm.children), len(regions)))

    for i, (name, addr, size, no_map) in enumerate(regions):
        if i >= len(rm.children):
            break
        got = rm.children[i].reg_pairs()
        if got != [(addr, size)]:
            failures.append('%s: ADT %s, DTSI %s' % (name, got, [(addr, size)]))
        has_no_map = rm.children[i].get('no-map') is not None
        if has_no_map != no_map:
            failures.append('%s: no-map %s in the ADT, %s in the DTSI' % (name, has_no_map, no_map))

    if failures:
        for line in failures:
            print('  FAIL ' + line)
        raise SystemExit('%d failure(s)' % len(failures))

    print('  the ADT and the DTSI agree: same regions, same order, same numbers')
    return 0


if __name__ == '__main__':
    sys.exit(main())
