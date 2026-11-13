# Windows needs a driver for fastboot

Windows has a driver for the ADB interface and none for the fastboot
(bootloader) interface. A phone in bootloader mode therefore appears under
Universal Serial Bus devices as **Android** with a warning triangle, its status
is `CM_PROB_FAILED_INSTALL`, and `fastboot devices` prints nothing at all --
which reads exactly like a dead cable or a dead phone.

Observed on the development host on 2026-11-13:

```
Get-PnpDevice | ? { $_.InstanceId -match 'VID_18D1' }
  Error | Android | USB\VID_18D1&PID_D00D\56DB9CB7

fastboot devices
  (nothing)
```

`VID_18D1 PID_D00D` is the Android bootloader interface. There is no way
around it in user mode: `pnputil`, `devcon` and the Device Manager all need an
Administrator prompt, and the bootloader does not implement the Microsoft OS
descriptor that would let Windows pick WinUSB on its own.

## Installing it

The `.inf` here binds WinUSB to the two Android bootloader hardware ids and
nothing else. In an **Administrator** prompt:

```
pnputil /add-driver "drivers\windows\fastboot_winusb.inf" /install
```

or right-click the file -> Install.

Then, with the phone still in bootloader mode:

```
fastboot devices
56db9cb7        fastboot
```

## Getting out without it

The bootloader does not need the host to leave: hold the power button for about
ten seconds and Android boots as it was. Both `fastboot boot` and everything on
this page are RAM-only; no partition is written either way.
