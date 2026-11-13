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

**`fastboot boot` never completed (measured 2026-11-13).** Four attempts, all of
them stopping at the same place:

```
$ fastboot boot Mu-haydn.img
Sending 'boot.img' (1090 KB)
<never returns>
```

It hangs in the download phase, not at the jump: the phone stayed in bootloader
mode and kept answering `fastboot devices` after each 100-150 s timeout and
kill. `--max-download-size` is not an option this fastboot has, so the
"negotiate a smaller download" workaround is not available either. The host
side of this is **unfinished**: the image is built and the driver binds, but one
successful `fastboot boot` has not been observed on this machine.

If a later attempt gets past `Sending`, the next line should be
`Booting OKAY`, then the screen. Anything else is a different failure and
should be recorded here with its exact output.

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