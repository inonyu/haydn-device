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