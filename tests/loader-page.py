#!/usr/bin/env python3
"""The loader page protocol, simulated.

The kernel side is a state machine over a shared page: it writes a request,
waits for the loader to set the matching sequence number, then copies out of
the loader's buffer. Every failure mode here is silent on hardware -- a page
with the wrong magic is read as garbage, a stale sequence number looks like an
answer -- so the protocol is written out and driven from here.

    python3 tests/loader-page.py
"""

import struct
import sys

# From package/storage/haydn.ufs.h
BLOCK_MAGIC = 0x4B434F4C42574452      # "RDWBLOCK"
BLOCK_VERSION = 3
BLOCK_MAX_PARTS = 160
BLOCK_OP_READ = 0
BLOCK_OP_WRITE = 1
PAGE = 0x4000

failures = []


def check(name, ok, detail=''):
    if ok:
        print(f'  ok    {name}')
    else:
        print(f'  FAIL  {name}  {detail}')
        failures.append(name)


class Page:
    """The loader's side of the shared page, as the loader would keep it."""

    def __init__(self, magic=BLOCK_MAGIC, version=BLOCK_VERSION, size=0x1000,
                 parts=3, buffer_size=0x40000):
        self.magic = magic
        self.version = version
        self.size = size
        self.parts = parts
        self.buffer_size = buffer_size
        self.request = 0
        self.answered = 0
        self.status = 0
        self.serve = True
        self.seen = []

    def valid(self):
        """haydn_ufs_attach()'s step 1."""
        return (self.magic == BLOCK_MAGIC and self.version == BLOCK_VERSION
                and self.parts <= BLOCK_MAX_PARTS and self.buffer_size > 0)

    def loader_poll(self):
        """What core 0 does: answer the request it finds."""
        if self.request != self.answered and self.serve:
            self.seen.append(self.request)
            self.status = 0
            self.answered = self.request


class Kernel:
    """The kernel side: haydn_ufs_read()'s state machine."""

    def __init__(self, page):
        self.page = page
        self.seq = 0
        self.dead = False

    def attach(self):
        if not self.page.valid():
            self.dead = True
            return False
        self.seq = self.page.answered   # a loader that served an earlier kernel
        return True

    def read(self, part, lba, count, ticks=4):
        # haydn_ufs_read(): ask, then look until answered or the timeout.
        # The real loop looks many times before sleeping, so one look taken
        # before core 0 has run is not a timeout. `ticks` is how many times
        # core 0 is allowed to run before the kernel gives up.
        if self.dead:
            return 'dead'
        self.seq += 1
        self.page.request = self.seq
        for _ in range(ticks):
            self.page.loader_poll()          # core 0 gets a turn
            if self.page.answered == self.seq:
                if self.page.status != 0:
                    return 'error'
                return 'ok'
        return 'timeout'


print('A page this kernel knows attaches')
p = Page()
k = Kernel(p)
check('attach succeeds', k.attach())
check('not dead', not k.dead)

print()
print('A page this kernel does not know is refused')
for label, wrong in [
    ('wrong magic', Page(magic=0xDEADBEEF)),
    ('wrong version', Page(version=2)),
    ('too many parts', Page(parts=BLOCK_MAX_PARTS + 1)),
    ('no buffer', Page(buffer_size=0)),
]:
    kk = Kernel(wrong)
    check(f'{label} is refused', not kk.attach())
    check(f'{label} marks the storage dead', kk.dead)
    check(f'{label} reads nothing', kk.read(0, 0, 1) == 'dead')

print()
print('A read is a sequence number, not a flag')
p = Page()
k = Kernel(p)
k.attach()
check('the sequence starts at 0', k.seq == 0)
check('the first read is answered', k.read(0, 0, 1) == 'ok')
check('the loader saw sequence 1', p.seen == [1], str(p.seen))
check('a second read is answered', k.read(0, 8, 1) == 'ok')
check('the loader saw sequence 2', p.seen == [1, 2], str(p.seen))
check('the kernel never writes answered', p.answered == p.request)

print()
print('A loader that served an earlier kernel is picked up where it left off')
p = Page()
p.answered = 41
k = Kernel(p)
k.attach()
check('the sequence resumes at 41', k.seq == 41, str(k.seq))
check('the next read is 42', k.read(0, 0, 1) == 'ok')
check('the loader saw 42', p.seen == [42], str(p.seen))

print()
print('A stale answer is not taken for one')
p = Page()
k = Kernel(p)
k.attach()
k.read(0, 0, 1)
# The kernel asks again but the loader does not serve it.
p.serve = False
check('an unanswered request times out', k.read(0, 8, 1, ticks=3) == 'timeout')
check('it did not mistake the old answer for a new one', p.answered == 1)

print()
print('A loader error is reported, not swallowed')
p = Page()
k = Kernel(p)
k.attach()
p.serve = False
p.status = -5
p.answered = 1          # an answer with a failure status
check('a failed request is an error', k.read(0, 0, 1) == 'error')

print()
print('One outstanding request, and the buffer bounds it')
p = Page(buffer_size=0x40000)
k = Kernel(p)
k.attach()
check('the buffer is 256 KB', p.buffer_size == 0x40000)
check('one request of 64 blocks fits', 64 * 4096 <= p.buffer_size)
check('65 blocks do not', 65 * 4096 > p.buffer_size)

print()
print('The page is one 16 KB mapping')
check('HAYDN_UFS_PAGE is 0x4000', PAGE == 0x4000)
# The address is page aligned by the loader; the driver maps down to it.
addr = 0x9F000000 + 0x1234
base = addr & ~(PAGE - 1)
offset = addr & (PAGE - 1)
check('a misaligned publication maps to its page', base % PAGE == 0)
check('the offset is kept', offset == 0x1234, hex(offset))

if failures:
    print(f'{len(failures)} failure(s)')
    sys.exit(1)
print('all checks passed')
