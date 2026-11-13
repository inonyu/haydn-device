
"""Build a haydn ADT (Apple Device Tree) from the sweet tooling, retargeted.

This is the payload XNU reads at boot: /chosen (dram base/size, panic log,
security posture), the CPU list, the GIC window, and the handful of nodes the
early boot path requires. sweet's mkadt.py supplies the encoding; every
board-specific number below comes from docs/hardware.md and the phone's own
FDT, not from sweet.

Writes out/haydn.adt and prints what it contains.
"""
import os, struct, sys

# The ADT encoder is ios-sweet's tools/adt.py, reused rather than rewritten.
# Point SWEET_TOOLS at a checkout of github.com/.../ios-sweet to run this.
SWEET_TOOLS = os.environ.get("SWEET_TOOLS",
                             os.path.join(os.path.dirname(__file__), "..", "..",
                                          "refs", "ios-sweet", "tools"))
sys.path.insert(0, SWEET_TOOLS)
import adt  # noqa: E402

OUT = os.environ.get("HAYDN_ADT",
                     os.path.join(os.path.dirname(__file__), "haydn.adt"))

# --- this board's numbers, each traceable to docs/hardware.md --------------
# RAM: the ADT window has to sit inside a real segment and above the
# bootloader's own carve-outs. The phone reports three windows:
#   0x80000000 + 0x39700000, 0x180000000 + 0x100000000, 0xc0000000 + 0xc0000000
# 512 MiB from 0x80000000 stays inside the first one.
PHYS_BASE = 0x80000000
MEM_SIZE = 0x20000000
PANIC_LOG_SIZE = 0x100000

GICD, GICD_SIZE = 0x17a00000, 0x10000
GICR, GICR_SIZE = 0x17a60000, 0x100000     # stride 0x20000, 8 PEs
TIMEBASE = 19200000
# docs/hardware.md: arm,armv8-timer interrupts = PPI 13/14/11/12
#   -> secure-phys 29, phys 30, virt 27, hyp 28
VTIMER_INTID = 27

FB, FB_SIZE = 0xdfc00000, 0x1000000          # splash_region the loader leaves
FB_W, FB_H = 1080, 2400
FB_STRIDE = FB_W * 4

UFS, UFS_SIZE = 0x01d84000, 0x3000           # ufshc@1d84000
SOC_BASE = 0x01000000

SWEET_ECID = 0x484159444E000001              # 'HAYDN' + 1, synthetic
BOOT_MANIFEST_HASH = b"\x00" * 48

u32 = lambda *v: struct.pack("<%dI" % len(v), *v)
u64 = lambda *v: struct.pack("<%dQ" % len(v), *v)
cstr = lambda s: s.encode() + b"\0"
import hashlib
BOOT_MANIFEST_HASH = hashlib.sha384(b"haydn boot manifest").digest()


def node(name, props=(), children=()):
    n = adt.Node()
    n.props = [("name", 0, cstr(name))] + [(k, 0, v) for k, v in props]
    n.children = list(children)
    return n


def build():
    panic_base = PHYS_BASE + MEM_SIZE - PANIC_LOG_SIZE
    mem = MEM_SIZE - PANIC_LOG_SIZE
    phandle = iter(range(1, 1000))
    ph = lambda: ("AAPL,phandle", u32(next(phandle)))

    chosen = node("chosen", [
        ph(),
        ("dram-base", u64(PHYS_BASE)),
        ("dram-size", u64(mem)),
        ("random-seed", os.urandom(64)),
        ("debug-enabled", u32(1)),
        ("embedded-panic-log-size", u32(PANIC_LOG_SIZE)),
        ("firmware-version", cstr("haydn-shim")),
        ("system-firmware-version", cstr("haydn-shim")),
        ("boot-manifest-hash", BOOT_MANIFEST_HASH),
        ("crypto-hash-method", cstr("sha2-384")),
        # 1080x2400 at 3x = 360x800 points, the same class as the D22AP tree
        ("display-scale", u32(3)),
        ("unique-chip-id", struct.pack("<Q", SWEET_ECID)),
        ("certificate-production-status", u32(0)),
        ("effective-production-status-ap", u32(0)),
        ("certificate-security-mode", u32(1)),
        ("effective-security-mode-sep", u32(1)),
    ], [
        node("memory-map", [ph()]),
        node("asmb", [ph(), ("lp-sip0", u64(0x6f)), ("lp-sip1", u32(1))]),
    ])

    # 8 cores: 4 A55 (MPIDR 0x0..0x300), 3 A78 (0x400..0x600), 1 X1 (0x700).
    cpu_nodes = []
    for core in range(8):
        cpu_nodes.append(node("cpu%d" % core, [
            ph(),
            ("device_type", cstr("cpu")),
            ("compatible", cstr("qcom,kryo680") + cstr("ARM,v8")),
            ("reg", u32(core << 8)),
            ("cpu-id", u32(core)),
            ("cluster-id", u32(0)),
            ("cluster-type", u32(0)),
            ("die-cluster-id", u32(0)),
            ("cluster-core-id", u32(core)),
            ("l2-cache-id", u32(core)),
            ("l3-cache-id", u32(0)),
            ("state", cstr("running" if core == 0 else "stopped")),
            ("timebase-frequency", u32(TIMEBASE)),
            # hardware.md: A55 1,804,800 kHz, A78 2,419,200, X1 2,841,600
            ("clock-frequency", u32(2841600000 if core == 7 else
                                   2419200000 if core >= 4 else
                                   1804800000)),
            ("bus-frequency", u32(100000000)),
            ("memory-frequency", u32(1866000000)),
            ("peripheral-frequency", u32(TIMEBASE)),
            ("fixed-frequency", u32(TIMEBASE)),
        ]))
    cpus = node("cpus", [ph(), ("#address-cells", u32(1)), ("#size-cells", u32(0))],
                cpu_nodes)

    gic = node("gic", [
        ph(),
        ("compatible", cstr("arm,gic-v3")),
        ("interrupt-controller", b""),
        ("virtual-timer-intid", u32(VTIMER_INTID)),
        ("reg", u64(GICD - SOC_BASE, GICD_SIZE, GICR - SOC_BASE, GICR_SIZE)),
    ])

    arm_io = node("arm-io", [
        ph(),
        ("device_type", cstr("haydn-io")),
        ("compatible", cstr("haydn-io") + cstr("arm-io")),
        ("#address-cells", u32(2)),
        ("#size-cells", u32(2)),
        ("ranges", u64(0, SOC_BASE, 0x100000000 - SOC_BASE)),
    ], [gic,
        node("wdt", [ph(), ("no-pmu", u32(1))]),
        node("disp0", [
            ph(),
            ("device_type", cstr("display-subsystem")),
            ("compatible", cstr("haydn,display")),
            ("canvas-width", u32(FB_W)),
            ("canvas-height", u32(FB_H)),
        ])])

    fbcon = node("haydn-fbcon", [
        ph(),
        ("reg", u64(FB, FB_SIZE)),
        ("width", u32(FB_W)),
        ("height", u32(FB_H)),
        ("stride", u32(FB_STRIDE)),
    ])

    ufs = node("sweet-ufs", [          # the driver looks this node up by name
        ph(),
        ("compatible", cstr("qcom,ufshc")),
        ("reg", u64(UFS, UFS_SIZE)),
    ])

    defaults = node("defaults", [ph(), ("no-effaceable-storage", u32(1))])
    buttons = node("buttons", [
        ph(),
        ("button-names", cstr("volup") + cstr("voldown") + cstr("hold")),
        ("home-button-type", u32(2)),
        ("opposed-power-vol-buttons", u32(1)),
    ])
    pram = node("pram", [ph(), ("reg", u64(panic_base) + u64(PANIC_LOG_SIZE))])

    return node("device-tree", [
        ph(),
        # compatible[0] is hw.model/hw.target. The userland is the iPhone X
        # (D22AP); 'xiaomi,haydn' is what the platform expert matches on.
        ("compatible", cstr("D22AP") + cstr("iPhone10,3") +
                       cstr("xiaomi,haydn") + cstr("qcom,sm8350") + cstr("AppleARM")),
        ("model", cstr("iPhone10,3")),
        ("target-type", cstr("D22")),
        ("target-sub-type", cstr("D22AP")),
        ("manufacturer", cstr("Apple Inc.")),
        ("#address-cells", u32(2)),
        ("#size-cells", u32(2)),
    ], [chosen, defaults, cpus, arm_io, fbcon, buttons, pram, ufs])


if __name__ == "__main__":
    root = build()
    blob = adt.serialize(root)
    os.makedirs(os.path.dirname(os.path.abspath(OUT)), exist_ok=True)
    open(OUT, "wb").write(blob)
    print("%s: %d bytes" % (OUT, len(blob)))
    print("  chosen dram-base 0x%x size 0x%x" % (PHYS_BASE, MEM_SIZE - PANIC_LOG_SIZE))
    print("  gic 0x%x, virtual-timer-intid %d, timebase %d" % (GICD, VTIMER_INTID, TIMEBASE))
    print("  fb 0x%x %dx%d stride %d" % (FB, FB_W, FB_H, FB_STRIDE))
    print("  ufs 0x%x +0x%x" % (UFS, UFS_SIZE))
    print("  8 cpus, 1 A78 trio, X1 at 2.8416 GHz")
