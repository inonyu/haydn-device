<#
.SYNOPSIS
    Try every prepared boot image on the haydn bootloader and record what each says.

.DESCRIPTION
    Runs when the phone is back on USB. RAM-only: `fastboot boot` writes nothing,
    and a power cycle returns the phone to Android.

    Always passes -v. Without it this bootloader prints "Sending 'boot.img'" and
    then nothing at all for 100-150 s, which reads like a hang and is actually an
    unsurfaced rejection (docs/install.md).

    Order matters: the v3 image the build now emits comes first, then the
    sweet-style v2 + the phone's own DTB, then the rest.
#>
[CmdletBinding()]
param(
    [string] $Serial = '56db9cb7',
    [int]    $TimeoutSec = 45
)

$ErrorActionPreference = 'Continue'

$fb  = 'D:\AndroidSDK\platform-tools\fastboot.exe'
$adb = 'D:\AndroidSDK\platform-tools\adb.exe'
$log = 'D:\design\k40-darwin\tools\boot-matrix.log'

$images = @(
    'D:\design\k40-darwin\out\haydn-uefi-v3\Mu-haydn-v3.img',
    'D:\design\k40-darwin\out\bootimg-variants\boot-sweetstyle.img',
    'D:\design\k40-darwin\out\bootimg-variants\boot-sweetstyle-nodtb.img',
    'D:\design\k40-darwin\out\bootimg-variants\boot-v4-p4096.img',
    'D:\design\k40-darwin\out\bootimg-variants\boot-v3-p4096.img',
    'D:\design\k40-darwin\out\bootimg-variants\boot-v2-p4096.img',
    'D:\design\k40-darwin\out\bootimg-variants\boot-v1-p2048-dtb.img'
)

'=== boot matrix ' + (Get-Date -Format o) + ' ===' | Out-File -Encoding utf8 $log

# Get the phone into bootloader mode, from whichever mode it is in.
$fbDev = ((& $fb devices 2>&1 | Out-String).Trim())
if (-not $fbDev) {
    $adbDev = ((& $adb devices 2>&1 | Out-String))
    if ($adbDev -match [regex]::Escape($Serial)) {
        'phone is in Android; rebooting to bootloader' | Out-File -Encoding utf8 -Append $log
        & $adb -s $Serial reboot bootloader 2>&1 | Out-Null
        for ($i = 0; $i -lt 30; $i++) {
            Start-Sleep -Milliseconds 1500
            if (((& $fb devices 2>&1 | Out-String).Trim()) -match $Serial) { break }
        }
    }
}

$fbDev = ((& $fb devices 2>&1 | Out-String).Trim())
if (-not ($fbDev -match $Serial)) {
    'phone is not in bootloader mode; nothing tried' | Out-File -Encoding utf8 -Append $log
    Get-Content $log -Raw
    return
}
('fastboot sees: ' + ($fbDev -replace '\s+', ' ')) | Out-File -Encoding utf8 -Append $log

foreach ($img in $images) {
    if (-not (Test-Path $img)) {
        ('MISSING  ' + $img) | Out-File -Encoding utf8 -Append $log
        continue
    }
    $name = Split-Path -Leaf $img
    $o = Join-Path $env:TEMP 'bm-out.txt'
    $e = Join-Path $env:TEMP 'bm-err.txt'
    $p = Start-Process -FilePath $fb -ArgumentList @('-v', 'boot', $img) -NoNewWindow -PassThru `
        -RedirectStandardOutput $o -RedirectStandardError $e
    $done = $p.WaitForExit($TimeoutSec * 1000)
    if (-not $done) { $p.Kill(); $verdict = 'TIMEOUT after ' + $TimeoutSec + 's' }
    else {
        $text = (((Get-Content $o, $e -Raw -ErrorAction SilentlyContinue) -join ' ') -replace '\s+', ' ').Trim()
        $verdict = $text
    }
    ('{0,-30} {1}' -f $name, $verdict) | Out-File -Encoding utf8 -Append $log

    # If the phone left fastboot, something ran. Give it time, then look.
    Start-Sleep -Seconds 2
    $now = ((& $fb devices 2>&1 | Out-String).Trim())
    if (-not ($now -match $Serial)) {
        ('    phone left fastboot after ' + $name + ' - waiting 25s to see where it lands') | Out-File -Encoding utf8 -Append $log
        for ($i = 0; $i -lt 25; $i++) {
            Start-Sleep -Seconds 1
            $a = ((& $adb devices 2>&1 | Out-String))
            $f = ((& $fb devices 2>&1 | Out-String).Trim())
            if ($a -match ($Serial + '\s+device')) {
                '    -> came up as ANDROID' | Out-File -Encoding utf8 -Append $log
                break
            }
            if ($f -match $Serial) {
                '    -> back in fastboot' | Out-File -Encoding utf8 -Append $log
                break
            }
        }
        if (-not (((& $fb devices 2>&1 | Out-String).Trim()) -match $Serial)) {
            '    -> not on USB at all; stopping here' | Out-File -Encoding utf8 -Append $log
            break
        }
    }
}

'=== done ' + (Get-Date -Format o) + ' ===' | Out-File -Encoding utf8 -Append $log
Get-Content $log -Raw
