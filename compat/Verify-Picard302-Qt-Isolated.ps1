# Run ONLY on BMAX-B6 as megal. Test candidate; never deploy to Picard.
# Uses independent Python venv/PyQt wheels; never reuses Picard _internal.
[CmdletBinding()]
param(
    [switch]$InstallDependencies,
    [switch]$SkipPythonTests
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

if ($env:COMPUTERNAME -ine 'BMAX-B6' -or $env:USERNAME -ine 'megal') {
    throw 'Only the authenticated BMAX-B6 megal test account is supported.'
}
$root = Join-Path $env:LOCALAPPDATA 'NEOWULF\Picard3\release-candidates\20261018-native302'
$project = Join-Path $root 'PicardWulf'
$upstream = Join-Path $root 'picard-3.0.2'
$venv = Join-Path $root '.qt-standalone-venv'
$python = Join-Path $venv 'Scripts\python.exe'
foreach ($path in @($root, $project, $upstream)) {
    $item = Get-Item -LiteralPath $path -ErrorAction Stop
    if (-not $item.PSIsContainer) { throw "Not a directory: $path" }
    if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Refusing reparse point in isolated candidate: $path"
    }
}
if (-not (Test-Path -LiteralPath (Join-Path $project 'compat\qt_isolated_probe.py'))) {
    throw 'Current PicardWulf candidate lacks isolated Qt test code: git pull first.'
}
if (-not (Test-Path -LiteralPath (Join-Path $upstream '.git'))) {
    throw 'Pinned 3.0.2 upstream checkout missing; refusing alternate Picard.'
}
$baseHead = (& git -C $upstream rev-parse HEAD)
if ($LASTEXITCODE -ne 0 -or $baseHead.Trim() -ne '02fece92db40acf236722f76e4a9234d5562f9d4') {
    throw "Unknown upstream Picard revision: $baseHead"
}
$guard = Join-Path $upstream 'picard\file.py'
if (-not (Select-String -LiteralPath $guard -Pattern 'collision_native_plan' -Quiet)) {
    throw 'Native Picard source patch missing in candidate; no GUI validation possible.'
}

# Report running production state but never stop, start or update Picard.exe.
$production = 'C:\Program Files\MusicBrainz Picard\picard.exe'
if (-not (Test-Path -LiteralPath $production)) { throw 'Production Picard not found.' }
Write-Output ('PRODUCTION_VERSION_READ_ONLY=' + (Get-Item -LiteralPath $production).VersionInfo.ProductVersion)
Write-Output ('PRODUCTION_PROCESS_COUNT_READ_ONLY=' + @(Get-Process picard -ErrorAction SilentlyContinue).Count)
Write-Output ('STAGED_PICARDWULF_HEAD=' + (& git -C $project rev-parse HEAD))
Write-Output ('STAGED_UPSTREAM_HEAD=' + $baseHead)

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    if (-not $InstallDependencies) {
        throw 'Standalone Qt virtualenv missing. Rerun explicitly with -InstallDependencies.'
    }
    & python -m venv $venv
    if ($LASTEXITCODE -ne 0) { throw 'Isolated Python virtualenv creation failed.' }
}
if ($InstallDependencies) {
    # Source lives only under the isolated candidate. Dependency wheels are
    # acquired from the normal trusted package index, not the bundled app.
    & $python -m pip install --disable-pip-version-check --only-binary=:all: -e $upstream
    if ($LASTEXITCODE -ne 0) { throw 'Standalone Picard/PyQt dependencies not installed.' }
}

$oldApp = $env:APPDATA
$oldLocal = $env:LOCALAPPDATA
$oldPyPath = $env:PYTHONPATH
$oldPicard = $env:PICARD302_SOURCE
$oldPlatform = $env:QT_QPA_PLATFORM
$sandbox = Join-Path $root 'test-sandbox\qt-standalone'
$roaming = Join-Path $sandbox 'Roaming'
$local = Join-Path $sandbox 'Local'
New-Item -ItemType Directory -Path $roaming,$local -Force | Out-Null
try {
    $env:APPDATA = $roaming
    $env:LOCALAPPDATA = $local
    $env:PYTHONPATH = $project
    $env:PICARD302_SOURCE = $upstream
    $env:QT_QPA_PLATFORM = 'offscreen'
    Push-Location $project
    try {
        & $python -B -m compat.qt_isolated_probe --upstream $upstream
        if ($LASTEXITCODE -ne 0) { throw 'Real Qt/Picard source runtime smoke failed.' }
        Write-Output 'REAL_QT_OFFSCREEN_NATIVE_API_SMOKE=PASS'
        if (-not $SkipPythonTests) {
            & $python -B -m unittest discover -s tests -q
            if ($LASTEXITCODE -ne 0) { throw 'PicardWulf Windows regression failed.' }
        }
    } finally {
        Pop-Location
    }
} finally {
    $env:APPDATA = $oldApp
    $env:LOCALAPPDATA = $oldLocal
    $env:PYTHONPATH = $oldPyPath
    $env:PICARD302_SOURCE = $oldPicard
    $env:QT_QPA_PLATFORM = $oldPlatform
}
Write-Output 'ISOLATED_CANDIDATE_QT_CHECK=PASS'
Write-Output 'PRODUCTION_PICARD_AND_AUDIO_UNCHANGED_BY_THIS_SCRIPT'
