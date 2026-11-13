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

## Installing it — the three conditions, measured 2026-11-13

Plain `pnputil /add-driver` is not enough. Each of these was found the hard way:

**1. The INF must carry Google's fastboot interface GUID.**

```
HKR,,DeviceInterfaceGUIDs,0x10000,"{F72FE0D4-CBCB-407d-8814-9ED673D0DD6B}"
```

`fastboot.exe` enumerates devices through that interface class, **not** by
VID/PID. With any other GUID the driver binds and Device Manager shows a healthy
*Android Bootloader Interface* — and `fastboot devices` still prints nothing.
The first version of this INF used an invented GUID and produced exactly that.

**2. The catalog must be signed by a certificate the machine trusts.**

Secure Boot is off on this host (`Confirm-SecureBootUEFI` -> False), so a
self-signed certificate works:

```powershell
$cert = New-SelfSignedCertificate -Type CodeSigningCert   -Subject 'CN=DSH local driver signing'   -CertStoreLocation 'Cert:\LocalMachine\My'   -KeyUsage DigitalSignature -KeyExportPolicy Exportable
# trust it as a root AND as a published signer
'Root','TrustedPublisher' | % {
  $s = New-Object System.Security.Cryptography.X509Certificates.X509Store($_,'LocalMachine')
  $s.Open('ReadWrite'); $s.Add($cert); $s.Close()
}
# build and sign the catalog
makecat dsh_fastboot.cdf
signtool sign /fd SHA256 /sm /s My /sha1 $cert.Thumbprint dsh_fastboot.cat
```

`/sm` is not optional: without it signtool searches the *user* store and fails
with *No certificates were found that met all the given criteria.* — a message
that reads like a broken certificate rather than a wrong store. The `.cdf`
hashes only the INF:

```
[CatalogHeader]
Name=dsh_fastboot.cat
ResultDir=<abs path to this folder>
PublicVersion=0x0000001
EncodingType=0x00010001

[CatalogFiles]
<HASH>dsh_fastboot.inf=dsh_fastboot.inf
```

**3. Then install it**, in an **Administrator** prompt:

```
pnputil /add-driver "fastboot_winusb.inf" /install
```

which must report

```
驱动程序包已安装在设备上: USB\VID_18D1&PID_D00D\56db9cb7
```

and then, with the phone still in bootloader mode:

```
fastboot devices
56db9cb7        fastboot
```

Without `/sm` the same driver reports
`无法添加驱动程序包: 第三方 INF 不包含数字签名信息` (*the third-party INF does
not contain digital signature information*), which is the unsigned-catalog case,
not a missing file.

## This bootloader does not implement getvar

Every `getvar` on it fails:

```
$ fastboot getvar product
getvar:product   FAILED (remote: 'GetVar Variable Not found')
```

so `product`, `unlocked`, `max-download-size`, `slot-count` and
`version-bootloader` are all unavailable. Do not script on `getvar` here;
`fastboot devices` is the only reliable probe, and `fastboot boot` /
`flash` answer on their own.

## Getting out without it

The bootloader does not need the host to leave: hold the power button for about
ten seconds and Android boots as it was. Both `fastboot boot` and everything on
this page are RAM-only; no partition is written either way.
