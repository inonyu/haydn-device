#!/usr/bin/env python3
"""Read, check and write Apple's ADT (the device tree the kernel is handed).

An ADT is a flat list of nodes, each:

    struct { uint32_t props; uint32_t children; }
    then `props` times: { char key[32]; uint32_t size; uint8_t value[size padded to 4] }
    then `children` child nodes, each the same shape.

The first property of every node is `name`, and it is what identifies it.
There is no magic, no length and no checksum: a wrong interpretation reads
the next node's header as a property and drifts.

This file exists so this repository can prove two things without a UniXNU
checkout beside it: that a haydn ADT parses, and that the reserved-memory
regions it carries are the ones the device tree generated.

    python3 scripts/adt.py check ADT
    python3 scripts/adt.py dump  ADT [PATH]
"""

import argparse
import struct
import sys


class Node:
    __slots__ = ('name', 'props', 'children')

    def __init__(self, name, props, children):
        self.name = name
        self.props = props
        self.children = children

    def get(self, key, default=None):
        for k, v in self.props:
            if k == key:
                return v
        return default

    def string(self, key, default=None):
        v = self.get(key)
        if v is None:
            return default
        return v.rstrip(b'\0').decode('utf-8', 'replace')

    def u32(self, key, default=None):
        v = self.get(key)
        if v is None or len(v) < 4:
            return default
        return struct.unpack_from('<I', v)[0]

    def reg_pairs(self, key='reg'):
        v = self.get(key)
        if v is None or len(v) % 16:
            return []
        out = []
        for i in range(0, len(v), 16):
            hi, lo, shi, slo = struct.unpack_from('<IIII', v, i)
            out.append(((hi << 32) | lo, (shi << 32) | slo))
        return out

    def walk(self, path=''):
        here = path + '/' + self.name
        yield here, self
        for child in self.children:
            yield from child.walk(here)


def parse(data):
    def visit(at):
        if at + 8 > len(data):
            raise SystemExit('ADT truncated at %d: no room for a node header' % at)
        count, children = struct.unpack_from('<II', data, at)
        at += 8
        props = []
        for _ in range(count):
            if at + 36 > len(data):
                raise SystemExit('ADT truncated at %d: no room for a property header' % at)
            key, size = struct.unpack_from('<32sI', data, at)
            at += 36
            if size > len(data) - at:
                raise SystemExit('ADT property %r claims %d bytes past the end' % (key, size))
            key = key.split(b'\0')[0].decode()
            props.append((key, data[at:at + size]))
            at += (size + 3) & ~3
        names = [k for k, _ in props]
        if not names or names[0] != 'name':
            raise SystemExit('ADT node without a leading name property')
        if len(set(names)) != len(names):
            raise SystemExit('ADT node with a duplicate property')
        node = Node(props[0][1].rstrip(b'\0').decode(), props, [])
        for _ in range(children):
            child, at = visit(at)
            node.children.append(child)
        return node, at

    node, end = visit(0)
    if end != len(data):
        raise SystemExit('ADT has %d bytes after the last node' % (len(data) - end))
    return node


def dump(node):
    props = [(k, v) for k, v in node.props if k != 'name']
    props = [('name', node.name.encode() + b'\0')] + props
    out = struct.pack('<II', len(props), len(node.children))
    for key, value in props:
        if len(key.encode()) > 31:
            raise SystemExit('ADT property name too long: ' + key)
        out += struct.pack('<32sI', key.encode(), len(value))
        out += value + bytes(-len(value) % 4)
    for child in node.children:
        out += dump(child)
    return out


def check(path):
    data = open(path, 'rb').read()
    root = parse(data)
    nodes = list(root.walk())
    print('%s: %d bytes, %d nodes, root %r' % (path, len(data), len(nodes), root.name))

    regs = [(p, n) for p, n in nodes if n.get('reg') is not None]
    print('  nodes with reg: %d' % len(regs))

    reserved = [n for p, n in nodes if n.get('reg') and p.count('/') >= 2 and 'reserved-memory' in p]
    if reserved:
        total = 0
        print('  reserved-memory regions: %d' % len(reserved))
        for node in reserved:
            for addr, size in node.reg_pairs():
                total += size
                tag = '  no-map' if node.get('no-map') is not None else ''
                print('    %-28s 0x%011x %7.1f MB%s' % (node.name, addr, size / 1048576.0, tag))
        print('    %-28s %13s %7.1f MB' % ('total', '', total / 1048576.0))
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)

    c = sub.add_parser('check', help='parse and summarise')
    c.add_argument('adt')

    d = sub.add_parser('dump', help='parse and print one subtree')
    d.add_argument('adt')
    d.add_argument('path', nargs='?', default='/')

    args = parser.parse_args()

    if args.command == 'check':
        return check(args.adt)

    root = parse(open(args.adt, 'rb').read())
    want = args.path.rstrip('/') or '/'
    for path, node in root.walk():
        if want == '/' or path == want or path.startswith(want + '/'):
            depth = max(path.count('/') - 1, 0)
            print('  ' * depth + path)
            for key, value in node.props:
                if key == 'name':
                    continue
                if len(value) == 4:
                    shown = '<0x%08x>' % struct.unpack('<I', value)[0]
                elif len(value) <= 64 and all(32 <= b < 127 or b == 0 for b in value):
                    shown = value.rstrip(b'\0').decode()
                else:
                    shown = value[:32].hex() + ('...' if len(value) > 32 else '')
                print('  ' * (depth + 1) + key + ' = ' + shown)
    return 0


if __name__ == '__main__':
    sys.exit(main())
