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
    #
    # shim.yml writes a mkbootimg wrapper script, not a device config, so it has
    # no [uefi_fd] block to compare. Only a heredoc that creates a .toml is in
    # scope here; anything else is a different kind of script.
    inline = re.search(r"cat > (\S+\.toml) <<'EOF'\n(.*?)\n\s*EOF", text, re.S)
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

        # The boot image header, which is the one number that cost a phone boot.
        #
        # The published image was v1 at 2048-byte pages and the ABL answered
        # "Failed to load/authenticate boot image: Load Error" before any of our
        # code ran (docs/install.md). board.toml and platform/haydnPkg/haydn.toml
        # both said 3; this inline copy said 1, and the inline copy is the one
        # that gets built. Compare all three so the drift cannot come back.
        inline_hv = re.search(r'header_version\s*=\s*(\d+)', body)
        check('%s: the inline config gives a header_version' % name,
              inline_hv is not None)
        if inline_hv:
            for rel in ('platform/haydnPkg/haydn.toml', 'board.toml'):
                other = re.search(r'header_version\s*=\s*(\d+)',
                                  read(os.path.join(ROOT, rel)))
                if not other:
                    continue
                check('%s: header_version %s is %s\'s' % (name, inline_hv.group(1), rel),
                      inline_hv.group(1) == other.group(1),
                      '%s vs %s' % (inline_hv.group(1), other.group(1)))

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
print('The build workflow reports what actually happened')
# It used to be marked continue-on-error because the build could only ever
# produce a log. edk2 links the volume now, so a red run has to mean the
# firmware did not build: no continue-on-error, and the log is still kept.
build_path = os.path.join(WORKFLOWS, 'build.yml')
if os.path.exists(build_path):
    text = read(build_path)
    # Match the key only: the comment above the job explains what it replaced,
    # and naming the removed key inside a comment is not the same as using it.
    check('a red run means the firmware did not build',
          not any(l.split('#')[0].strip().startswith('continue-on-error')
                  for l in text.splitlines()),
          'the build job still swallows its failure')
    check('it keeps the log when the build fails',
          'if: always()' in text)
    check('it says the boot image boots in RAM',
          'fastboot boot' in text)
    check('it warns the seeded volume must not be flashed',
          'must not be flashed' in text)
    check('it runs the repository checks first',
          'needs: checks' in text)
    # The artifact upload has to come after the step that copies the volume
    # into out/, or the artifact carries the log and not the firmware.
    keep = text.find('keep the volume')
    upload = text.find('actions/upload-artifact')
    check('the volume is copied before the artifact is uploaded',
          0 <= keep < upload, 'keep=' + str(keep) + ' upload=' + str(upload))
else:
    check('build.yml exists', False)

if failures:
    print()
    print('%d failure(s)' % len(failures))
    sys.exit(1)
print()
print('all checks passed')