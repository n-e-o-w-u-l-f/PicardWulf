param([switch]$LiveUpdate, [switch]$AllowUnrecognizedExisting)
# PicardWulf 1.0 – filesystem plugin installation without picard-cli.exe.
# Source-of-truth: Picard 3 picard/const/appdirs.py (plugin_folder),
# picard/tagger.py (manager.add_directory) and plugin3/manager/__init__.py.
# Only writes to the current user's plugin directory; does not edit Picard.ini.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
function Stop-Install([string]$message) {
    Write-Host "NICHT INSTALLIERT: $message" -ForegroundColor Red
    exit 1
}
if ($env:COMPUTERNAME -ine 'BMAX-B6') {
    Stop-Install 'Dieser Installer ist fuer BMAX-B6 vorgesehen.'
}
if ($env:USERNAME -ine 'megal') {
    Stop-Install 'Bitte am Desktop als megal ausfuehren, nicht in der chatgpt-login-SSH-Sitzung.'
}
if ([string]::IsNullOrWhiteSpace($env:APPDATA)) {
    Stop-Install 'APPDATA fehlt. Benutzerbezogenen Pluginordner nicht nachweisbar.'
}
$picardRunning = @(Get-Process -Name 'picard' -ErrorAction SilentlyContinue).Count -gt 0
if ($picardRunning) {
    if (!$LiveUpdate) {
        Stop-Install 'Picard ist geoeffnet. Fuer ein Update OHNE Picard-Neustart: Plugin in Optionen > Plugins deaktivieren und Install-PicardWulf-Live.cmd verwenden.'
    }
    Write-Host 'LIVE-UPDATE: Picard BLEIBT OFFEN. Nur das DEAKTIVIERTE Plugin wird aktualisiert.' -ForegroundColor Yellow
    Write-Host 'Bitte in Picard unter Optionen > Plugins zuerst PicardWulf deaktivieren.' -ForegroundColor Yellow
    Write-Host 'Wenn Picard nicht reagiert, ABBRECHEN. Niemals den Prozess beenden.' -ForegroundColor Yellow
    $confirm = Read-Host 'Bestaetigung (JA-PLUGIN-DEAKTIVIERT)'
    if ($confirm -cne 'JA-PLUGIN-DEAKTIVIERT') {
        Stop-Install 'Live-Upgrade nicht freigegeben. Keine Aenderung vorgenommen.'
    }
}
$source = Join-Path $PSScriptRoot 'neowulf_picard_repair'
$required = @('__init__.py', 'MANIFEST.toml', 'repair_logic.py', 'universal_engine.py', 'universal_adapters.py', 'credentials.py', 'native_workflow.py', 'native_ui.py', 'auto_selection.py', 'auto_apply.py', 'background_io.py', 'provider_policy.py', 'save_tracking.py', 'cluster_matching.py', 'cluster_ui.py', 'gold_retirement.py', 'collision_preview.py', 'retention_policy.py', 'staged_flac_import.py', 'picard_safe_import.py', 'native_move_bridge.py', 'wwe_series.py')
foreach ($item in $required) {
    if (!(Test-Path -LiteralPath (Join-Path $source $item) -PathType Leaf)) {
        Stop-Install "Paket unvollstaendig: $item"
    }
}
$manifest = Get-Content -LiteralPath (Join-Path $source 'MANIFEST.toml') -Raw -Encoding UTF8
if ($manifest -notmatch 'uuid\s*=\s*"cf3c909b-eccb-4b89-90e3-55eb68e0176c"') {
    Stop-Install 'Unerwartete Pluginidentitaet: MANIFEST.toml.'
}
$picardCandidates = @()
if ($env:ProgramFiles) { $picardCandidates += (Join-Path $env:ProgramFiles 'MusicBrainz Picard\picard.exe') }
if (${env:ProgramFiles(x86)}) { $picardCandidates += (Join-Path ${env:ProgramFiles(x86)} 'MusicBrainz Picard\picard.exe') }
if ($env:LOCALAPPDATA) { $picardCandidates += (Join-Path $env:LOCALAPPDATA 'Programs\MusicBrainz Picard\picard.exe') }
$picard = $picardCandidates | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) } | Select-Object -First 1
if (!$picard) { Stop-Install 'picard.exe nicht gefunden. Bitte Picard installieren oder Pfad pruefen.' }

# Picard 3: QStandardPaths.AppDataLocation => %APPDATA%\MusicBrainz\Picard.
# Override only when deliberately set by the owner for Picard itself.
if ([string]::IsNullOrWhiteSpace($env:PICARD_PLUGIN_DIR)) {
    $pluginRoot = Join-Path $env:APPDATA 'MusicBrainz\Picard\plugins3'
} else {
    $pluginRoot = $env:PICARD_PLUGIN_DIR
}
$target = Join-Path $pluginRoot 'neowulf_picard_repair'
$stage = Join-Path $pluginRoot ('.neowulf-stage-' + [guid]::NewGuid().ToString('N'))

# SHA-256 independent of an optional PowerShell Utility hashing cmdlet.
# Some Windows PowerShell sessions lack that cmdlet; use streaming .NET hashing
# so full audio files and plugin source are never loaded into memory.
function Get-FileSha256([string]$path) {
    $stream = $null
    $sha256 = $null
    try {
        $stream = [System.IO.File]::OpenRead($path)
        $sha256 = [System.Security.Cryptography.SHA256]::Create()
        if ($null -eq $sha256) { throw 'SHA-256-Kryptografiedienst nicht verfuegbar.' }
        return [System.BitConverter]::ToString($sha256.ComputeHash($stream)).Replace('-', '')
    } finally {
        if ($null -ne $sha256) { $sha256.Dispose() }
        if ($null -ne $stream) { $stream.Dispose() }
    }
}

function Files-Match([string]$left, [string]$right) {
    foreach ($rel in $required) {
        $a = Join-Path $left $rel
        $b = Join-Path $right $rel
        if (!(Test-Path -LiteralPath $a -PathType Leaf) -or !(Test-Path -LiteralPath $b -PathType Leaf)) { return $false }
        $shaA = Get-FileSha256 $a
        $shaB = Get-FileSha256 $b
        if ($shaA -ne $shaB) { return $false }
    }
    return $true
}

# Existing v2/v3 files are recognized only by their audited checksums.
# A different or locally modified plugin is NOT overwritten automatically.
$v2Hashes = @{
    '__init__.py' = '05E430377C0EC180BF8F9E2890D6798E747C767AF3D274F3EEE8655C24461241'
    'MANIFEST.toml' = '5B4F668DA6D9F533D81312CB3FB1AC2536F83D24BC941DBD3972A010810F60C6'
    'repair_logic.py' = 'F8AFA38CA6A176166FAEFBE73808934B406BCC89D66C0DB16839E2CF1DD6EAB5'
}
# Match the exact release-v3 plugin source. Never silently overwrite locally edited files.
$v3Hashes = @{
    'MANIFEST.toml' = 'F8D07D9B30E1F4415D61717B25051DFDDDD526C35C42E9E131A13108193EE6C1'
    '__init__.py' = 'B47957AD9758836CD387D3B9FA86FCA4984A9D01E1FD9ECDC249528D0AF09F1E'
    'credentials.py' = '468B018E4EFFE743F11F89EA45A98F3E12F6D231E91EBE4E4175B16D7C849301'
    'repair_logic.py' = 'F8AFA38CA6A176166FAEFBE73808934B406BCC89D66C0DB16839E2CF1DD6EAB5'
    'universal_adapters.py' = '0BD4C0FA9161A1F2F2EB37243BA6818A239567674206A06FEACA5984553784A9'
    'universal_engine.py' = 'C745F7A666485187F09D36B55F13F6570141DBFB42DEBBBB2B0447E9EF45374B'
}
$v1Hashes = @{
    '__init__.py' = 'AD3C735098D781C1F1ECD7FC76FFBEC38390F89CEFF34E8AD7034E36A138B62A'
    'MANIFEST.toml' = 'B490B676327911A4F9E0D7673DB75E10DAA5400CB1971CBEC84055FDD9C2BE04'
    'repair_logic.py' = 'F8AFA38CA6A176166FAEFBE73808934B406BCC89D66C0DB16839E2CF1DD6EAB5'
    'universal_engine.py' = '028825F876266ED30818CF9D843FCB89C79898BFFF41A299952E5BEB9DCA03FF'
    'universal_adapters.py' = 'C723D2A7359F38BCCBF7D9E8005DAB4ED02D16CA699E21FF9D92007EC10FD1D0'
    'credentials.py' = '468B018E4EFFE743F11F89EA45A98F3E12F6D231E91EBE4E4175B16D7C849301'
    'native_workflow.py' = 'E7B917AB5CA898965626B3C282803AACF2C5B55EEF73567238B90B3796C6628'
    'native_ui.py' = '33F6E1E64E530EEBD4A9A920111189A9B4C6B3948FDF5DBBBF0238F6BB14FA02'
}
function Matches-Pinned-Source([string]$path, [hashtable]$pinned) {
    foreach ($rel in $pinned.Keys) {
        $file = Join-Path $path $rel
        if (!(Test-Path -LiteralPath $file -PathType Leaf)) { return $false }
        if ((Get-FileSha256 $file) -ne $pinned[$rel]) { return $false }
    }
    # Do not silently discard unrecognized user-maintained source files.
    $sourceNames = @(Get-ChildItem -LiteralPath $path -File | ForEach-Object { $_.Name })
    foreach ($name in $sourceNames) {
        if (-not $pinned.ContainsKey($name)) { return $false }
    }
    return $true
}
function Matches-Known-V3([string]$path) {
    return Matches-Pinned-Source $path $v3Hashes
}
function Matches-Known-V2([string]$path) {
    return Matches-Pinned-Source $path $v2Hashes
}
function Matches-Known-V1([string]$path) {
    return Matches-Pinned-Source $path $v1Hashes
}

$mode = 'install'
if (Test-Path -LiteralPath $target) {
    if (!(Test-Path -LiteralPath $target -PathType Container)) {
        Stop-Install "Ziel belegt, aber kein Pluginordner: $target"
    }
    if (Files-Match $source $target) { $mode = 'already_current' }
    elseif (Matches-Known-V3 $target) { $mode = 'upgrade_v3' }
    elseif (Matches-Known-V1 $target) { $mode = 'upgrade_v1' }
    elseif (Matches-Known-V2 $target) { $mode = 'upgrade_v2' }
    elseif ($AllowUnrecognizedExisting) {
        # Unknown local revisions are never discarded. Only explicitly
        # approved copies of THIS plugin UUID may be upgraded, with a full
        # retained rollback directory and independent confirmation.
        $installedManifest = Join-Path $target 'MANIFEST.toml'
        if (!(Test-Path -LiteralPath $installedManifest -PathType Leaf)) {
            Stop-Install "Unbekannte Installation ohne Pluginidentitaet: $target"
        }
        $installedText = Get-Content -LiteralPath $installedManifest -Raw -Encoding UTF8
        if ($installedText -notmatch 'uuid\s*=\s*"cf3c909b-eccb-4b89-90e3-55eb68e0176c"') {
            Stop-Install "Unbekannte Pluginidentitaet. Keine Aenderung: $target"
        }
        $targetItem = Get-Item -LiteralPath $target -ErrorAction Stop
        if (($targetItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            Stop-Install "Pluginordner ist eine Verknuepfung/Junction. Keine Aenderung: $target"
        }
        Write-Host 'UNBEKANNTE LOKALE VERSION: Der gesamte bisherige Pluginordner wird vor dem Upgrade als Rollback bewahrt.' -ForegroundColor Yellow
        Write-Host 'Lokale Python-Aenderungen werden NICHT in die neue Version uebernommen; das unveraenderte Backup bleibt erhalten.' -ForegroundColor Yellow
        $approval = Read-Host 'Nur wenn PicardWulf DEAKTIVIERT ist: JA-PLUGIN-SICHERN-UND-ERSETZEN'
        if ($approval -cne 'JA-PLUGIN-SICHERN-UND-ERSETZEN') {
            Stop-Install 'Unbekannte Pluginversion nicht zum gesicherten Upgrade freigegeben.'
        }
        $mode = 'upgrade_unrecognized'
    }
    else { Stop-Install "Pluginordner hat unbekannte lokale Aenderungen; sicherheitshalber NICHT ueberschrieben: $target. Fuer ein GESICHERTES Upgrade explizit -AllowUnrecognizedExisting benutzen." }
}
if ($mode -eq 'already_current') {
    Write-Host "PicardWulf v1.0 bereits vorhanden: $target" -ForegroundColor Green
} else {
    New-Item -ItemType Directory -Path $pluginRoot -Force -ErrorAction Stop | Out-Null
    $backup = $null
    $oldBackedUp = $false
    $newInstalled = $false
    try {
        Copy-Item -LiteralPath $source -Destination $stage -Recurse -ErrorAction Stop
        if (!(Files-Match $source $stage)) { throw 'Integritaetspruefung fehlgeschlagen.' }
        if ($mode -in @('upgrade_v2', 'upgrade_v3', 'upgrade_v1', 'upgrade_unrecognized')) {
            # Picard ignores dot-prefixed directories; leave the full previous
            # release as a retained rollback point, never delete it.
            $backup = Join-Path $pluginRoot ('.picardwulf-backup-' + $mode + '-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N'))
            Move-Item -LiteralPath $target -Destination $backup -ErrorAction Stop
            $oldBackedUp = $true
        }
        Move-Item -LiteralPath $stage -Destination $target -ErrorAction Stop
        $newInstalled = $true
        if (!(Files-Match $source $target)) { throw 'Zielintegritaet nach Upgrade falsch.' }
    } catch {
        $detail = $_.Exception.Message
        # Never delete the old plugin if moving it to backup failed.
        # Only a newly placed target from THIS run may be removed.
        if ($newInstalled -and (Test-Path -LiteralPath $target)) {
            Remove-Item -LiteralPath $target -Recurse -Force -ErrorAction SilentlyContinue
        }
        if ($oldBackedUp -and $backup -and (Test-Path -LiteralPath $backup)) {
            if (!(Test-Path -LiteralPath $target)) {
                Move-Item -LiteralPath $backup -Destination $target -ErrorAction SilentlyContinue
            }
        }
        if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue }
        Stop-Install "Pluginupgrade fehlgeschlagen; Rollback versucht: $detail"
    }
    if ($backup) {
        Write-Host "Bisheriges Plugin unveraendert gesichert: $backup" -ForegroundColor Green
    }
    Write-Host "PicardWulf v1.0 bereitgestellt: $target" -ForegroundColor Green
}
Write-Host ''
Write-Host 'Picard-CLI-Abhaengigkeit entfernt; keine Verwendung von picard-cli.exe.' -ForegroundColor Green
Write-Host 'Kein Eingriff in Picard.ini und keine Veraenderung von Musikdateien.'
Write-Host 'Picard 3 entdeckt das Plugin beim Start automatisch.'
Write-Host 'Nach dem Start: Optionen > Plugins > PicardWulf v1.0 > Aktivieren (falls noch nicht aktiv).'  -ForegroundColor Yellow
Write-Host 'Ordner hinzufuegen: bestes Release aus ALLEN Quellen wird bei sicherem Treffer automatisch in Picard angezeigt.' -ForegroundColor Yellow
Write-Host 'Automatisches Schreiben von Audiodateien ist standardmaessig AUS; separat mit Backup aktivierbar.' -ForegroundColor Yellow
Write-Host 'Native Release-Zuordnung/Tags: Werkzeuge > PicardWulf.' -ForegroundColor Yellow
Write-Host 'VA-Reparatur bleibt separat: Werkzeuge > NEOWULF > VA-Sortierung reparieren.' -ForegroundColor Yellow
Write-Host ''
if (!$picardRunning) {
    try {
        Start-Process -FilePath $picard -WorkingDirectory (Split-Path $picard -Parent) -ErrorAction Stop
        Write-Host 'Picard gestartet.' -ForegroundColor Cyan
    } catch {
        Write-Host 'Plugin abgelegt, aber Picard konnte nicht gestartet werden.' -ForegroundColor Yellow
        Write-Host "Details: $($_.Exception.Message)" -ForegroundColor Yellow
        Write-Host 'Picard manuell starten und in Optionen > Plugins aktivieren.'
    }
} else {
    Write-Host 'LIVE-UPDATE abgeschlossen. Picard wurde NICHT beendet oder neu gestartet.' -ForegroundColor Green
    Write-Host 'Jetzt in Picard Optionen > Plugins > PicardWulf wieder AKTIVIEREN.' -ForegroundColor Yellow
}
Write-Host 'ERGEBNIS: Plugin-Dateien bereit; Picard-GUI muss Erkennung und Aktivierungsstatus noch bestaetigen.' -ForegroundColor Green
