
"""Extract the members an XNU bring-up needs from the iPhone X IPSW.

refs/ipsw-x/:
  kernelcache.release.iphone10b   the iOS 16 kernel (unpatched, reference)
  DeviceTree.d22ap.im4p           the real D22AP device tree as shipped
  d22ap.adt                       its payload, which tools/mkadt.py reads for /product

Apple wraps the payload in DER with IA5String members:
  SEQUENCE { IA5String "IM4P", IA5String "dtre", IA5String "EmbeddedDeviceTrees-...",
             OCTET STRING <data> }
"""
import argparse, os, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument("ipsw", nargs="?",
                help="path to an iPhone10,3 / iPhone10,6 restore IPSW")
ap.add_argument("-o", "--outdir", default=os.path.join(REPO, "out", "ipsw-x"))
args = ap.parse_args()
if not args.ipsw:
    ap.error("an IPSW is required; it is Apple's and is not in this repository")

IPSW = args.ipsw
OUT = args.outdir
os.makedirs(OUT, exist_ok=True)
log = []

def read_len(buf, pos):
    n = buf[pos]; pos += 1
    if n & 0x80:
        k = n & 0x7F
        n = int.from_bytes(buf[pos:pos+k], "big"); pos += k
    return n, pos

def im4p_payload(buf):
    assert buf[0] == 0x30, "expected SEQUENCE, got 0x%02x" % buf[0]
    n, pos = read_len(buf, 1)
    end = pos + n
    strings, payload = [], None
    while pos < end:
        tag = buf[pos]
        ln, body = read_len(buf, pos + 1)
        val = buf[body:body+ln]
        if tag == 0x04:
            payload = val
            break
        strings.append(val.decode("latin-1"))
        pos = body + ln
    return strings, payload

with zipfile.ZipFile(IPSW) as z:
    for member, target in [
        ("kernelcache.release.iphone10b", "kernelcache.release.iphone10b"),
        ("Firmware/all_flash/DeviceTree.d22ap.im4p", "DeviceTree.d22ap.im4p"),
    ]:
        data = z.read(member)
        open(os.path.join(OUT, target), "wb").write(data)
        log.append("%-34s %10d bytes" % (target, len(data)))
        if target.endswith(".im4p"):
            strings, payload = im4p_payload(data)
            open(os.path.join(OUT, "d22ap.adt"), "wb").write(payload)
            log.append("%-34s %10d strings=%r" % ("d22ap.adt", len(payload), strings))
            log.append("  first 16 bytes: %s" % payload[:16].hex())

open(r"D:\design\k40-darwin\tools\ipsw-extract.log", "w").write("\n".join(log))
