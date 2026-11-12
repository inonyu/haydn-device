#!/usr/bin/env python3
"""Check that the firmware files put under Platform/haydnPkg/Binaries/ are the
ones platform/haydnPkg/binaries.toml describes.

The binaries are Qualcomm's and the phone's, so they are not in this
repository. What is in it is the record: which partition each came from, how
many bytes of it were real, and the SHA-256. Whoever brings the files does this
and finds out immediately whether they have the right ones.

    python3 scripts/verify-binaries.py                 # check what is there
    python3 scripts/verify-binaries.py --dir SOME/DIR  # somewhere else

A missing file is reported as missing, not as a failure: this repository has
never contained them.
"""

import argparse
import hashlib
import os
import sys
import tomllib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MANIFEST = os.path.join(ROOT, 'platform', 'haydnPkg', 'binaries.toml')
DEFAULT_DIR = os.path.join(ROOT, 'platform', 'haydnPkg', 'Binaries')


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--dir', default=DEFAULT_DIR)
    parser.add_argument('--strict', action='store_true',
                        help='exit non-zero when a piece is present but wrong')
    args = parser.parse_args()

    with open(MANIFEST, 'rb') as f:
        spec = tomllib.load(f)

    pieces = spec.get('piece', [])
    if not pieces:
        raise SystemExit('no pieces in ' + MANIFEST)

    print('%s: %d pieces expected' % (os.path.basename(MANIFEST), len(pieces)))
    print('  looking in %s' % args.dir)
    print()

    present = wrong = missing = 0
    for piece in pieces:
        path = os.path.join(args.dir, piece['file'])
        if not os.path.exists(path):
            missing += 1
            print('  missing   %-24s %s' % (piece['file'], piece['partition']))
            continue

        size = os.path.getsize(path)
        digest = sha256(path)
        if digest != piece['sha256']:
            wrong += 1
            print('  WRONG     %-24s %s' % (piece['file'], piece['partition']))
            print('              expected %s' % piece['sha256'])
            print('              got      %s' % digest)
            print('              %d bytes (the manifest says %d)' %
                  (size, piece['content_bytes']))
            continue

        present += 1
        print('  ok        %-24s %s  %d bytes' %
              (piece['file'], piece['partition'], size))

    print()
    print('%d ok, %d wrong, %d missing' % (present, wrong, missing))

    if missing and present == 0:
        print('none of the binaries are here, which is expected: this'
              ' repository does not carry them.')
    if wrong:
        print('a wrong hash means the file is not the one this phone produced.')
        return 1 if args.strict else 0
    return 0


if __name__ == '__main__':
    sys.exit(main())
