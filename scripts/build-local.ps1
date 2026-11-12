<#
.SYNOPSIS
  Build a Mu-Silicium platform on this machine, one variable at a time.

.DESCRIPTION
  The recommended first test is NOT haydn: it is venus, the board this
  repository's platform was derived from. If venus builds, the toolchain is
  right and any haydn failure is haydnPkg's. If venus does not, the toolchain
  is wrong and building haydn would tell you nothing.

  Control one variable at a time. That is the whole point of this script.

.PARAMETER Device
  venus (the control) or haydn (the thing under test).

.EXAMPLE
  ./scripts/build-local.ps1 -Device venus
  ./scripts/build-local.ps1 -Device haydn
#>
param(
    [ValidateSet('venus', 'haydn')]
    [string]$Device = 'venus',

    [ValidateSet('DEBUG', 'RELEASE')]
    [string]$Mode = 'DEBUG',

    [string]$MuRoot = 'D:\design\k40-darwin\Mu-Silicium'
)

$ErrorActionPreference = 'Stop'

function Say($text, $colour = 'Gray') {
    Write-Host $text -ForegroundColor $colour
}

function Step($n, $text) {
    Write-Host ''
    Say ("[$n] $text") 'Cyan'
}

# --- 0. what is here -------------------------------------------------------
Step 0 'Checking the toolchain'

$have = @{}
foreach ($tool in @('clang', 'lld', 'nasm', 'make', 'python', 'git')) {
    $found = Get-Command $tool -ErrorAction SilentlyContinue
    $have[$tool] = $null -ne $found
    Say ("  {0,-8} {1}" -f $tool, $(if ($found) { 'ok   ' + $found.Source } else { 'MISSING' })) `
        $(if ($found) { 'Gray' } else { 'Red' })
}

$missing = $have.GetEnumerator() | Where-Object { -not $_.Value } | ForEach-Object { $_.Key }
if ($missing) {
    Say ''
    Say ('missing: ' + ($missing -join ', ')) 'Red'
    Say 'Install them and reopen the shell so PATH updates:' 'Yellow'
    Say '  winget install --id LLVM.LLVM NASM.NASM ezwinports.make' 'Yellow'
    exit 1
}

# --- 1. the tree -----------------------------------------------------------
Step 1 'Checking the Mu-Silicium tree'

if (-not (Test-Path $MuRoot)) {
    Say "  $MuRoot does not exist" 'Red'
    Say '  git clone --recursive --depth 1 https://github.com/Project-Silicium/Mu-Silicium.git' 'Yellow'
    exit 1
}

if (-not (Test-Path (Join-Path $MuRoot 'Build')) -and -not (Test-Path (Join-Path $MuRoot 'Common\Mu\MdePkg'))) {
    Say '  the submodules are not checked out; waiting for the clone to finish' 'Yellow'
}

$pkg = Get-ChildItem (Join-Path $MuRoot 'Platforms') -Recurse -Directory -Filter "${Device}Pkg" -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $pkg) {
    Say "  Platforms/**/${Device}Pkg not found" 'Red'
    exit 1
}
Say "  ${Device}Pkg at $($pkg.FullName)" 'Gray'

# --- 2. the device config --------------------------------------------------
Step 2 'Checking Resources/Configs'

$config = Join-Path $MuRoot "Resources\Configs\$Device.toml"
if (Test-Path $config) {
    Say "  $Device.toml ok" 'Gray'
} else {
    Say "  $Device.toml missing -- copying this repository's" 'Yellow'
    $ours = Join-Path $PSScriptRoot '..\platform\haydnPkg\haydn.toml'
    if (Test-Path $ours) {
        Copy-Item $ours $config
        Say '  copied' 'Gray'
    } else {
        Say '  and this repository has none either' 'Red'
        exit 1
    }
}

# --- 3. build --------------------------------------------------------------
Step 3 "Building $Device ($Mode)"
Say '  this is where it either works or tells us why not' 'Gray'

$log = Join-Path $PSScriptRoot "..\build-$Device.log"
Push-Location $MuRoot
try {
    $env:PYTHONUNBUFFERED = '1'
    & python build_uefi.py -d $Device -r $Mode 2>&1 | Tee-Object -FilePath $log
    $code = $LASTEXITCODE
} finally {
    Pop-Location
}

# --- 4. what came out ------------------------------------------------------
Step 4 'Result'

if ($code -eq 0) {
    Say '  the build succeeded' 'Green'
    Get-ChildItem (Join-Path $MuRoot "Build\${Device}Pkg") -Recurse -Filter '*.fd' -ErrorAction SilentlyContinue |
        ForEach-Object { Say ('  ' + $_.FullName + '  ' + $_.Length + ' bytes') 'Green' }
} else {
    Say "  the build failed (exit $code); the log is $log" 'Red'
    Say ''
    Say '  the first error:' 'Yellow'
    Select-String -Path $log -Pattern 'error|not found|failed' -ErrorAction SilentlyContinue |
        Select-Object -First 5 | ForEach-Object { Say ('    ' + $_.Line.Trim()) 'Yellow' }
    Say ''
    Say '  the files it said it could not find:' 'Yellow'
    (Select-String -Path $log -Pattern '[A-Za-z0-9_./\-]+\.(inf|dec|fdf|dsc)' -AllMatches -ErrorAction SilentlyContinue |
        ForEach-Object { $_.Matches } | ForEach-Object { $_.Value } | Sort-Object -Unique | Select-Object -First 20) |
        ForEach-Object { Say ('    ' + $_) 'Yellow' }
}

exit $code
