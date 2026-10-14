# LAST_TASKS — PicardWulf

Updated: 2026-10-14 · Project: `n-e-o-w-u-l-f/PicardWulf`

## Source of truth

- GitHub repository: https://github.com/n-e-o-w-u-l-f/PicardWulf
- Branch: `main`
- First complete source publication: `11277cb221affaaead8afc009f1bd5bab8c109f8`
- Persistent local checkout on Legion: `/home/andreas/projects/PicardWulf`, owner `andreas`; the remote and local HEAD were equal after publication.
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

- **PASS**: 119 Python unit/contract tests on Legion using self-contained packaged sources (`python3 -m unittest discover -s tests -q`), 2026-10-14.
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

## Next safe actions

1. Run fresh `git pull --ff-only` before editing, inspect `README.md`, `CHANGELOG.md` and failing runtime gates. Preserve unrelated changes.
2. On BMAX-B6 under interactive `megal`, install and enable via `Install-NEOWULF.cmd` (not the unsigned PS1 directly); verify actual plugin log. Do not treat file copy as activation.
3. Use a disposable copy of a small audio sample before tag write. Confirm source backup SHA-256 and resulting tags after asynchronous Picard save; verify naming profile overrides.
4. Validate allowed provider endpoints with legitimate API credentials; do not use scraping bypasses or paid services.
5. Track discovered defects with reproducible failure fingerprints, minimal fixes, tests, and Git commits. Avoid provider-denied remote credential approaches.

DoD: all requested providers demonstrably functional where legitimate access is available, cross-source matching accurate, files associated to the correct native Picard releases, tags safely persisted/rollback tested, and BMAX runtime acceptance evidenced.
