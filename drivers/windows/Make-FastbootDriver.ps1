<#
.SYNOPSIS
    Bind the Android bootloader (fastboot) interface on Windows.

.DESCRIPTION
    Windows has no inbox driver for `USB\VID_18D1&PID_D00D`, so a phone in
    bootloader mode enumerates with CM_PROB_FAILED_INSTALL and `fastboot devices`
    prints nothing.

    Three things have to hold, and the second is the one that silently fails:

      1. The INF carries Google's fastboot interface GUID.
         fastboot.exe enumerates by *interface class*, not by VID/PID, so a
         different GUID binds the driver and still leaves `fastboot devices` empty.
      2. The catalog is signed by a certificate this machine trusts. With Secure
         Boot off a self-signed certificate works, but it must go into both
         LocalMachine\Root and LocalMachine\TrustedPublisher, and signtool needs
         /sm — without it, it searches the user store and reports "No
         certificates were found that met all the given criteria".
      3. The catalog is regenerated from the .cdf with makecat before signing;
         a stale .cat does not describe the current INF.

    Run this from an elevated prompt: it writes to LocalMachine certificate
    stores and installs a driver package.

.PARAMETER Subject
    Subject of the self-signed code-signing certificate to create or reuse.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File drivers\windows\Make-FastbootDriver.ps1
#>
[CmdletBinding()]
param(
    [string] $Subject = 'CN=haydn-device fastboot signing'
)

$ErrorActionPreference = 'Stop'

$here   = Split-Path -Parent $MyInvocation.MyCommand.Path
$inf    = Join-Path $here 'fastboot_winusb.inf'
$cdf    = Join-Path $here 'fastboot.cdf'
$cat    = Join-Path $here 'fastboot_winusb.cat'

if (-not (Test-Path $inf)) { throw "missing $inf" }

$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) { throw 'run this from an elevated prompt: it writes to LocalMachine certificate stores' }

# makecat and signtool ship with the Windows SDK; find the newest x64 copy.
function Find-SdkTool([string] $name) {
    $roots = @(
        "${env:ProgramFiles(x86)}\Windows Kits\10\bin",
        "${env:ProgramFiles}\Windows Kits\10\bin"
    ) | Where-Object { Test-Path $_ }
    foreach ($root in $roots) {
        $hit = Get-ChildItem $root -Recurse -Filter $name -ErrorAction SilentlyContinue |
               Where-Object { $_.FullName -match '\\x64\\' } |
               Sort-Object FullName -Descending | Select-Object -First 1
        if ($hit) { return $hit.FullName }
    }
    throw "could not find $name (install the Windows SDK)"
}

$makecat  = Find-SdkTool 'makecat.exe'
$signtool = Find-SdkTool 'signtool.exe'

# 1. certificate: reuse the newest matching one, else create it
$cert = Get-ChildItem Cert:\LocalMachine\My |
        Where-Object { $_.Subject -eq $Subject } |
        Sort-Object NotAfter -Descending | Select-Object -First 1
if (-not $cert) {
    Write-Host "creating $Subject"
    $cert = New-SelfSignedCertificate -Type CodeSigningCert -Subject $Subject `
        -CertStoreLocation 'Cert:\LocalMachine\My' -KeyUsage DigitalSignature `
        -KeyExportPolicy Exportable -NotAfter (Get-Date).AddYears(5)
} else {
    Write-Host "reusing $($cert.Thumbprint)"
}

# 2. trust it as a root and as a published signer
foreach ($storeName in 'Root', 'TrustedPublisher') {
    $store = New-Object System.Security.Cryptography.X509Certificates.X509Store($storeName, 'LocalMachine')
    $store.Open('ReadWrite')
    if (-not ($store.Certificates | Where-Object { $_.Thumbprint -eq $cert.Thumbprint })) {
        $store.Add($cert)
        Write-Host "added to LocalMachine\$storeName"
    }
    $store.Close()
}

# 3. catalogue + signature
if (Test-Path $cat) { Remove-Item $cat -Force }
Push-Location $here
try {
    & $makecat $cdf
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $cat)) { throw "makecat failed for $cdf" }
} finally {
    Pop-Location
}

$p = Start-Process -FilePath $signtool -NoNewWindow -Wait -PassThru `
    -ArgumentList @('sign', '/fd', 'SHA256', '/sm', '/s', 'My', '/sha1', $cert.Thumbprint, $cat)
if ($p.ExitCode -ne 0) { throw "signtool failed with exit $($p.ExitCode)" }

$sig = Get-AuthenticodeSignature $cat
Write-Host "catalogue signature: $($sig.Status)"
if ($sig.Status -ne 'Valid') { throw "catalogue did not verify: $($sig.Status)" }

# 4. install
& pnputil.exe /add-driver $inf /install
if ($LASTEXITCODE -ne 0) { throw "pnputil failed with exit $LASTEXITCODE" }
& pnputil.exe /scan-devices | Out-Null

Start-Sleep -Seconds 2
$dev = Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -match 'VID_18D1&PID_D00D' }
foreach ($d in $dev) { Write-Host "device: $($d.Status) | $($d.FriendlyName) | $($d.InstanceId)" }
if (-not $dev) { Write-Host 'no bootloader device present — put the phone in bootloader mode and re-run' }
