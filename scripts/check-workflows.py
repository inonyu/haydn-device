#!/usr/bin/env python3
"""Check the workflows: they parse, and they agree with the repository.

A workflow is code that only runs on push, so a typo in it costs a red build
and an hour. The checks here are the ones that can be made without GitHub:

  * every workflow parses as YAML;
  * every file a step names actually exists;
  * the inline haydn.toml a step writes matches platform/haydnPkg/binaries.toml
    and the FD numbers in haydn.dsc, so the two cannot drift.

    python3 scripts/check-workflows.py
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WORKFLOWS = os.path.join(ROOT, '.github', 'workflows')

failures = []


def check(name, ok, detail=''):
    if ok:
        print('  ok    ' + name)
    else:
        print('  FAIL  ' + name + '  ' + detail)
        failures.append(name)


try:
    import yaml
except ImportError:
    print('  skip  PyYAML is not installed; only the file checks run')
    yaml = None


def read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


files = sorted(f for f in os.listdir(WORKFLOWS) if f.endswith(('.yml', '.yaml')))
print('Workflows: %d' % len(files))
check('there is at least one', len(files) > 0)

for name in files:
    path = os.path.join(WORKFLOWS, name)
    text = read(path)

    if yaml is not None:
        try:
            doc = yaml.safe_load(text)
            check('%s parses' % name, isinstance(doc, dict))
        except Exception as exc:
            check('%s parses' % name, False, str(exc))
            continue
    else:
        doc = None

    # Every path a step names must be here. This is the mistake that would
    # otherwise only show up as a red run on push.
    for m in re.finditer(r'python3 (tests/[a-z-]+\.py|scripts/[a-z-]+\.py)', text):
        rel = m.group(1)
        check('%s: %s exists' % (name, rel), os.path.exists(os.path.join(ROOT, rel)), rel)

    for m in re.finditer(r'diff /tmp/from-dtb\.dtsi (\S+)', text):
        rel = m.group(1)
        check('%s: %s exists' % (name, rel), os.path.exists(os.path.join(ROOT, rel)), rel)

    # The inline device config must agree with the repository's own numbers.
    inline = re.search(r"cat > (\S+) <<'EOF'\n(.*?)\n\s*EOF", text, re.S)
    if inline:
        body = inline.group(2)
        dsc = read(os.path.join(ROOT, 'platform', 'haydnPkg', 'haydn.dsc'))
        dsc_base = int(re.search(r'FD_BASE\s*=\s*(\S+)', dsc).group(1), 16)
        dsc_size = int(re.search(r'FD_SIZE\s*=\s*(\S+)', dsc).group(1), 16)

        # Compare as numbers, not as text: 0x200000 and 0x00200000 are the same
        # flash device, and a checker that cannot see that is a checker that
        # gets disabled.
        inline_base = re.search(r'base\s*=\s*(0x[0-9a-fA-F]+)', body)
        inline_size = re.search(r'size\s*=\s*(0x[0-9a-fA-F]+)', body)
        check('%s: the inline config gives a base' % name, inline_base is not None)
        check('%s: the inline config gives a size' % name, inline_size is not None)
        if inline_base and inline_size:
            check('%s: the inline base is the DSC\'s' % name,
                  int(inline_base.group(1), 16) == dsc_base,
                  '%s vs %s' % (inline_base.group(1), hex(dsc_base)))
            check('%s: the inline size is the DSC\'s' % name,
                  int(inline_size.group(1), 16) == dsc_size,
                  '%s vs %s' % (inline_size.group(1), hex(dsc_size)))

    # The Binaries the workflow seeds must be a set that exists upstream.
    m = re.search(r'cp -r Binaries/(\w+) Binaries/(\w+)', text)
    if m:
        src, dst = m.group(1), m.group(2)
        check('%s: seeds Binaries/%s into Binaries/%s' % (name, src, dst), True)
        check('%s: the source is the venus set, the same SoC' % name,
              src == 'venus', src)

print()
print('haydnPkg has what a build needs, and nothing it cannot find')
PKG = os.path.join(ROOT, 'platform', 'haydnPkg')
dsc = read(os.path.join(PKG, 'haydn.dsc'))
fdf = read(os.path.join(PKG, 'haydn.fdf'))
check('the DSC has a FLASH_DEFINITION', 'FLASH_DEFINITION' in dsc)
check('it points at haydn.fdf', 'haydnPkg/haydn.fdf' in dsc)
check('it includes LahainaPkg', '!include LahainaPkg/LahainaPkg.dsc.inc' in dsc)
check('the FDF includes the three include files',
      all(('!include Include/%s.inc' % n) in fdf for n in ('APRIORI', 'DXE', 'RAW')))
for _n in ('APRIORI', 'DXE', 'RAW'):
    _p = os.path.join(PKG, 'Include', _n + '.inc')
    check('Include/%s.inc exists' % _n, os.path.exists(_p), _p)
    if os.path.exists(_p):
        _b = read(_p)
        check('  %s has no venus paths left' % _n, 'Binaries/venus/' not in _b)
        check('  %s names Binaries/haydn/' % _n, 'Binaries/haydn/' in _b)

print()
print('The components UniXNU would add are commented out, not referenced')
# UniXNUPkg and DarwinBootPkg are UniXNU's; they are not in the Mu-Silicium
# tree, so a build that references them cannot succeed there. Both files name
# them in comments so the place to put them back is obvious.
dsc_refs = [l.strip() for l in dsc.splitlines() if 'UniXNUPkg' in l or 'DarwinBootPkg' in l]
check('the DSC mentions them', len(dsc_refs) > 0)
check('every DSC mention is commented out',
      all(r.startswith('#') for r in dsc_refs),
      str([r for r in dsc_refs if not r.startswith('#')]))
fdf_refs = [l.strip() for l in fdf.splitlines() if 'UniXNUPkg' in l or 'DarwinBootPkg' in l]
check('the FDF names where they go', len(fdf_refs) > 0)
check('every FDF mention is commented out',
      all(r.startswith('#') for r in fdf_refs),
      str([r for r in fdf_refs if not r.startswith('#')]))

print()
print('The build workflow is honest about failing')
build_path = os.path.join(WORKFLOWS, 'build.yml')
if os.path.exists(build_path):
    text = read(build_path)
    check('it says the first run is expected to fail',
          'expected to fail' in text.lower())
    check('it continues on error so the log is still kept',
          'continue-on-error: true' in text)
    check('it uploads the log even when the build failed',
          'if: always()' in text)
    check('it warns the seeded volume must not be flashed',
          'must not be flashed' in text)
    check('it runs the repository checks first',
          'needs: checks' in text)
else:
    check('build.yml exists', False)

if failures:
    print()
    print('%d failure(s)' % len(failures))
    sys.exit(1)
print()
print('all checks passed')
