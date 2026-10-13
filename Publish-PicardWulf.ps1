# Optional operator-driven GitHub release path. No stored credentials or force pushes.
# Target is fixed; never falls back to unrelated repositories.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$repo = 'n-e-o-w-u-l-f/PicardWulf'
function Fail([string]$message) { Write-Host "NICHT VEROEFFENTLICHT: $message" -ForegroundColor Red; exit 1 }
foreach ($tool in @('git','gh')) {
    if (!(Get-Command $tool -ErrorAction SilentlyContinue)) {
        Fail "Erforderliches kostenloses Werkzeug '$tool' fehlt. Keine Anmeldung oder Veroeffentlichung versucht."
    }
}
$authorized = $false
try {
    & gh auth status 2>$null | Out-Null
    $authorized = ($LASTEXITCODE -eq 0)
} catch { $authorized = $false }
if (-not $authorized) {
    Write-Host 'GitHub-CLI ist noch nicht angemeldet. Die regulaere Browser-Anmeldung wird geoeffnet.'
    & gh auth login --hostname github.com --web
    if ($LASTEXITCODE -ne 0) { Fail 'GitHub-Anmeldung abgebrochen oder fehlgeschlagen.' }
}
$found = $false
try {
    & gh repo view $repo --json name --jq '.name' 2>$null | Out-Null
    $found = ($LASTEXITCODE -eq 0)
} catch { $found = $false }
if (-not $found) {
    Write-Host "Repository $repo ist nicht erreichbar oder existiert noch nicht."
    $choice = Read-Host 'Ein neues PRIVATES Repository mit genau diesem Namen erstellen? (ja/nein)'
    if ($choice -notin @('ja','j','yes','y')) { Fail 'Kein zugreifbares Repository; nichts erstellt.' }
    & gh repo create $repo --private --description 'PicardWulf v1.0: Picard 3 universal metadata and native matching'
    if ($LASTEXITCODE -ne 0) { Fail 'Repository-Erstellung fehlgeschlagen (evtl. existiert ein nicht freigegebenes Repository).' }
}
$stage = Join-Path ([System.IO.Path]::GetTempPath()) ('picardwulf-git-' + [guid]::NewGuid().ToString('N'))
Write-Host "Hole ausschliesslich $repo ..."
& gh repo clone $repo $stage
if ($LASTEXITCODE -ne 0) { Fail 'Das Zielrepository kann nicht geklont werden.' }
$root = $PSScriptRoot
$srcFiles = @('README.md','CHANGELOG.md','LICENSE','.gitignore',
    'Install-NEOWULF.cmd','Install-NEOWULF.ps1',
    'Publish-PicardWulf.cmd','Publish-PicardWulf.ps1')
$plugin = Join-Path $root 'neowulf_picard_repair'
$tests = Join-Path $root 'tests'
if (!(Test-Path $plugin -PathType Container) -or !(Test-Path $tests -PathType Container)) {
    Fail 'Quelle unvollstaendig; weder Commit noch Push.'
}
foreach ($file in $srcFiles) {
    $src=Join-Path $root $file
    if (!(Test-Path -LiteralPath $src -PathType Leaf)) { Fail "Quelle unvollstaendig: $file" }
    Copy-Item -LiteralPath $src -Destination (Join-Path $stage $file) -Force -ErrorAction Stop
}
foreach ($subdir in @('neowulf_picard_repair','tests')) {
    $from = Join-Path $root $subdir
    $into = Join-Path $stage $subdir
    New-Item -ItemType Directory -Path $into -Force | Out-Null
    $allowed = @(Get-ChildItem -LiteralPath $from -File | Where-Object { $_.Name -eq 'MANIFEST.toml' -or $_.Extension -eq '.py' })
    foreach ($src in $allowed) {
        Copy-Item -LiteralPath $src.FullName -Destination (Join-Path $into $src.Name) -Force -ErrorAction Stop
    }
}
$paths = @($srcFiles) + @('neowulf_picard_repair','tests')
& git -C $stage add -- $paths
if ($LASTEXITCODE -ne 0) { Fail 'git add fehlgeschlagen.' }
& git -C $stage diff --cached --quiet
if ($LASTEXITCODE -eq 0) {
    Write-Host 'GitHub-Repository ist bereits auf demselben Stand; kein neuer Commit erforderlich.' -ForegroundColor Green
    exit 0
}
& git -C $stage -c user.name=PicardWulf-Release -c user.email=picardwulf@users.noreply.github.com commit -m 'release: PicardWulf v1.0 source, native album matching and backed-up tag writes'
if ($LASTEXITCODE -ne 0) { Fail 'Commit fehlgeschlagen. Staging bleibt erhalten.' }
& git -C $stage push origin HEAD
if ($LASTEXITCODE -ne 0) { Fail 'Push fehlgeschlagen; kein force-push. Lokaler Commit bleibt im Staging.' }
$commit = (& git -C $stage rev-parse HEAD).Trim()
& gh api "repos/$repo/commits/$commit" --jq '.sha'
if ($LASTEXITCODE -ne 0) { Fail 'Push moeglicherweise erfolgt, aber GitHub-Readback fehlgeschlagen.' }
Write-Host "GITHUB VEROEFFENTLICHUNG BESTAETIGT: https://github.com/$repo/commit/$commit" -ForegroundColor Green
