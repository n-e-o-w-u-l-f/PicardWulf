# PicardWulf v1.0 — S1 implementation evidence

Date: 2026-10-14. Target remains **v1.0**; this is a source milestone, not a stable release.

## Verified starting point

- GitHub `main` and clean Legion source checkout both had HEAD `a952afa84df199f5296497da1a98bf32bff12183`. `LAST_TASKS.md` and `V1.0-NEXT-EXECUTION.md` were read before changes; fast-forward refresh found no newer source.
- Isolated implementation/test worktree: `/home/andreas/Projekte/.worktrees/PicardWulf-S1-20261014`. Existing canonical source: `/home/andreas/Projekte/n-e-o-w-u-l-f/PicardWulf`.
- Baseline: 120 unit/contract tests passed on Legion. Plugin manifest/version/UUID remain unchanged. Installer adds the new background I/O module; original script executable permissions are preserved.
- Desktop Commander reported a monthly usage limit and BMAX offline. Existing authorized SSH to Legion worked. Direct `andreas-BMAX` resolution failed, as did SSH through Legion and Spinnennet. The actual device hostname `BMAX-B6` was then tried as `megal`, directly and through both jump hosts: all three attempts failed host-key verification. No trust-policy bypass or host-key change was attempted. No retry of the quota-limited service, login bypass, Picard process action, live DB access or music-file change occurred.
- **S0: OPEN / BLOCKED_RUNTIME (EXTERNAL_BOUNDARY).** BMAX PID, heartbeat, live queue integrity/backup, hashes and actual counters are unobserved. No deployment or BMAX responsiveness claim follows from these source tests.

## S1 implementation contract

- GUI entry points stage detached JSON envelopes, read in-memory status and request asynchronous reads. One dedicated SQLite owner serializes all runtime database operations; two provider workers and a scheduler wait only off the GUI thread. Database startup, credential loading, migration and backup happen in the background.
- At most **2,048** uncommitted job envelopes, including an in-flight batch, may be admitted. Batches are configurable from 1 to 256 through the `sqlite_batch_size` plugin setting (default 256). Pacing adapts to measured transaction cost, bounded between 10 and 250 ms, without increasing concurrency. Returning false means backpressure/rejection, never persistence. The controller keeps weak, versioned references to loaded Picard identities and retries overflow in bounded timer slices. Manual forced refresh retains its request across backpressure and selection changes. Reload recovery enumerates original file snapshots incrementally, without forcing unchanged cached songs to rescan.
- `staging` is volatile. `committed` counts envelopes acknowledged after a successful transaction, including durable cache/dedupe decisions; `queued` counts newly inserted jobs in this session. Cached state counts distinguish queued/running/retry/failed jobs. Status includes capacity, backpressure, DB error, flush/stop acknowledgements and per-provider rates/ETA based on observations only.
- Schema v2 uses per-provider progress, job revisions, running state recovery, retry timestamps and unique query keys. A forced revision invalidates the prior result and checkpoints; obsolete work stops before its next provider and cannot commit a stale result. Completion writes the result and removes its job atomically. Provider requests interrupted before checkpoint may be retried after restart: logical durable jobs are deduplicated; external network calls are not promised exactly once.
- Dispatch alternates new-session imports with historical backlog. Executor submissions are limited to two jobs. SQLite busy timeout is 250 ms, entirely off the GUI thread. Database failures pause dispatch, retain staged envelopes and never increment commit acknowledgement for a failed batch. Retry of internal worker failures is capped at three attempts. Provider-specific HTTP retry/quota/capability policy remains S2.
- Existing DB integrity is checked before migration. Old schema receives a versioned SQLite backup through the backup API before transactional migration. Future/corrupt schemas fail closed without deleting the database. WAL is enabled only for positively identified local filesystems; UNC/network/unknown mounts retain rollback journaling. No live WAL/SHM file is removed.
- A writer lease prevents concurrent enable from resetting active jobs. Disable returns immediately; staging continues to flush. The successor waits off-GUI for acknowledgement before taking ownership. A terminated failed startup with no staged work permits a subsequent enable; retained uncommitted work never gets a false flush acknowledgement.
- Queued Qt signals carry immutable JSON result/backup receipts. Result caches and request mailboxes are bounded. Refresh epochs reject stale queued envelopes. GUI file identities and metadata snapshots reject edited, renamed, removed or replaced targets. A stale backup cannot remove a replacement watch. Full-media copying/hashing is on a separate single backup worker; only an acknowledged, still-valid target may proceed to Picard's existing asynchronous save.

## Validation and review

- Unit/contract suite: **129 tests** on Legion, including real SQLite BUSY and FULL failures, rollback/recovery, corrupt/future schema preservation, migration backup, revision fencing, fair selection, clean disable/enable and failed-startup recovery.
- Abrupt-process regression: seed 29,000 historical jobs, ingest and acknowledge 10,000 new jobs, kill only the synthetic helper process, reopen SQLite. **All 39,000 jobs remain**, with `quick_check=ok`.
- Real Qt synthetic load on Legion: **29,000 historical + 10,000 new identities**, maximum staging **2,048**, additional traced peak **36.53 MiB**, event-loop lag **p95 4.44 ms / p99 10.58 ms / max 32.89 ms**, elapsed **21.44 s**, **zero GUI SQLite calls**. Timer retries were accelerated to 2 ms to stress the bounded work slices. These measurements are a development fixture, not representative BMAX acceptance.
- Real Qt backup receipt probe: six scenarios (success, metadata edit, rename, plugin disable, backup failure, replacement watch). Only the unchanged enabled identity reached the save callback; heartbeat continued during synthetic slow backups. No actual audio was read or written. A separate generation probe rejects an old result queued before force-refresh.
- Real Qt native-dialog regression: a force request survives a full buffer and a subsequent file-selection change, eventually admitting the original identity rather than silently reverting to a cached search.
- Independent read-only review found four defects: stale forced result delivery, idle failed-startup successor rejection, lost manual force under backpressure, stale backup deleting a replacement watch. Each was reproduced by a failing regression, fixed and verified green. No deferred review findings.
- Source compilation and `git diff --check` are required before commit. Tests run on Legion using its local Python plus an isolated free PyQt6 test environment; no paid CI/services were started.

Reproduce:

```sh
python3 -m unittest discover -s tests -q
python3 -m compileall -q neowulf_picard_repair tests
QT_QPA_PLATFORM=offscreen /tmp/picardwulf-s1-venv/bin/python tests/qt_scheduler_probe.py
QT_QPA_PLATFORM=offscreen /tmp/picardwulf-s1-venv/bin/python tests/qt_native_refresh_probe.py
git diff --check
```

## Remaining acceptance

S1 source evidence is separate from the **OPEN BMAX S0/S1 runtime gate**. No stable v1.0 tag or release is authorized by these tests. S2 provider policy, S3 calibrated edition ranking, S4 actual-media save completion/rollback and S5 controlled deployment remain pending. Existing Picard and original music have not been changed. The already-completed Deep Research was not restarted.
