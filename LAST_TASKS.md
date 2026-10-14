# LAST_TASKS — PicardWulf

Updated: 2026-10-14 · Project: `n-e-o-w-u-l-f/PicardWulf`

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
