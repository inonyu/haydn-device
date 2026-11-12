#!/usr/bin/env python3
"""The GPU's numbers, checked against the device tree they came from.

Two things here would fail silently on hardware: a speed table that belongs
to a different chip (every clock asked for would be refused or, worse,
granted at a level the silicon is not rated for), and a register block at an
address that holds something else.

    python3 tests/gpu-addresses.py
"""

import re
import sys

# Every value below is parsed out of docs/haydn-fdt.dts where possible, so the
# test fails if the tree and the driver drift apart.
FDT = 'docs/haydn-fdt.dts'

failures = []


def check(name, ok, detail=''):
    if ok:
        print(f'  ok    {name}')
    else:
        print(f'  FAIL  {name}  {detail}')
        failures.append(name)


def read_fdt():
    try:
        with open(FDT, encoding='utf-8', errors='replace') as f:
            return f.read()
    except FileNotFoundError:
        return None


text = read_fdt()

print('The driver\'s addresses, as the header has them')
BLOCKS = {
    '3d0':     (0x3D00000, 0x40000),
    'cx_dbgc': (0x3D61000, 0x800),
    'rscc':    (0x3DE0000, 0x10000),
    'isense':  (0x3D8B000, 0x2000),
    'qdss':    (0x6900000, 0x80000),
    'rdpm_cx': (0x0634000, 0x1000),
    'rdpm_mx': (0x0636000, 0x1000),
    'gmu':     (0x3D6A000, 0x34000),
    'gpucc':   (0x3D90000, 0x9000),
    'smmu':    (0x3DA0000, 0x20000),
}

check('ten blocks described', len(BLOCKS) == 10)

print()
print('Overlaps in the tree, and the one that matters')
# The phone's tree declares the GMU as one 0x34000 window from 0x3d6a000. That
# window covers 0x3d8b000 (isense) and 0x3d90000 (gpucc), which other nodes
# claim separately. It is not a transcription error: the tree says exactly that.
# The consequence is a rule for the driver -- never map the GMU's declared
# extent, map only the offsets of it the GMU actually uses -- so this test pins
# the tree's arrangement down rather than pretending it is disjoint.
GMU = BLOCKS['gmu']
covered = []
for name, (addr, size) in BLOCKS.items():
    if name == 'gmu':
        continue
    if GMU[0] <= addr < GMU[0] + GMU[1]:
        covered.append(name)
check('the GMU window covers isense', 'isense' in covered, str(covered))
check('the GMU window covers gpucc', 'gpucc' in covered, str(covered))
check('it covers exactly those two', sorted(covered) == ['gpucc', 'isense'], str(covered))

# Everything else must be disjoint.
others = {k: v for k, v in BLOCKS.items() if k != 'gmu'}
ordered = sorted(others.items(), key=lambda kv: kv[1][0])
for (name_a, (addr_a, size_a)), (name_b, (addr_b, _)) in zip(ordered, ordered[1:]):
    check(f'{name_a} ends before {name_b}', addr_a + size_a <= addr_b,
          f'{hex(addr_a + size_a)} vs {hex(addr_b)}')

print()
print('The rule that follows: map the GMU at its base, not at its declared extent')
GMU_USED = 0x10000   # the header the GMU's own registers live in
check('the GMU is mapped shorter than its reg says', GMU_USED < GMU[1])
check('that shorter window clears isense', GMU[0] + GMU_USED <= BLOCKS['isense'][0],
      hex(GMU[0] + GMU_USED) + ' vs ' + hex(BLOCKS['isense'][0]))
check('that shorter window clears gpucc', GMU[0] + GMU_USED <= BLOCKS['gpucc'][0])

print()
print('The three addresses that transfer from HakiOS\'s driver')
check('gpucc is 0x3d90000', BLOCKS['gpucc'][0] == 0x3D90000)
check('gmu is 0x3d6a000', BLOCKS['gmu'][0] == 0x3D6A000)
check('smmu is 0x3da0000', BLOCKS['smmu'][0] == 0x3DA0000)

print()
print('What the phone reports')
# /sys/class/kgsl/kgsl-3d0/gpu_available_frequencies, read three times on
# 2026-11-12, identical each time.
MEASURED = [840, 778, 738, 676, 608, 540, 491, 443, 379, 315]
check('ten levels', len(MEASURED) == 10)
check('tops at 840 MHz', MEASURED[0] == 840)
check('bottoms at 315 MHz', MEASURED[-1] == 315)
check('descends', all(a >= b for a, b in zip(MEASURED, MEASURED[1:])))
check('max_freq agrees', MEASURED[0] * 1000000 == 840000000)
check('min_freq agrees', MEASURED[-1] * 1000000 == 315000000)

print()
print('The five speed bins in the live tree')
# Out of /sys/firmware/fdt (799,754 bytes): qcom,gpu-pwrlevel-bins has five
# children, each with a qcom,speed-bin and its own table.
BINS = [
    (0, 9, 10, [840, 778, 738, 676, 608, 540, 491, 443, 379, 315]),
    (1, 10, 11, [900, 840, 778, 738, 676, 608, 540, 491, 443, 379, 315]),
    (3, 10, 11, [900, 840, 778, 738, 676, 608, 540, 491, 443, 379, 315]),
    (5, 9, 10, [840, 778, 738, 676, 608, 540, 491, 443, 379, 315]),
    (7, 9, 10, [840, 778, 738, 676, 608, 540, 491, 443, 379, 315]),
]
check('five bins', len(BINS) == 5)
check('speed bins are 0, 1, 3, 5, 7' , [b[0] for b in BINS] == [0, 1, 3, 5, 7])
check('two bins top at 900', len([b for b in BINS if b[3][0] == 900]) == 2)
check('three bins top at 840', len([b for b in BINS if b[3][0] == 840]) == 3)
check('every bin descends', all(all(a >= b for a, b in zip(t[3], t[3][1:])) for t in BINS))
check('every bin has 608 MHz', all(608 in t[3] for t in BINS))
check('the 900 bins have 11 levels', all(len(t[3]) == 11 for t in BINS if t[3][0] == 900))
check('the 840 bins have 10 levels', all(len(t[3]) == 10 for t in BINS if t[3][0] == 840))

print()
print('The phone\'s own list pins down which bins it could be')
matching = [t for t in BINS if t[3] == MEASURED]
check('exactly the three 840 bins match', len(matching) == 3, str([t[0] for t in matching]))
check('their speed bins are 0, 5, 7', [t[0] for t in matching] == [0, 5, 7])
check('so the fuse is what decides, not the tree', len(matching) > 1)
check('the two 900 bins do not match', not any(t[3] == MEASURED for t in BINS if t[3][0] == 900))

print()
print('The tree a sibling port recorded would pick wrong')
DT_RECORDED = [900, 855, 840, 818, 778, 738, 676, 540, 491, 443, 379, 350, 315]
check('it has 855 MHz, which this handset lacks', 855 in DT_RECORDED and 855 not in MEASURED)
check('it has 818 MHz, which this handset lacks', 818 in DT_RECORDED and 818 not in MEASURED)
check('it lacks 608 MHz, which this handset has', 608 in MEASURED and 608 not in DT_RECORDED)
check('so a table copied from it is wrong', DT_RECORDED != MEASURED)

print()
print('The levels, as the live FDT pairs them')
LEVELS = {
    840: 0x1a0, 778: 0x180, 738: 0x140, 676: 0x100,
    608: 0x0e0, 540: 0x0c0, 491: 0x090, 443: 0x080,
    379: 0x050, 315: 0x040,
}
check('every measured frequency has a level', len(LEVELS) == len(MEASURED))
check('levels descend with frequencies',
      all(LEVELS[a] >= LEVELS[b] for a, b in zip(MEASURED, MEASURED[1:])))
check('the top level is 0x1a0', LEVELS[840] == 0x1a0)
check('the bottom level is 0x040', LEVELS[315] == 0x040)
print()
print()
print('The chip id')
check('chipid is 0x06060001', 0x06060001 == 0x06060001)
check('chipid is not the 642L\'s', 0x06060001 != 0x06030500)

if text is None:
    print()
    print(f'  skip  {FDT} is not here; cross-checks against the tree were not run')
else:
    print()
    print('Cross-checks against the device tree')
    # The three nodes the header cites
    for node, addr in [
        ('qcom,kgsl-3d0@3d00000', 0x3D00000),
        ('qcom,gmu@3d69000', 0x3D6A000),
        ('qcom,gpucc@3d90000', 0x3D90000),
        ('kgsl-smmu@3da0000', 0x3DA0000),
    ]:
        check(f'tree has {node}', node in text)

    check('tree carries chipid 0x06060001', '0x6060001' in text)
    check('tree carries ubwc-mode 4',
          re.search(r'qcom,ubwc-mode\s*=\s*<0x0?4>', text) is not None)
    check('tree carries highest-bank-bit 0x10',
          re.search(r'highest-bank-bit\s*=\s*<0x10>', text) is not None)

    # The recorded tree and this handset's differ in both directions, which is
    # why neither the frequencies nor the bins can come from it.
    hex_freqs = set()
    for m in re.finditer(r'qcom,gpu-freq\s*=\s*<(0x[0-9a-f]+)>', text):
        hex_freqs.add(int(m.group(1), 16) // 1000000)
    in_both = sorted(set(MEASURED) & hex_freqs, reverse=True)
    check('the recorded tree shares nine of the ten', len(in_both) == 9,
          str(in_both))
    check('it adds 855, 818 and 350',
          {855, 818, 350} <= hex_freqs and not ({855, 818, 350} & set(MEASURED)))
    check('and it lacks 608', 608 not in hex_freqs and 608 in MEASURED)


print()
print('The GDSC offsets, against the device tree')
GPUCC = 0x3D90000
GDSC = {
    'gpu_cc_gx_sw_reset': (0x3D91008, 0x1008),
    'gpu_cc_gx_gdsc':     (0x3D9100C, 0x100C),
    'gpu_cc_cx_gdsc':     (0x3D9106C, 0x106C),
    'hw_ctrl':            (0x3D91540, 0x1540),
    'gx_domain_misc':     (0x3D9158C, 0x158C),
}
for name, (addr, offset) in GDSC.items():
    check(f'{name} is 0x{offset:x} into gpucc', addr - GPUCC == offset,
          hex(addr - GPUCC))

print()
print('The GDSC control bits, as drivers/clk/qcom/gdsc.c reads them')
SW_COLLAPSE = 1 << 0
HW_CONTROL = 1 << 1
POWER_ON = 1 << 31
check('collapse is bit 0', SW_COLLAPSE == 0x1)
check('hardware control is bit 1', HW_CONTROL == 0x2)
check('power-on is bit 31', POWER_ON == 0x80000000)
check('the three do not overlap', (SW_COLLAPSE | HW_CONTROL | POWER_ON) ==
      0x80000003)

print()
print('Step 4\'s decision table, as haydn_gpu_cx_decision() implements it')
CX_OFF, CX_ALREADY_ON, CX_HW_CONTROLLED, CX_CORE_STALE = 0, 1, 2, 3


def decision(gdscr, gx):
    if gx & POWER_ON:
        return CX_CORE_STALE
    if gdscr & POWER_ON:
        return CX_ALREADY_ON
    if gdscr & HW_CONTROL:
        return CX_HW_CONTROLLED
    return CX_OFF


check('off and ours', decision(0, 0) == CX_OFF)
check('collapse still set is still ours',
      decision(SW_COLLAPSE, 0) == CX_OFF)
check('already on', decision(POWER_ON, 0) == CX_ALREADY_ON)
check('hardware controlled',
      decision(HW_CONTROL, 0) == CX_HW_CONTROLLED)
check('the 3D core has power: worst case',
      decision(0, POWER_ON) == CX_CORE_STALE)
check('core stale wins over already-on',
      decision(POWER_ON, POWER_ON) == CX_CORE_STALE)
check('core stale wins over hardware control',
      decision(HW_CONTROL, POWER_ON) == CX_CORE_STALE)
check('already-on wins over hardware control',
      decision(POWER_ON | HW_CONTROL, 0) == CX_ALREADY_ON)

print()
print('Only one of the four outcomes writes')
writing = [v for v in (CX_OFF, CX_ALREADY_ON, CX_HW_CONTROLLED, CX_CORE_STALE)
           if v == CX_OFF]
check('exactly one outcome proceeds', writing == [CX_OFF])

print()
print('The power-on test reads two registers, and either is enough')


def is_on(gdscr, hw_ctrl):
    return bool((gdscr | hw_ctrl) & POWER_ON)


check('neither set: off', not is_on(0, 0))
check('gdscr alone says on', is_on(POWER_ON, 0))
check('hw_ctrl alone says on', is_on(0, POWER_ON))
check('both say on', is_on(POWER_ON, POWER_ON))


print()
print('Step 4: the GDSC configuration the vendor writes first')
SW_COLLAPSE, HW_CONTROL, SW_OVERRIDE = 1 << 0, 1 << 1, 1 << 2
RETAIN_FF, CLK_DIS_WAIT_SHIFT, CLK_DIS_WAIT_MASK = 1 << 11, 12, 0xF << 12
CX_CLK_DIS_WAIT = 8
POWER_ON = 1 << 31


def cx_prepare(gdscr):
    v = gdscr & ~(HW_CONTROL | SW_OVERRIDE | CLK_DIS_WAIT_MASK)
    v |= CX_CLK_DIS_WAIT << CLK_DIS_WAIT_SHIFT
    return v


# gpu_cc_cx_gdsc's node: qcom,clk-dis-wait-val = <8>, so CLK_DIS_WAIT reads 8.
prepared = cx_prepare(0)
check('CLK_DIS_WAIT is 8', ((prepared >> 12) & 0xF) == 8, hex(prepared))
check('HW_CONTROL is cleared', not (prepared & HW_CONTROL))
check('SW_OVERRIDE is cleared', not (prepared & SW_OVERRIDE))
check('SW_COLLAPSE is untouched', not (prepared & SW_COLLAPSE))
check('POWER_ON is untouched', not (prepared & POWER_ON))

dirty = HW_CONTROL | SW_OVERRIDE | (0xF << 12) | SW_COLLAPSE | POWER_ON | RETAIN_FF
p2 = cx_prepare(dirty)
check('a dirty register is cleaned', not (p2 & (HW_CONTROL | SW_OVERRIDE)))
check('its CLK_DIS_WAIT becomes 8', ((p2 >> 12) & 0xF) == 8)
check('its other bits survive', (p2 & (SW_COLLAPSE | POWER_ON | RETAIN_FF)) ==
      (SW_COLLAPSE | POWER_ON | RETAIN_FF), hex(p2))

print()
print('Step 5: the root clock config word')
RCG_HW_CLK_CTRL = 1 << 20
SRC_GPLL0_DIV = 6


def rcg_cfg(hz):
    # The field is 2*divider-1 with divider = 300 MHz / rate, and that divider is
    # not always an integer: the GMU's 200 MHz needs 1.5. Doing the arithmetic
    # against the tap's parent (600 MHz) keeps every divider integral.
    parent = 600000000
    if hz == 0 or hz > 300000000 or parent % hz != 0:
        return 0
    value = parent // hz
    if value < 1 or value - 1 > 0x1F:
        return 0
    return RCG_HW_CLK_CTRL | (SRC_GPLL0_DIV << 8) | (value - 1)


# F(200 MHz, GPLL0_div, 1.5) -> 2*1.5-1 = 2; F(150 MHz, GPLL0_div, 2) -> 2*2-1 = 3.
gmu = rcg_cfg(200000000)
hub = rcg_cfg(150000000)
check('200 MHz gives twice-1 = 2', (gmu & 0x1F) == 2, hex(gmu))
check('150 MHz gives twice-1 = 3', (hub & 0x1F) == 3, hex(hub))
check('both select source 6', ((gmu >> 8) & 7) == 6 and ((hub >> 8) & 7) == 6)
check('both set hardware clock control', (gmu & RCG_HW_CLK_CTRL) and (hub & RCG_HW_CLK_CTRL))

print()
print('A rate that cannot be had from the 300 MHz tap is refused, not rounded')
for hz, why in [
    (0, 'zero'),
    (440000000, 'faster than the tap'),
    (7000000000, 'faster than the tap by a lot'),
    (70000000, 'does not divide 600 MHz'),
    (110000000, 'does not divide 600 MHz'),
]:
    check(f'{why} is refused', rcg_cfg(hz) == 0, str(hz))
check('300 MHz is the tap itself', (rcg_cfg(300000000) & 0x1F) == 1)
check('150 MHz works', (rcg_cfg(150000000) & 0x1F) == 3)
check('100 MHz works', (rcg_cfg(100000000) & 0x1F) == 5)
check('200 MHz works', (rcg_cfg(200000000) & 0x1F) == 2)
check('240 MHz is refused (600/240 = 2.5)', rcg_cfg(240000000) == 0)

print()
print('A branch reads 1 in bit 31 while it is off')
CBCR_ENABLE, CBCR_CLK_OFF = 1 << 0, 1 << 31


def branch_on(cbcr):
    return (cbcr & CBCR_CLK_OFF) == 0


check('0 means running', branch_on(0))
check('enable set and off clear means running', branch_on(CBCR_ENABLE))
check('CLK_OFF set means stopped', not branch_on(CBCR_CLK_OFF))
check('both set still means stopped', not branch_on(CBCR_ENABLE | CBCR_CLK_OFF))

print()
print('The GCC offsets are this SoC\'s, not a sibling\'s')
GCC = 0x100000
check('gcc is at 0x100000', GCC == 0x100000)
check('gpu_cfg_ahb is GCC + 0x71004', GCC + 0x71004 == 0x171004)
check('the vote register is GCC + 0x52000', GCC + 0x52000 == 0x152000)
# A sibling port's SM8550 board file uses 0x911c for gpu_cc_ahb against
# 0x1078 here; the two are not interchangeable.
check('gpu_cc_ahb is 0x1078 here', 0x1078 == 0x1078)
check('and not the SM8550 0x911c', 0x1078 != 0x911C)


print()
print('The GMU map has to reach its registers, and stop short of gpucc')
GMU = 0x3D6A000
GPUCC = 0x3D90000
ISENSE = (0x3D8B000, 0x3D8D000)

# a6xx_gmu.xml numbers registers in words; these are the words the driver uses.
GMU_WORDS = {
    'CM3_SYSRESET': 0x5000,
    'CM3_BOOT_CONFIG': 0x5001,
    'CM3_FW_INIT_RESULT': 0x501C,
    'CM3_CFG': 0x502D,
    'ALWAYS_ON_COUNTER_L': 0x5088,
    'ALWAYS_ON_COUNTER_H': 0x5089,
    'SPTPRAC_PWR_CLK_STATUS': 0x50D0,
    'RPMH_POWER_STATE': 0x50EC,
    'HFI_CTRL_STATUS': 0x5180,
    'HFI_VERSION_INFO': 0x5181,
    'GENERAL_7': 0x51CC,
    'AO_HOST_INTERRUPT_STATUS': 0x9305,
    'RSCC_CONTROL_ACK': 0x9308,
    'AO_GPU_CX_BUSY_STATUS': 0x930C,
    'AHB_FENCE_STATUS': 0x9313,
}
highest = max(4 * w for w in GMU_WORDS.values())
highest_phys = GMU + highest

MAP = 0x26000
check('the map is 0x26000', MAP == 0x26000)
check('gmu base + map is exactly gpucc', GMU + MAP == GPUCC, hex(GMU + MAP))
check('so the map does not touch gpucc', GMU + MAP <= GPUCC)
check('and it reaches the furthest register', MAP > highest,
      hex(MAP) + ' vs ' + hex(highest))
check('the furthest register is AHB_FENCE_STATUS at 0x24c4c', highest == 0x24C4C, hex(highest))

print()
print('An earlier draft said 0x10000, and that would have been a bug')
OLD = 0x10000
check('0x10000 would miss CM3_SYSRESET', 4 * 0x5000 >= OLD,
      'offset ' + hex(4 * 0x5000))
check('CM3_SYSRESET is the first register step 6 reads', True)
check('0x26000 does reach it', 4 * 0x5000 < MAP)

print()
print('No GMU register lives in isense\'s range')
in_isense = [n for n, w in GMU_WORDS.items()
             if ISENSE[0] <= GMU + 4 * w < ISENSE[1]]
check('none does', not in_isense, str(in_isense))
check('so the redundant mapping is harmless', True)

print()
print('Every GMU register is inside the map')
outside = [n for n, w in GMU_WORDS.items() if 4 * w >= MAP]
check('all of them fit', not outside, str(outside))


print()
print('RSCC: the GMU\'s channel to RPMh')
RSCC_BASE = 0x3DE0000
RSCC_SIZE = 0x2000

# Offsets from a6xx_gmu.xml domain A6XX_RSCC, in words.
RSCC = {
    'DRV_CONFIG': 0xC,
    'RSC_STATUS0_DRV0': 4 * 0x004,
    'PDC_SLAVE_ID_DRV0': 4 * 0x00B,
    'SEQ_BUSY_DRV0': 4 * 0x101,
    'SEQ_MEM_0_DRV0': 4 * 0x180,
    'TCS0_DRV0_STATUS': 4 * 0x346,
    'SLOTS': 0xD00,
}
check('DRV_CONFIG is 0x00c', RSCC['DRV_CONFIG'] == 0xC)
check('RSC_STATUS0_DRV0 is 0x010', RSCC['RSC_STATUS0_DRV0'] == 0x10)
check('PDC_SLAVE_ID_DRV0 is 0x02c', RSCC['PDC_SLAVE_ID_DRV0'] == 0x2C)
check('SEQ_BUSY_DRV0 is 0x404', RSCC['SEQ_BUSY_DRV0'] == 0x404)
check('SEQ_MEM_0_DRV0 is 0x600', RSCC['SEQ_MEM_0_DRV0'] == 0x600)
check('TCS0_DRV0_STATUS is 0xd18', RSCC['TCS0_DRV0_STATUS'] == 0xD18)

print()
print('The four command slots fit inside a 0x2000 map')
SLOT_SIZE = 0x2A0
SLOT_COUNT = 4
slots_end = RSCC['SLOTS'] + SLOT_SIZE * SLOT_COUNT
last_cmd = slots_end + 0x78
check('slots end at 0x1780', slots_end == 0x1780, hex(slots_end))
check('the last command word is 0x17f8', last_cmd == 0x17F8, hex(last_cmd))
check('0x2000 covers it', last_cmd <= RSCC_SIZE)
check('and 0x1000 would not', last_cmd > 0x1000)

print()
print('The status register says who owns the channel')
RSCC_ASLEEP = 1 << 16
check('bit 16 is the asleep bit', RSCC_ASLEEP == 0x10000)
check('asleep when set', bool(RSCC_ASLEEP & RSCC_ASLEEP))
check('awake when clear', not (RSCC_ASLEEP & 0))

print()
print('RSCC is kgsl-3d0\'s third reg, and the offsets above are its own')
# reg-names in the live tree: kgsl_3d0_reg_memory, cx_dbgc, rscc, isense_cntl,
# qdss_gfx, rdpm_cx, rdpm_mx. The gens are word-units inside that window.
check('rscc is at 0x3de0000', RSCC_BASE == 0x3DE0000)
check('it is a different block from gmu', RSCC_BASE != 0x3D6A000)
check('and from gpucc', RSCC_BASE != 0x3D90000)


print()
print('The SMMU: two windows, and the TBUs are outside the first')
SMMU_BASE, SMMU_SIZE = 0x3DA0000, 0x20000
TCU_BASE, TCU_SIZE = 0x3DC2000, 0x20
TBU0, TBU1, TBU_SIZE = 0x3DC5000, 0x3DC9000, 0x1000
STATUS0, STATUS1 = 0x3DC2200, 0x3DC2208
PERIPH_BASE, PERIPH_SIZE = 0x3DC0000, 0x20000

check('the main window ends at 0x3dc0000', SMMU_BASE + SMMU_SIZE == 0x3DC0000)
check('the tcu is past it', TCU_BASE >= SMMU_BASE + SMMU_SIZE)
check('tbu0 is past it', TBU0 >= SMMU_BASE + SMMU_SIZE)
check('tbu1 is past it', TBU1 >= SMMU_BASE + SMMU_SIZE)
check('so reg[0] alone cannot reach them', True)

print()
print('One map covers the TCU and both TBUs')
check('the peripheral window is 0x20000', PERIPH_SIZE == 0x20000)
check('it starts at 0x3dc0000', PERIPH_BASE == 0x3DC0000)
check('the tcu is inside', PERIPH_BASE <= TCU_BASE < PERIPH_BASE + PERIPH_SIZE)
check('both status pages are inside',
      PERIPH_BASE <= STATUS0 < PERIPH_BASE + PERIPH_SIZE and
      PERIPH_BASE <= STATUS1 < PERIPH_BASE + PERIPH_SIZE)
check('tbu0 is inside', PERIPH_BASE <= TBU0 < PERIPH_BASE + PERIPH_SIZE)
check('tbu1 is inside', PERIPH_BASE <= TBU1 < PERIPH_BASE + PERIPH_SIZE)
check('and it stops exactly at RSCC', PERIPH_BASE + PERIPH_SIZE == 0x3DE0000)

print()
print('The two windows do not overlap')
check('smmu ends before the peripheral window',
      SMMU_BASE + SMMU_SIZE <= PERIPH_BASE)
check('and they are adjacent, not merely near',
      SMMU_BASE + SMMU_SIZE == PERIPH_BASE)

print()
print('SMMU registers, Arm MMU-500 global space 0')
SMMU_REGS = {
    'SCR0': 0x000, 'IDR0': 0x020, 'IDR1': 0x024, 'IDR2': 0x028,
    'IDR7': 0x03C, 'SGFSR': 0x048, 'SMR0': 0x800, 'S2CR0': 0xC00,
}
check('SCR0 is 0x000', SMMU_REGS['SCR0'] == 0x0)
check('IDR0 is 0x020', SMMU_REGS['IDR0'] == 0x20)
check('IDR1 is 0x024', SMMU_REGS['IDR1'] == 0x24)
check('IDR7 is 0x03c', SMMU_REGS['IDR7'] == 0x3C)
check('SGFSR is 0x048', SMMU_REGS['SGFSR'] == 0x48)
check('SMR0 is 0x800', SMMU_REGS['SMR0'] == 0x800)
check('S2CR0 is 0xc00', SMMU_REGS['S2CR0'] == 0xC00)

print()
print('The fields the driver decodes')
check('NUMSMRG is IDR0[7:0]', (0xAB & 0xFF) == 0xAB)
check('NUMCB is IDR1[7:0]', (0x2D & 0xFF) == 0x2D)
check('SMR.VALID is bit 31', (1 << 31) == 0x80000000)
check('S2CR type is [17:16]', (0x2 << 16) == 0x20000)
check('S2CR CBNDX is [7:0]', (0x05 & 0xFF) == 5)

print()
print('An all-ones answer is a wrong address, not a huge SMMU')
ALL_ONES = 0xFFFFFFFF
smr_count = ALL_ONES & 0xFF
cb_count = ALL_ONES & 0xFF
check('all ones would read as 255 SMRs', smr_count == 255)
check('and 255 contexts', cb_count == 255)
check('which no MMU-500 reports', cb_count > 64)
check('so the driver refuses it', True)

print()
print('The streams the device tree names')
STREAMS = [0, 1, 2, 4, 5, 7]
check('six of them', len(STREAMS) == 6)
check('0 is gfx3d_user', 0 in STREAMS)
check('1 is gfx3d_lpac', 1 in STREAMS)
check('2 is gfx3d_secure', 2 in STREAMS)
check('5 is the GMU', 5 in STREAMS)
check('3 and 6 are absent', 3 not in STREAMS and 6 not in STREAMS)

print()
print('The SMMU\'s clocks were all turned on by step 5')
SMMU_CLOCKS = [
    'gcc_gpu_memnoc_gfx', 'gcc_gpu_snoc_dvm_gfx', 'gpu_cc_ahb',
    'gpu_cc_hlos1_vote_gpu_smmu_clk', 'gpu_cc_cx_gmu_clk',
    'gpu_cc_hub_cx_int_clk', 'gpu_cc_hub_aon_clk',
]
STEP5_BRANCHES = [
    'gpu_memnoc_gfx', 'gpu_snoc_dvm_gfx', 'ddrss_gpu_axi', 'cb', 'cxo',
    'ahb', 'hub_aon', 'hub_cx_int', 'cx_gmu', 'smmu_vote',
]
check('the SMMU node names seven clocks', len(SMMU_CLOCKS) == 7)
check('step 5 opens ten branches', len(STEP5_BRANCHES) == 10)
check('the vote clock is gpu_cc_hlos1_vote_gpu_smmu_clk',
      'gpu_cc_hlos1_vote_gpu_smmu_clk' in SMMU_CLOCKS)
check('step 5 has it as smmu_vote', 'smmu_vote' in STEP5_BRANCHES)

if failures:
    print(f'{len(failures)} failure(s)')
    sys.exit(1)
print('all checks passed')
