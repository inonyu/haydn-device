# Firmware: what to take from the phone, and how

289 files, 30.14 MB, in four groups. None of them belongs in this repository:
they are Xiaomi's, and the licence of this project promises never to carry
them. What is here instead is this page, so the same set can be taken again.

The extraction was done on 2026-11-12 on a phone running MIUI
V14.0.5.0.TKKCNXM (Android 13, kernel 5.4.147-qgki-gc59a695f9a4d) with root.

## Prerequisite: root

`adb shell` alone cannot read any of these paths: they are owned by root and
SELinux is enforcing. Root comes from Magisk, and the manager app has to match
the running daemon's version (a mismatch shows up as *"this build cannot run"*
and no request is ever honoured).

```sh
adb shell /debug_ramdisk/magisk -V      # the daemon's versionCode, e.g. 30100
# install the manager release with the same versionCode, then:
adb shell '/debug_ramdisk/su -c id'     # uid=0(root) ... context=u:r:magisk:s0
```

## Group 1: GPU (7 files, 0.12 MB)

| File | Bytes | SHA-256 |
| --- | --- | --- |
| `a660_gmu.bin` | 55,256 | `6BB9360A1601253A86EE3AE1B9B916F5F1832A72D55E9B8573567F1740C94E2B` |
| `a660_sqe.fw` | 40,496 | `F911A4BADF7B56719CB130492BC39F9EDB85335F54E8B4983B5C67EB9E6204BB` |
| `a660_zap.mdt` | 6,860 | `E730DB1C20727EBFECF96B863F79308D9C1BC3362B95BC2845053012F0EF69CC` |
| `a660_zap.elf` | 14,264 | `BC5FFB63C0AD3BC1267FBEF50C8F504499F6B26B1F6562A96D84304696676EB4` |
| `a660_zap.b00` | 148 | `CE73476CB8CF86ABC79885DDC4E178DFA7884FC8F5ED7254B6D756A4244A23BF` |
| `a660_zap.b01` | 6,712 | `0019A8A3BEC3A6FAC20BA340405AED02769F24D4DD1134BF71B01972C90C19F7` |
| `a660_zap.b02` | 1,976 | `1A5FDBF458EA547C5459B301AB577A83461797B77BDE9501FB48FC62D2D5F185` |

Source: `/vendor/firmware/a660_*`.

The ZAP pair is the one that matters most: it is the TrustZone-signed shader
without which the 3D core stays locked in secure mode. `mdt` is the header
that points at the `b00..b02` segments; `elf` is the joined image.

## Group 2: Wi-Fi (148 files, 8.41 MB)

| File | Bytes | Where |
| --- | --- | --- |
| `bdwlan.e01` .. `bdwlan.e93`, `e96`, `ee1`, `elf` | 59,868 each | `/vendor/firmware_mnt/image/` |
| `WCNSS_qcom_cfg.ini` | 15,420 | `/vendor/etc/wifi/qca6750/` |

147 segments plus the joined `bdwlan.elf`. The per-segment SHA-256 set is in
the extraction manifest this board's first pull produced; regenerate it with
the script below rather than trusting a copied list.

`/vendor/firmware_mnt` is a separate vfat partition (`sde5`, 248 MB, 554
files, mounted read-only). The BDF is **not** under `/vendor/firmware/`:
looking there finds only `wlan/qca_cld`, which holds symlinks and the config.

## Group 3: ADSP (29 files, 19.97 MB)

`/vendor/firmware_mnt/image/adsp.mdt` plus `adsp.b00` .. `adsp.b25`,
`adspr.jsn`, `adspua.jsn`. The largest is `adsp.b20` at 12.06 MB; `adsp.b03`
(2.40 MB), `adsp.b10` (2.03 MB) and `adsp.b16` (1.99 MB) come next.

The codec modules in `/vendor/dsp/adsp/` (AudioSphere, FLAC, LDAC, AAC and
the rest) are a separate set and are not needed until audio is attempted.

## Group 4: Bluetooth (102 files, 0.86 MB)

`/vendor/bt_firmware/image/`: `hpbtfw10.tlv` (196,276), `hpbtfw21.tlv`
(82,648), and the `hpnv21*` NVRAM variants (6,319 to 6,535 each).

`/vendor/bt_firmware` is a third vfat partition (`sde6`), owned by
`bluetooth:net_bt` with mode 0750 — root is required even to list it.

## Plus: device tree and partition table

| Item | Bytes | Note |
| --- | --- | --- |
| `/sys/firmware/fdt` | 799,754 | the live tree, as a DTB |
| `/proc/partitions` | 6,037 | the block devices at the time of capture |

The live DTB is 6,300 bytes larger than the one an earlier port recorded
(793,454): the phone has taken a system update since.

## Taking it again

One root session is enough. Keep it short: MIUI's USB debugging drops the
transport when a root session holds the device too long, and the loop of
`offline` / `unauthorized` / `device` that follows is not a fault in the
extraction.

```sh
OUT=/data/local/tmp/fw
su -c "rm -rf $OUT; mkdir -p $OUT/fw-gpu $OUT/fw-wifi $OUT/fw-adsp $OUT/fw-bt $OUT/meta"

su -c "cp /vendor/firmware/a660_* $OUT/fw-gpu/"
su -c "cp /vendor/firmware_mnt/image/bdwlan.e* $OUT/fw-wifi/"
su -c "cp /vendor/etc/wifi/qca6750/WCNSS_qcom_cfg.ini $OUT/fw-wifi/"
su -c "cp /vendor/firmware_mnt/image/adsp.* $OUT/fw-adsp/"
su -c "cp -r /vendor/bt_firmware/image/. $OUT/fw-bt/"
su -c "cp /sys/firmware/fdt $OUT/meta/haydn-fdt.dtb; cat /proc/partitions > $OUT/meta/partitions.txt"

su -c "cd $OUT && find . -type f -exec sha256sum {} \; > ../SHA256SUMS.txt"
su -c "cd /data/local/tmp && tar -czf fw.tgz fw && chmod 644 fw.tgz"
adb pull /data/local/tmp/fw.tgz
```

Then `tar xzf fw.tgz` and compare against the manifest. A single mismatched
hash means a different phone, a different build, or a truncated copy: check
before building anything with it.

## Not taken yet

Two inputs a port needs that this page does not yet describe:

- **The panel's DSI timing.** It lives in the `dtbo` partition
  (`androidboot.dtbo_idx=21`); the base tree only names the panel. Reading
  `dtbo_a` needs root and has not been done.
- **The modem's image.** Recorded as present (`modem_a`) but not pulled;
  cellular is P9 and nothing there can start before P1.
