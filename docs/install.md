# Installing

**Nothing here has been run on a phone.** This page records the shape the
install has to take and the two facts that decide it.

## The two facts

1. **userdata is 225 GiB and holds Android's data.** `/dev/block/sda34`,
   241,906,462,720 bytes. Writing an XNU root there erases it. The earlier
   sibling work says the same in one line: *"installs into the userdata
   partition and so erases Android's user data"*.
2. **The phone is unlocked.** `ro.boot.verifiedbootstate=orange`,
   `ro.boot.flash.locked=0`. `fastboot boot` works, so a RAM-only session —
   loader, kernel and payload in memory, nothing written — is available
   before any partition is touched.

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
| `fastboot continue` | `Resuming boot OKAY` — resumes **Android**, not our image |
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