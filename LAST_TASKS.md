# LAST_TASKS — PicardWulf

Updated: 2026-10-17 · Project: `n-e-o-w-u-l-f/PicardWulf`

## 2026-10-17 · Native Save Guard und echter FLAC-Rollback

- Nach fehlgeschlagener Post-Commit-SHA-256- oder Decoderprüfung wird die vorherige FLAC jetzt **tatsächlich** aus dem separaten Backup wiederhergestellt; fehlerhafte Wiederherstellung bleibt explizit UNVERIFIED.
- PicardWulf-eigene Auto-/manuelle `File.save()` erfordern `rename_files=False` und `move_files=False`; Toggle verweigert risikoreiche Aktivierung ohne Änderung an Picard.ini/Preset 3.
- **333 Tests PASS**, Legion-HEAD `877c6887e25b794ee82c9570e634568dd3a83faa`; SHA-gebundene Vorschau. Picard **3.0.2** weiterhin ohne Save-Veto; **BMAX und Ctrl+S OPEN**. PR #1 DRAFT.

## 2026-10-17 · Picard-Dateiaktion und BMAX-Audit

- **PLUGIN-REGISTERED / LEGION-TESTED**: `SafeStagedFlacImport` im Picard-Dateimenü, aktives Preset-3-Ziel, zweistufige Nutzerbestätigung, FLAC-Größenregel, Backup; neue Serienordner mit Leerordner-Rollback. **318 Tests PASS**, Head `5a84068df0714ae9bebe351d0346e5fbd9d8a7e8`.
- **OPEN**: Normales `Strg+S` nicht abgefangen; BMAX-Peer/SSH-Port erreichbar, aber `megal`-Login nicht bestätigt (Legion sentinelx ohne SSH-Agent/Key; RDC 0%). Kein Live-Deploy. [Plan](docs/planning/PICARD3-SAVE-INTEGRATION-20261017.md).

## 2026-10-17 · Gold-CD-Skalierung und strenge Tagprüfung

- SOURCE-ONLY: Gold-Controller liest höchstens 100 Alben je Timer-Durchlauf, ohne sämtliche Alben zu kopieren; Änderungen an der Registry führen zum kontrollierten Iterator-Neustart.
- Picards eigene Option `remove_complete_albums_after_save` muss nachweislich **False** sein, sonst bleibt die PicardWulf-Goldentfernung gesperrt. Erneute Kontrolle vor Qt-Retirement; `Tag-Speicherstatus` zeigt GESPERRT/NICHT GESTARTET/AKTIV. Picards native frühere Entfernung ist damit nicht automatisch deaktiviert; BMAX-Einstellung und Laufzeit bleiben OPEN.
- Picard `Metadata.getall()` statt `get()` für alle Mehrfachwerte; zusätzliche Release-/Genre-/ISRC-Tags gegen Originalmetadaten und echte FLAC-Disk-Tags prüfen. Unterschiedlicher zweiter Tag-Wert oder entfernte Album-ID blockiert die UI-Entfernung.
- **304 Tests PASS** auf Legion, `compileall`/Git-Diff PASS, Code-HEAD `6c6c015d1d30097553bf6cbd7e86c2f5a9fd1c9b`. Kein Windows-Deployment, keine Originalmusik verändert. PR #1 DRAFT. [Evidence](docs/planning/PICARD3-RETENTION-GATES-2026-10-17.md).

## 2026-10-17 · Staged FLAC actual arbitration (without native Picard hook)

- **IMPLEMENTED SOURCE-ONLY** `neowulf_picard_repair/staged_flac_import.py`: offline `import_staged_flac` default `apply=False`, explicit `apply=True`; verified `WOULD_REPLACE/SKIP/CREATE` → `REPLACED/SKIPPED/CREATED`. Independent staging, library and recovery roots; full FLAC decoder; source retained; SHA-256 verified backup of replaced target; atomic replace/exclusive new target; fail-closed locks, invalid identity and symlink/inode conflicts. No MP3 or staging-source deletion.
- Retention identity tightened for opposing `musicbrainz_albumid`, `musicbrainz_recordingid`, ISRC, barcode, date, albumartist and release status (including one-sided evidence); unequal editions now abstain from collision replacement and MP3 cleanup.
- **TESTED:** 294 local Python regressions, `compileall`, `git diff --check` PASS on a fresh Legion source checkout `18387d6486730455db9d0af1b7588f7f903bc33b`. Includes disposable real FLAC stream generation and byte-comparison, plus stale lock and concurrent destination tests. Initial installer integrity test correctly caught missing new module and was repaired.
- **EXTERNAL BLOCKER:** a separate standalone CLI entrypoint write to `scripts/picardwulf_staged_flac.py` was denied by a generic OpenAI security check; independent readback returned 404 (not published). Do not retry an equivalent write by altered payload/transport. Source importer and tests remain published.
- **OPEN:** Native Picard save collision hook still cannot be vetoed using documented public API. The new importer is a separately callable source function, not registered for automatic use or BMAX deployed. Windows file locks/Hardlinks/Picard session and recovery have NOT been verified; installed Preset 3 and all original music remain untouched. PR #1 DRAFT. [Evidence and constraints](docs/planning/STAGED-FLAC-IMPORT-2026-10-17.md).

## 2026-10-17 · Picard 3 native filename-collision advisory

- REQUEST CONTINUATION: automatic overwrite of smaller verified FLAC, skip existing larger/equal FLAC, FLAC-only, UI-only gold retirement. This checkpoint advances the **native destination-path discovery**, not the fully automatic collision rewrite.
- Picard upstream `release-3.0.0rc4` verified: `File.save()` invokes a pre-save callback (no documented cancellation or destination redirect), then asynchronously saves tags and calls `_rename()` with `File.make_filename()`. When `move_overwrite_existing_files` is false, Picard uses an available new filename instead of replacing; when true, native overwrite bypasses PicardWulf's size rule. Therefore an unattended plugin monkey-patch or forged "done" claim is forbidden.
- New `collision_preview.py` provides an **action on selected files** `PicardWulf: Dateikollisionen / FLAC-Größenregel prüfen (nur lesen)`. Uses the real active Picard naming format/preset 3 to calculate destination on GUI, compares at most 20 FLAC candidates on worker for matching track identity/duration/size, and warns of global native overwrites, symlink risks and mismatches. Never moves/copies/unlinks or changes config.
- `__init__.py` registers the new read-only file action and cleans its Qt timer on plugin disable; Windows installer inventories the module. Added 18 isolation tests (including missing target directories); **276 Python tests PASS on Legion** at source HEAD `38eff80f78fd50dd2992a579c437cd4af019830d`, `compileall` and `git diff --check` PASS.
- **OPEN:** No supported native Picard save-veto plugin API; automatic skip/replace is NOT yet wired, BMAX live runtime/active preset still unverified, and real Qt/Windows collision tests not executed. User music and running Picard were untouched; PR #1 DRAFT. [Full scope](docs/planning/PICARD3-RETENTION-GATES-2026-10-17.md).

## 2026-10-17 · Picard 3 / retention policy source checkpoint

- USER GOAL: larger validated FLAC wins duplicate conflict; existing equal/larger wins otherwise; remove only verified redundant MP3; remove finished gold albums only from Picard UI.
- STATUS: **PARTIAL / SOURCE-ONLY**, on feature branch `feature/picard3-retention-policy-20261017`. No Picard runtime or actual music was modified.
- Added `retention_policy.py`, nine synthetic policy tests and one generated real-audio integration test. Scoped, SHA-256-backup-preserving duplicate-replacement primitive exists but **is not connected to Picard's actual destination collision path**.
- Added PicardWulf-specific post-save callback that runs only after verified tag readback; same-stem verified FLAC/MP3 comparison, full FLAC decoder requirement and independent MP3 backup precede potential unlink. Missing/invalid evidence aborts without deletion. On BMAX this is **not deployed** and `flac` binary availability is not known.
- Fixed discovered installer inventory regression; fresh Legion clone test suite **240 tests PASS**, including disposable real FLAC/MP3 encoded-stream acceptance, plus `compileall` PASS at `bc2e2d3c18f8cc39613703d7520aaa3caf9ab00f`. Following documentation commit has no code changes.
- Picard 3 native General setting `remove_complete_albums_after_save` is documented; **not yet enabled/tested on BMAX**, and its native complete/saved check is not independent PicardWulf zero-discrepancy verification.
- Acceptance gates and missing runtime evidence: [Picard 3 retention plan](docs/planning/PICARD3-RETENTION-GATES-2026-10-17.md). NEXT: implement collision interception + strict UI gold cleanup; then disposable real-file BMAX tests, review, merge and deployment. Target version remains **v1.0**.

## 2026-10-17 · Strict gold-CD UI retirement continuation

- STATUS: **SOURCE IMPLEMENTED / SYNTHETIC VERIFIED / BMAX NOT DEPLOYED**. Built on the existing retention draft PR #1; source code remains on `feature/picard3-retention-policy-20261017`. Main and the active Windows Picard/preset 3 are untouched.
- Picard 3.0.0rc4 native auto-remove happens in its post-save hook, potentially before PicardWulf's asynchronous independent readback. Strict mode therefore needs its own delayed Qt GUI retirement and requires the built-in auto-remove setting to be OFF during live acceptance; no silent Picard.ini change was made.
- New `gold_retirement.py`: checks every track mapped and saved, all actual files FLAC, no errors/review mismatches, on-disk FLAC tags independently verified on a worker. Qt queued completion rechecks album/SaveTracker state before **UI-only** `panel.remove([album])`. Bounded rotation across albums and 60-second retry; zero disk writes by this controller.
- `SaveTracker` now records bounded per-path `PENDING/VERIFIED/MISMATCH/UNKNOWN_TIMEOUT` and exposes in-flight state. Installer inventory includes new plugin module. Fake-Qt race tests, negative matching cases and generated real-FLAC tag checks added.
- **PASS:** independent fresh Legion checkout at `ce9e3f4721ca651b13e8460541198f461ab44558`; 258 Python tests, compileall and git diff --check; recovered test-harness `NameError` by fixing class-scope fixture, no app-code rollback needed. [Scope and evidence](docs/planning/PICARD3-RETENTION-GATES-2026-10-17.md).
- **OPEN:** native file destination collision interception (Picard's public pre-save plugin hook cannot safely cancel/redirect a native rename); actual BMAX interactive Picard 3 execution, Qt integration, native setting, Windows locks/FLAC decoder and disposable-media retention tests. MP3 cleanup remains limited to verified same-stem partners following PicardWulf save. Do not merge, tag, deploy or delete client media yet. Keep PR DRAFT.

## Fixed target version

- **TARGET_VERSION: v1.0** (no interim v1.0.1 / 1.0.0 version designation for source milestones).
- Changes for provider matching, scalability, installer recovery, documentation and BMAX runtime fixes all belong to the same PicardWulf v1.0 target.
- Do not announce a release as stable until end-to-end Windows runtime, native matching, provider permissions and safe tag persistence are verified. Commits are development milestones, not new versions.
- Acceptance must be verified on actual BMAX Picard 3 before a release tag is considered.

## Source of truth

- GitHub repository: https://github.com/n-e-o-w-u-l-f/PicardWulf
- Branch: `main`
- First complete source publication: `11277cb221affaaead8afc009f1bd5bab8c109f8`
- Verified canonical checkout on Legion: `/home/andreas/Projekte/n-e-o-w-u-l-f/PicardWulf`, owner `andreas`; isolated S1 worktree: `/home/andreas/Projekte/.worktrees/PicardWulf-S1-20261014`.
- Local GitHub auth path: existing authorized `andreas` GitHub CLI on Legion; no new paid CI or OAuth credentials created. Avoid unrelated repositories.

## Implemented source

- Picard 3.0 plugin API and user plugin directory, without the broken frozen `picard-cli.exe`.
- Multi-source adapters: MusicBrainz, Deezer, Apple/iTunes catalogue; optional authenticated Spotify, SoundCloud, Last.fm.
- Automatic file-load and metadata-update background search, SQLite persistent queue/cache, per-source quota, and source-neutral release ranking.
- Automatic Picard in-memory metadata takeover for a uniquely highest-scoring release from **any** configured provider (not a MusicBrainz priority); configurable via PicardWulf Tools.
- Automatic audio-file saving is OFF by default and requires an explicit user opt-in, full-media backup and asynchronous save readback.
- Release-specific provider album IDs, edition ambiguity guard, file-original metadata baseline, native MusicBrainz race handling, and provider attribution as private Picard metadata.
- 11 translated README pages with 121 mutually linked header entries.
- Picard native release/recording association only for authentic MusicBrainz IDs.
- Consent-gated tag changes with diff preview and hash-checked full audio backup.
- NEOWULF script repair; distinguish compilations from Various Artists; Eminem *Curtain Call 2* must remain Eminem.
- Install/upgrade v2/v3 with rollback safeguards and documented profile compatibility assumptions.

## Validation

- **PASS**: 120 Python unit/contract tests on Legion using self-contained packaged sources (`python3 -m unittest discover -s tests -q`), 2026-10-14.
- **PASS**: `git diff --check` before push; GitHub code, README and file tree read back; fast-forward push succeeded.
- **PENDING**: actual installer/plugin activation on Windows BMAX-B6 as `megal`; the release is a candidate, not a production-verified binary.
- **PENDING**: live credentials/API responses, rate limits and terms for individual providers.
- **PENDING**: interactive Picard 3 native release selection, asynchronous tag saving, file moves/renames, recovery from backup on actual media.
- **IMPLEMENTED (source)**: automatic best-source candidate ranking and Picard-file metadata takeover; no counterfeit external release in native MusicBrainz album pane.
- **PENDING**: BMAX runtime confirmation that Picard's automatic MusicBrainz lookup does not replace source-selected metadata after background completion; ensure no stale-MBID regressions.
- **PENDING**: direct external catalogue album representation in native Picard release pane would require additional compatibility work or a Picard core feature; currently visible in PicardWulf review only.

## Incident: suspected Picard UI stall with 29k known + 10k new files

- **FAILURE_FINGERPRINT:** PicardWulf v1.0 load hook / BMAX-B6 / ~10,000 additions on a ~29,000-file Picard session / synchronous SQLite queue access once or more per file, repeated GUI result reads / acceptance: retain loaded files, background search pause/recovery without terminating Picard, no lost persisted jobs.
- **ROOT CAUSE (confirmed in code, not process):** file-load processor called `schedule()`, which performed `get_result()`, `enqueue()` and `_pump()` synchronously in Picard's GUI thread. Result timer also opened SQLite per watched file and could starve later files. Six-provider queries with rate limits can take hours at this scale.
- **GOVERNANCE:** `GUARD_OR_CHECKER_DEFECTIVE` (previous release lacked 10k UI-latency load test), plus `GOVERNANCE_GAP` for process-preserving pause and live upgrade. No confirmed BMAX process hang until runtime telemetry is available.
- **DO_NOT_REPEAT:** no mass `RefreshAction.schedule()` writes on Qt thread, no DB deletion, no forced Picard termination, no bulk unbacked audio writes, no claiming a patched GitHub checkout repaired the already-running Windows Python process.
- **FIX IMPLEMENTED:** `schedule_async` with memory staging and 256-row SQLite batches, fair/one-query GUI timer, pause/resume UI, auto-pause huge existing backlog on startup, opt-in live plugin swap with Picard still running.
- **VALIDATION:** 119 local tests, including 10k-job durable ingest and paused-backlog recovery. **PENDING:** BMAX actual process health; plugin disable → live update → enable; queue counts and responsiveness; provider calls/limits while resumed.

## Research checkpoint — PicardWulf v1.0 stability (2026-10-14)

- **TARGET_VERSION = v1.0**, source development milestones are not new versions.
- Primary source-backed research: [Architecture and API evidence](docs/research/PICARDWULF-V1.0-DEEP-RESEARCH-2026-10-14.md).
- Next authorized development plan: [S0–S5 with gates](docs/planning/V1.0-NEXT-EXECUTION.md); next code phase S1 must follow S0 observations where runtime access is available, otherwise proceed with isolated local simulation.
- **CRITICAL remaining**: unbounded volatile staging before SQLite durability; SQLite reads on GUI QTimer; synchronous full-media backup/hashing in GUI. These are code findings, **not proof** Picard is currently hung for a particular reason.
- **HIGH remaining**: 429/503 partial results prematurely finalized, edition-level matching not calibrated, 2026 Spotify/SoundCloud restrictions and OAuth token management, post-save success receipt missing.
- 119 existing tests and target-version regression are baseline; **BMAX 29k+10k runtime acceptance still OPEN**.
- Research made no BMAX process changes, no media modifications, no paid API purchases, no user-secret uploads.

## Full metadata & provider registration checkpoint — 2026-10-14

- Target stays v1.0. Read-only Legion public probes: MusicBrainz, Deezer, Apple all AVAILABLE. A real matched Deezer track+album showed all available core fields; API responses and account rights from BMAX remain unverified.
- Full official-detail Deezer enrichment now shares Deezer rate/quota bucket; complete candidate fields map to Picard in-memory tags, with MBID, albumartist, release and manual-edit protection. 158 local mocks/regressions passed (before final documentation validation).
- Previous unrequested >2,000-backlog pause is now a warning only; persisted explicit pause is still honored. New cache keys prevent replay of old incomplete candidate data.
- BMAX reached by Tailscale but SSH key login to the tested local accounts was denied. No Picard termination, no BMAX data changes.
- New SoundCloud client credentials currently require Artist Pro; Spotify Development requires Premium. Last.fm requires personal app registration. No extra cost authorized, no keys invented. All account-dependent runtime gates OPEN.
- Registration instructions, source-backed eligibility and operational acceptance: [provider guide](docs/planning/V1.0-PROVIDER-ACCESS.md).
- NEXT: verified BMAX user-session plugin activation, provider status and legitimate credentials; no stable release label before actual save/restore and 29k+10k UI tests.

## v1.0 provider completeness repair — 2026-10-14

- Reproduced RED: strong sibling album-pool match could return LOCAL_CACHE with zero provider calls because an empty checkpoint list passed the completed check. Separate early-exit skipped Last.fm after a good prior source.
- Fixed: all eligible provider lookups occur, or exact-query provider cache/checkpoint is reused; quotas and persisted retries are maintained. Source-neutral ranking, edition guards and private metadata remain intact.
- Four synthetic regressions, 180 local tests PASS. See [provider completeness](docs/planning/V1.0-PROVIDER-COMPLETENESS-2026-10-14.md).
- No BMAX changes; authentic SoundCloud/Spotify/Last.fm developer credentials and S4/S5 Windows runtime acceptance remain OPEN. Target is v1.0 only.

## S5 publication and BMAX remote-access check — 2026-10-14

- Windows S4 installer manifest omitted save_tracking.py. RED/ GREEN regression verifies all Python modules in required installer files; 198 local Python tests PASS.
- Commit 34cf49c8851cf66ae5f672f56aec8aefc538d955 pushed to GitHub main and remote HEAD verified; Git/Bash from authorized Legion account works. A previous execution policy rejection was not evidence of a Git executable malfunction.
- SentinelX has only Legion connected (free one-host slot). Remote Desktop Commander connection quota is 0 percent. BMAX is reachable over Tailnet but its normal SSH public-key user authentication was previously denied.
- Tailscale SSH wrapper cannot serve Windows destinations: official Tailscale SSH server supports Linux and selected macOS daemon devices only (https://tailscale.com/docs/features/tailscale-ssh). Hostname DNS maps to the already pinned endpoint, and the observed ED25519 key matched the existing IP pin; the alias was added without disabling StrictHostKeyChecking. A retry still failed Tailscale SSH coordination-host-key verification, as expected on Windows. DO_NOT_REPEAT the Tailscale SSH wrapper for Windows.
- Next authorized operation: establish ordinary Windows OpenSSH user authorization from the BMAX desktop, or an existing eligible remote-management connection; only then run live installer with plugin disabled and Picard still open. No password guessing, host-verification bypass, process termination, original-music edits or installed-plugin change.
- S5 deployment and BMAX post-save/restore verification remain BLOCKED by absent authenticated remote execution, not by repository publication. Target is v1.0 only.

## Installer portability: missing Get-FileHash on BMAX-B6 — 2026-10-14

- User-reported runtime failure in the downloaded Windows Live installer at Install-NEOWULF.ps1:67: PowerShell did not recognize the Get-FileHash cmdlet. This proves the installer failed before file hash comparison completed; no conclusion about plugin activation.
- FAILURE_FINGERPRINT: BMAX-B6 / megal / PowerShell LiveUpdate / Files-Match hashing / missing command Get-FileHash. ROOT CAUSE: installer depends on an optional PowerShell cmdlet unavailable in the target session. Classification: GOVERNANCE_GAP (installer portability preflight missing).
- Corrected all three sites: content comparison and historical pinned hashes now call Get-FileSha256, a streaming .NET SHA256 function using File.OpenRead and finally-disposed stream/hash object. Exact hex digests remain uppercase and are compared unchanged; missing files and unidentified plugin source are still rejected.
- RED/GREEN regression checks absence of any Get-FileHash dependency, .NET hashing and all call sites. Updated old installer test that required the deprecated dependency. 199 local Python tests passed; no Windows PowerShell runtime test yet.
- Existing downloaded archive on BMAX contains the old script and must be refreshed from the new verified GitHub commit. No process restart, provider key change or music-file modification.
- Next: authenticated actual BMAX installer rerun with only PicardWulf disabled, Picard open, consent; validate installed plugin and API provider statuses before stable v1.0 release.

## PicardWulf v1.0 multi-source album context search and guarded local upgrade — 2026-10-14

- Requested behavior: right-click an album group on left OR a matched album on right, run **PicardWulf: Ähnliche Alben aus ALLEN Quellen (ab 75 %)**; all enabled and authorized sources compete, not just MusicBrainz. This is a separate official Picard 3 plugin action rather than an unsupported override of Picard's built-in lookup.
- New source modules: cluster_matching.py (source-neutral release-level matches with >=75% confidence AND >=75% track coverage, one hit per original track, edition and provider release-ID isolation) and cluster_ui.py (asynchronous SQLite result delivery and bounded 200-track GUI dialog). Selected hit can be inspected without automatic writing.
- Official API: register_cluster_action() and register_album_action() per https://github.com/metabrainz/picard/blob/master/docs/PLUGINSV3/API.md.
- New installer failure fingerprint: BMAX-B6 as megal, Picard running, previously installed neowulf_picard_repair directory unknown hash/source files. Existing strict allowlist correctly halted; do NOT silently overwrite. A gated -AllowUnrecognizedExisting path now demands valid MANIFEST UUID and non-reparse target, explicit second confirmation JA-PLUGIN-SICHERN-UND-ERSETZEN, and retains FULL original plugin directory in rollback folder. Existing live-plugin-disabled confirmation remains required.
- Verified: 212 local unit tests PASS and real Qt offscreen context dialog probe PASS (two release choices, Deezer first, both forced asynchronous queries). **Not yet verified on BMAX**: actual plugin loaded and current API provider auth. Tailscale BMAX port reachable but remote authenticated operation blocked by platform; RDC remaining quota 0; no audio originals changed.
- Installation requires an updated full archive (two new .py modules), not just the installer PS1. Version target remains v1.0; no stable tag before actual BMAX S5 acceptance.

## S4 pre-save identity source checkpoint — 2026-10-15

- Target is **v1.0**. Continued from clean HEAD 9d5bf679759c4a09343874dff88829ea3c3afcbe; earlier S1/S2/S3 and cross-source context-menu features were not reimplemented.
- Fixed the post-backup/original-mutation gap with off-GUI device/inode/size/mtime and SHA256 preflight, and a second queued Qt acknowledgement before automatic/manual Picard File.save().
- 223 standalone Python tests PASS on Legion. Real Qt probe updated but cannot execute with current system Python because PyQt6 is absent; the actual-Qt gate is OPEN, not passed. [S4 pre-save evidence](docs/planning/S4-PRESAVE-IDENTITY-2026-10-15.md).
- Residual asynchronous File.save() TOCTOU and BMAX runtime S0/S5 gates are OPEN; no process restart, original media writes, access bypass, paid CI or provider purchase.

## S5 album grouping/readback/performance repair — 2026-10-15

- Baseline GitHub/local HEAD fb9f08d (contains concurrently published S4 pre-save identity repair); clean before editing.
- RED→GREEN: same official provider album ID split by sparse optional release metadata (4-track group reduced to 3); now prefer actual provider release ID and abstain if present edition fields conflict. Distinct provider IDs still separate.
- RED→GREEN: 200-track group previously produced 20,100 edition-conflict comparisons on GUI timer. Accumulated per-release evidence bounded to linear comparisons (<650 in 200-track regression).
- Selected Deezer/MusicBrainz row is carried through to the per-track details dialog without writing audio; real offscreen PyQt6 probe verifies Deezer wins and the correct selected release goes into review.
- **228 local Python tests PASS**, real Qt source-selection probe PASS; latest BMAX v1.0 installed/runtime state still UNKNOWN without authorized remote Windows execution, no client music touched.
- [S5 release grouping evidence](docs/planning/V1.0-S5-CLUSTER-CORRECTIONS-2026-10-15.md). Target v1.0; Windows rollout and actual provider credentials remain OPEN.

## Next safe actions

### S1 source checkpoint — 2026-10-14

- Verified starting GitHub/local HEAD `a952afa84df199f5296497da1a98bf32bff12183` and clean source worktree before implementation. **TARGET_VERSION remains v1.0**; no release/tag/deployment.
- Implemented 2,048-envelope admission bound including in-flight batches, weak GUI identity retries/backpressure, one SQLite owner, queued Qt result/backup signals, cached status, transactional schema v2 migration/SQLite backup, provider checkpoints, revision cancellation, new/backlog fairness and asynchronous stop-flush acknowledgement. Database and full-media I/O are off the GUI thread.
- **PASS:** 129 unit/contract tests on Legion; actual SQLite BUSY/FULL regressions, migration/corrupt/future schema protection, and abrupt synthetic helper termination preserve all 29,000 historical + 10,000 newly committed jobs.
- **PASS:** independent review fixes with regression evidence, real Qt 39k identity load and six asynchronous backup/identity cases, forced-result generation fencing, and manual forced refresh under backpressure/selection change. Aggregate measurements and commands: [S1 execution evidence](docs/planning/S1-EXECUTION-2026-10-14.md).
- **S0 / BMAX S1 runtime: OPEN (EXTERNAL_BOUNDARY).** Desktop Commander monthly limit/offline device; direct SSH and jumps through Legion/Spinnennet cannot resolve documented `andreas-BMAX`. The actual `BMAX-B6` hostname as `megal` fails host-key verification directly and through both jump hosts; trust settings were not bypassed or changed. No Picard PID/heartbeat/live DB backup was observed; no Picard stop/restart, deployment, original audio change, API call against personal music or paid service.
- Next: read back GitHub commit/tree and compare remote/main with clean Legion HEAD. Obtain authorized BMAX runtime observations before claiming its responsiveness/deployment; then continue S2→S3→S4→S5 in plan order. Do not restart Deep Research.

The earlier validation/incident sections above are historical checkpoints; this S1 evidence supersedes the old unbounded-ingest and GUI SQLite/media-I/O findings only at source level.

### S2 provider-policy source checkpoint — 2026-10-14

- Starting HEAD `c492fa8a7b6efb24f76b51e5f5dcb83a8dbb317a` verified clean on GitHub/local Legion; target remains **v1.0**, no deployment/release/tag. Existing Deep Research reused.
- Implemented schema v3 with persisted provider budgets, cooldown/circuit and retry cursors; capability/consent/budget UI; incomplete-result auto-apply guard; safe complete album-pool reuse; source-neutral competing queries; selective enrichment and MBID/ISRC lookup; optional existing Spotify access confirmation; quota-reserved encrypted SoundCloud rotation and asynchronous credential updates.
- **PASS:** 145 unit/contract tests; real Qt 39k load (staging ≤2,048, zero GUI SQLite calls), backup/identity/refresh regressions and operator/credential acknowledgement. Three independently reviewed P1 defects reproduced and fixed. [S2 evidence](docs/planning/S2-EXECUTION-2026-10-14.md).
- **OBSERVED LIVE:** anonymous fixed public Bach/Air query returns valid data from MusicBrainz, Deezer and iTunes. No personal music/API secrets submitted; no artwork cached. Spotify/SoundCloud/Last.fm remain **UNAVAILABLE_FOR_THIS_VALIDATION**, not claimed healthy.
- **OPEN:** BMAX access/runtime, actual encrypted-vault/token lifecycle there, and credentialed provider entitlement/quota. Existing Picard/music untouched; no new paid services and no host-trust bypass. S3 is the next source phase; S4/S5 and full v1.0 acceptance remain separate.
- Final publication requires commit/push plus GitHub HEAD/LAST_TASKS/evidence readback and clean Legion checkout confirmation.

### S3 release-ranking source checkpoint — 2026-10-14

- Starting clean HEAD `562618ba12625ffefd525837e63955b40d79a4a9` verified against GitHub. Target remains **v1.0**; no release, deployment, Picard restart, original audio change or paid service.
- Implemented production edition snapshots, recording/release identifier separation, release-v2 context cache, matching-point weight/contribution reports, full alternatives, missing-evidence abstention, verified sibling-recording consensus and fixed-preview conflict review.
- **PASS:** curated synthetic 41-case corpus: 10 correct proposals, 31 abstentions, zero wrong automatic assignments or provider-artist corruption. Independent review's Critical snapshot and Important conflict/consensus issues fixed with RED→GREEN regressions. [S3 evidence and review ledger](docs/planning/S3-EXECUTION-2026-10-14.md).
- Combined Legion suite: 176 tests PASS; Windows: 176 run, 175 PASS, 1 platform skip. Publication readback recorded with S3 completion. Concurrent main `cb01721` fully preserved. Real Qt 39k load: bound 2,048, p95 5.81 ms / p99 19.09 ms, zero GUI SQLite/media operations; backup/refresh/operator probes PASS. These are synthetic Legion measurements, not BMAX evidence.
- **OPEN:** BMAX runtime/S0, S4 media-write/recovery and S5 release gate. Unverified cross-script aliases and missing full tracklists abstain; native matching-window percentage wording is a deferred minor. Existing source and original music were preserved; Deep Research was not repeated.
- Next safe work: finish remaining S3 evidence limitations where legitimate catalogue data is available, then S4→S5 in order. Never interpret these source results as stable v1.0 acceptance.

### Historical later-phase follow-ups (S4/S5, not current deployment)

1. Run fresh `git pull --ff-only` before editing, inspect `README.md`, `CHANGELOG.md` and failing runtime gates. Preserve unrelated changes.
2. On BMAX-B6 under interactive `megal`, install and enable via `Install-NEOWULF.cmd` (not the unsigned PS1 directly); verify actual plugin log. Do not treat file copy as activation.
3. Use a disposable copy of a small audio sample before tag write. Confirm source backup SHA-256 and resulting tags after asynchronous Picard save; verify naming profile overrides.
4. Validate allowed provider endpoints with legitimate API credentials; do not use scraping bypasses or paid services.
5. Track discovered defects with reproducible failure fingerprints, minimal fixes, tests, and Git commits. Avoid provider-denied remote credential approaches.

DoD: all requested providers demonstrably functional where legitimate access is available, cross-source matching accurate, files associated to the correct native Picard releases, tags safely persisted/rollback tested, and BMAX runtime acceptance evidenced.
