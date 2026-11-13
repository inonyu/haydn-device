# Installing

**Part of this has now been run on the phone.** The Windows side is solved, the
bootloader answers, and `fastboot boot` reaches the ABL and is refused with
`Load Error` — see the section of that name below. Nothing has been written to
any partition.

## The two facts

1. **userdata is 225 GiB and holds Android's data.** `/dev/block/sda34`,
   241,906,462,720 bytes. Writing an XNU root there erases it. The earlier
   sibling work says the same in one line: *"installs into the userdata
   partition and so erases Android's user data"*.
2. **The phone is unlocked.** `ro.boot.verifiedbootstate=orange`,
   `ro.boot.flash.locked=0`. `fastboot boot` was expected to work on that basis,
   and it is now measured: the command is accepted, the image transfers, and the
   ABL then refuses to load it (`Load Error`). Unlock status alone did not make
   this path work.

## Order

| Step | Writes | Reversible by |
| --- | --- | --- |
| `fastboot boot boot.img` | nothing | a reboot |
| Kernel reaches launchd | nothing | a reboot |
| Root volume in a **new** partition | a new partition only | deleting it |
| Root volume over userdata | Android's data | a factory image |

The third row is the one to aim for. Carving a separate partition keeps
Android intact and makes every later test a `fastboot boot`.

## Before touching the phone

```sh
# 1. the factory image, downloaded and checked
sha256sum haydn_*_V14.0.5.0.TKKCNXM*.tgz

# 2. the phone's own firmware, pulled as docs/firmware.md describes
#    (289 files, with their SHA-256)

# 3. the partition table, recorded so it can be restored
adb shell su -c 'cat /proc/partitions' > partitions.before.txt
```

## The open question

The partition layout has 100+ entries and `super` is dynamic, so a free
region large enough for a root volume may not exist. Deciding whether to
carve one — and where — needs the phone's full GPT, which this repository
does not have yet. That is the first thing the install work has to answer.

## The first test once the volume builds

`build.yml` publishes two files when the build is green: `SILICIUM_UEFI.fd`
(the firmware image itself) and `Mu-haydn.img` (the same volume with BootShim
prepended and wrapped in an Android boot header, which is what `fastboot boot`
takes).

```sh
adb reboot bootloader                      # or: adb reboot fastboot is NOT this
fastboot devices                           # must list the serial
fastboot boot Mu-haydn.img                 # RAM only; nothing is written
```

**On Windows the second line is where it stops**, and it stops silently: see
`drivers/windows/README.md`. Windows has no inbox driver for the fastboot
interface, so the phone enumerates as `USB\VID_18D1&PID_D00D` with
`CM_PROB_FAILED_INSTALL`, and both `fastboot devices` and `adb devices` print
nothing. Installing that .inf needs one Administrator prompt; leaving bootloader
mode does not need it at all (ten seconds on the power button).

### What actually binds it (measured 2026-11-13)

Three things have to be true, and the third is the one that costs an hour:

1. **The INF must carry Google's fastboot interface GUID**,
   `{F72FE0D4-CBCB-407d-8814-9ED673D0DD6B}`. `fastboot.exe` enumerates devices by
   that interface class, not by VID/PID. A locally invented GUID binds the
   driver — Device Manager shows *Android Bootloader Interface*, status OK — and
   `fastboot devices` still prints nothing.
2. **The catalog must be signed by a certificate the machine trusts.** With
   Secure Boot off (`Confirm-SecureBootUEFI` → False) a self-signed certificate
   works: `makecat` builds `dsh_fastboot.cat` from a `.cdf`, `signtool sign /sm`
   signs it, and the certificate goes into `LocalMachine\Root` **and**
   `LocalMachine\TrustedPublisher`. `/sm` matters: without it signtool looks in
   the user store and fails with *No certificates were found*.
3. **`pnputil /add-driver … /install`** then reports
   `驱动程序包已安装在设备上: USB\VID_18D1&PID_D00D\56db9cb7`, and

   ```
   $ fastboot devices
   56db9cb7         fastboot
   ```

   which is the phone in bootloader mode, seen from this machine.

The Google `usb_driver_r13-windows.zip` INF ships `PID_D001` and `PID_4EE7`, not
`PID_D00D`, so installing it alone leaves this bootloader unbound — the vendor
INF in `drivers/windows/` exists for exactly that PID.

**This bootloader rejects `getvar`** (`FAILED (remote: 'GetVar Variable Not
found')` for `product`, `unlocked`, `max-download-size`, `slot-count`) **and it
also rejects `reboot-bootloader`** (`FAILED (remote: 'unknown command')`). Do not
script on either; `fastboot devices` is the only reliable probe.

## `fastboot boot` — the first real answer (measured 2026-11-13)

The download works and the ABL **rejects the image**:

```
$ fastboot -v boot Mu-haydn.img
Sending 'boot.img' (1090 KB)                       OKAY [ 0.028s]
Booting                                            FAILED (remote: 'Failed to load/authenticate boot image: Load Error')
```

Getting that line required `-v`. Without it, `fastboot` prints
`Sending 'boot.img' (1090 KB)` and then **stalls with no further output at all**
— four separate attempts sat there for 100-150 s each and had to be killed, and
the phone answered `fastboot devices` throughout. Read that as "the host is
waiting on a REJECT it will not surface without `-v`", not as a hang in the
transfer. Always pass `-v` on this board.

`Load Error` is the ABL refusing the image before any of our code runs, so it
is a packaging question and not a boot-progress one.

**But the same ABL fails the same way on the phone's own boot partition**, which
is the fact that decides how much weight the line above carries:

```
$ fastboot continue
Resuming boot   FAILED (remote: 'Failed to load image from partition: Load Error')
```

`continue` asks the boot loader to boot whatever is in `boot_a` — the stock
Android image that boots perfectly well on a normal power cycle. It fails with
the identical `Load Error`. So on this handset the fastboot-side load path
rejects a known-good image too, and `Load Error` on `Mu-haydn.img` is evidence
that **this path is restricted**, not proof that the header is wrong. Both
explanations are still open; the v3 rebuild is what separates them.

### Why the image is the wrong shape

Two files in this repository disagree, and the artifact followed the wrong one:

| Record | Says |
| --- | --- |
| `board.toml` `[bootimg.image]` | `header_version = 3`, `pagesize = 4096` |
| `platform/haydnPkg/haydn.toml` | `header_version = 1` |
| `.github/workflows/build.yml` | writes its **own** `haydn.toml` inline with `header_version = 1` |

The CI step regenerates the device config rather than copying the one in
`platform/haydnPkg`, so the repository's `header_version` is not what gets
built. The artifact was measured:

```
Mu-haydn.img   ANDROID!  kernel_size 1,111,772  page_size 2,048  header_version 1
               ramdisk_size 5 (an empty page)  tags_addr 0x10000100
```

An SM8350 board on Android 13 launches through `vendor_boot` and expects
header v3/v4 at 4096-byte pages; a v1 image at 2 KiB pages is what `Load Error`
is about. `build_uefi.py` never passes `--pagesize` (its `argument_map` has no
such key) or `--header_version` 3/4 with the matching layout, so fixing this is
a change to the build, not to the phone.

Six repackaged variants of the same payload (v0/v1/v3/v4 × 2048/4096) were
prepared under `out/bootimg-variants/` for the next session; none of them could
be tried, because the phone left the bus first (below).

### The v3 rebuild, and how the first attempt will be run

The build now emits v3 at 4096-byte pages (`board.toml`, `haydn.toml` and the
CI step all agree, and `verify-volume.py` fails an image that is not). The first
artifact from it measures:

```
Mu-haydn.img   1,122,304 bytes
  header_version  3     header_size 1,580     page_size 4,096
  kernel_size     1,111,676        kernel offset 4,096
  gzip payload    decompresses to 2,097,264 bytes = BootShim 112 + the same FD
```

`tools/test-boot.ps1` in this repository tries it and the six prepared fallbacks
in one pass, always with `-v`, and records what each one answers. The order is
chosen so the first line is the informative one:

| # | Image | Why it is in this order |
| --- | --- | --- |
| 1 | `Mu-haydn-v3.img` | what the build now emits |
| 2 | `boot-sweetstyle.img` | sweet's exact recipe: v2, 4096 pages, **the phone's own DTB**, `console=null` |
| 3 | `boot-sweetstyle-nodtb.img` | same without the DTB, to tell "wrong header" from "missing DTB" |
| 4-6 | `boot-v4/v3/v2-p4096.img` | the header versions on their own |
| 7 | `boot-v1-p2048-dtb.img` | the old shape plus the DTB |

If #1 is still refused, #2 is the interesting one: every field in it is copied
from an image that is known to load on a Qualcomm ABL, so a refusal there says
the restriction is on this bootloader rather than in the header.

### Where the work stands, honestly

| | State |
| --- | --- |
| Windows driver | **solved** and scripted (`drivers/windows/Make-FastbootDriver.ps1`) |
| `fastboot devices` sees the phone | **yes**, `56db9cb7 fastboot` |
| Bootloader command support | measured; `getvar` and `reboot-bootloader` refused |
| Boot image shape | **fixed**: the build now emits v3 / 4096-byte pages, verified in the artifact and enforced by `scripts/verify-volume.py` |
| `fastboot boot` reaches the ABL | **yes**, and the ABL refuses with `Load Error` |
| The v3 image has been tried | **no** — the phone left USB (powered off) before it could be |
| Anything written to any partition | **no** |

The single unrun step is `fastboot -v boot` on the v3 image. Everything needed
for it is in place: the image, six fallbacks, and `tools/test-boot.ps1` to try
them in one pass.

### The phone dropped off USB

After the variant sweep the handset stopped enumerating entirely — no
`VID_18D1`, no `VID_05C6` EDL, nothing under any USB class, and a forced
`pnputil /scan-devices` found no new device. The bootloader had accepted
`oem poweroff` (`OKAY`) shortly before, and the last variant exchange ended in
`Status read failed (Too many links)`, so the board is most likely simply off.
**It needs a physical power-button press to come back**, which is why this
record stops here rather than at a screen photo.

Other commands, measured on the same session, so the next attempt does not
rediscover them:

| Command | Result |
| --- | --- |
| `fastboot continue` | **both outcomes seen**: `Resuming boot OKAY` (then Android came up on adb) and, on a later session, `Resuming boot FAILED (remote: 'Failed to load image from partition: Load Error')` — see below |
| `fastboot reboot` | works, but may re-enter the bootloader |
| `fastboot reboot-bootloader` | `unknown command` (worked once, then not) |
| `fastboot reboot recovery` | falls back to a normal Android boot on this phone |
| `fastboot --set-active=a` | `OKAY` |
| `fastboot oem poweroff` | `OKAY` (and the device stayed visible) |
| `fastboot oem device-info` | `unknown command` |
| `fastboot flashing get_unlock_ability` | `unknown command` |
| `fastboot getvar …` | `GetVar Variable Not found` for every variable |
| `adb shell su -c …` | `su: inaccessible or not found` — no root shell on this MIUI build |

`fastboot boot` loads the image into DDR and jumps to it. It does not write
`boot_a`, and a power cycle puts Android back. The worst case is a black screen.

**Nobody has run this yet**, and one thing about the current state decides when
it is safe to:

> The `Binaries/` this volume was built against are the venus set, copied
> because `Device-Binaries` has no `haydn` directory. venus is the same SoC and
> a different phone: its panel init and PMIC tables are in this image. A green
> build proves the package assembles and the FD links. It does not prove the
> display comes up.

If the screen stays black, the recovery is a ten-second power-button hold —
which needs a person with the phone in their hand. So the first `fastboot boot`
should be run with someone present, not unattended.