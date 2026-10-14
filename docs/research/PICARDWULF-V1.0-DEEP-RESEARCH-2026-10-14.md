# PicardWulf v1.0 — Deep Architecture & Stability Research

**Research date:** 2026-10-14 (Europe/Berlin)
**Scope:** user-requested complete NEOWULF/PicardWulf feature integration, scalable 29k existing + 10k newly added tracks, unified release choice across metadata providers, safe tags and naming, no extra paid subscriptions/runners.
**Source of truth:** `n-e-o-w-u-l-f/PicardWulf` main, inspected HEAD `97d59e52e3b9251681bf22521f504c8fc46774c8`.
**Status:** DESIGN/RESEARCH ONLY. No BMAX runtime operation or completion claim. **Target remains v1.0.**
**Source quality:** Code findings below were verified against repository files. External API/lifecycle statements are backed by official primary docs. Proposed controls are not yet implemented.

## 1. Architecture verdict

The current v1.0 code is a useful prototype with 119 local tests; it is **not production-certified** for a 39k-track Picard session. The correct design is **one durable, bounded scheduler + one normalized provider adapter registry + one release/recording candidate graph + one controlled commit pipeline**, with a Qt-only UI orchestrator. Simply increasing the thread count or searching all six providers for all files magnifies rate limits and UI pressure.

### Required invariants
1. **KEEP PICARD OPEN:** Never kill/restart Picard to fix a metadata backlog; no cache/queue deletion while live.
2. **GUI SAFE:** Picard File, Qt objects and widgets stay on GUI thread; **no disk access, sqlite waits, hashing full media, HTTP, backup copying or long loops in event handlers**. Asynchronous results return through a Qt queued signal.
3. **DURABLE BEFORE ACK:** Never announce a job as queued/persisted until its DB transaction commits. Memory-only staging is explicitly transient; on a full buffer persist/backpressure via worker, not unbounded RAM or silent loss.
4. **PROVIDER NEUTRAL:** MusicBrainz is not the scoring winner by definition. A Deezer, Spotify, SoundCloud, Last.fm or iTunes release can win on evidence when actually available and permitted. Source name is provenance **only**.
5. **RELEASE != RECORDING:** ISRC/AcoustID/recording MBID identify a recording or composition signal, not a unique album edition; verify release title, album artist, tracklist, track number, year, edition, barcode and source-specific release IDs separately.
6. **NO FAKE MBIDS:** Only authentic MusicBrainz Release+Recording MBID pairs enter the native Picard album pane. External release winners are represented in the PicardWulf result panel and eligible Picard file metadata.
7. **NO UNSAFE WRITE:** No file save by default; optional auto save only after explicit configuration, full verified backup, immutable original-file identity check and post-save confirmation. Never interpret `file.save()` returning as success.
8. **NO EXTRA SPEND:** Existing local Legion runner and legitimate free APIs where usable; never assume free Spotify dev-mode access or require paid SoundCloud Artist Pro for v1.0. If access is unavailable, show unavailable and continue with healthy sources.
9. **NO SILENT LOSS:** Interrupted/failed provider calls do not turn into cache-success; pending DB tasks survive clean reload; record per-provider partial status.
10. **SOURCE AUDIT:** Structured logs redact secrets and paths when exported; provenance/audit records preserve source, source identifier, original values, scores, rule version, timestamp and whether tags were actually saved.

## 2. Source-backed external constraints

| Provider / subsystem | Primary documented fact | Design consequence |
| --- | --- | --- |
| MusicBrainz | Non-commercial web service requires meaningful User-Agent, max ~1 request/s per IP; recording search vs release lookup are different entities [MB API]. | Rate budget must be shared between recording search, cross-source ISRC lookup and Picard-native queries when possible; never flood with 10k individual requests. |
| Apple iTunes Search | Approx. **20 requests/minute** and caching strongly encouraged [Apple Search]. | 10k individual Apple queries need ~500 minutes at best, before errors; use selective fan-out and durable cache, **not** all-provider mass search. |
| Spotify | Feb 2026 development mode changes: owner **Premium** required; reduced dev quotas/search limit and eligibility, extended quota has separate approval [Spotify Migration]. | Optional adapter; no purchase; preflight token+endpoint+quota; disabled with informative status if no existing eligible credentials. |
| SoundCloud | Current API guide states OAuth 2.1, PKCE, ~1h tokens, single-use refresh tokens; public catalog client_credentials possible for registered clients. Token limits: 50/12h/app, 30/h/IP [SC Guide]. | Static access-token-only adapter is incomplete; credential lifecycle, throttled refresh and scoped, encrypted token storage required; never invent an app or require paid account. |
| Deezer | Official FAQ documents search, query quota and ability to store artist/track text but **not album images**. May 2026 community indicates new app registration not open (not proof public /search broken) [Deezer FAQ][Deezer community]. | Public search must be runtime-probed and feature-gated. Never cache Deezer images; distinguish catalog metadata endpoint availability from new app registration. |
| Last.fm | Metadata track search can be queried with authorized API key; album details may need additional track.getInfo request [Last.fm API]. | Optional adapter, quota budget and selectively enrich only promising candidates; do not double network load for every track. |
| Qt 6 | Widgets and QObject tree are not generally cross-thread safe; long tasks must stay off GUI thread [Qt Threads]. | Design one UI signal bridge; worker threads return immutable data only. |
| SQLite | WAL separates readers/writers but can suffer checkpoint starvation, SQLITE_BUSY and excessive WAL growth [SQLite WAL]. | Single-writer queue, short transactions, WAL on **local** disk only, busy_timeout, integrity/migrations, bounded reader snapshots and idle checkpoint policy. |
| Picard 3 | Post-load, album/track metadata and post-save hooks are officially supported. File.save schedules asynchronous work and pre/post-save callbacks [Picard API][Picard processing][Picard file.py]. | Use post-save signals for success evidence, register cancellable tasks where appropriate, and keep the native Picard matching pipeline intact. |
| AcoustID | Acoustic fingerprint refers to recording identification, not necessarily a release edition [AcoustID]. | Fingerprint boosts recording identity but cannot decide whether *Curtain Call 2*, a remaster or single edition is the correct release. |

**References**
- [MB API] https://musicbrainz.org/doc/MusicBrainz_API
- [Apple Search] https://performance-partners.apple.com/search-api
- [Spotify Migration] https://developer.spotify.com/documentation/web-api/tutorials/february-2026-migration-guide
- [SC Guide] https://developers.soundcloud.com/docs/api/guide
- [Deezer FAQ] https://support.deezer.com/hc/en-gb/articles/360011538897-Deezer-FAQs-For-Developers
- [Deezer community] https://en.deezercommunity.com/features-feedback-44/app-registration-82666
- [Last.fm API] https://www.last.fm/api
- [Qt Threads] https://doc.qt.io/qt-6/threads-qobject.html
- [SQLite WAL] https://www.sqlite.org/wal.html
- [Picard API] https://github.com/metabrainz/picard/blob/master/docs/PLUGINSV3/API.md
- [Picard processing] https://picard-docs.musicbrainz.org/en/latest/extending/processing.html
- [Picard file.py] https://github.com/metabrainz/picard/blob/master/picard/file.py
- [AcoustID] https://picard-docs.musicbrainz.org/en/latest/tutorials/acoustid.html
- [Release-group types] https://musicbrainz.org/doc/Release_Group/Type
- [Canonical MusicBrainz data] https://musicbrainz.org/doc/Canonical_MusicBrainz_data

## 3. Current repository findings: priority-ranked hazards

| ID | Severity | Evidence from current project code | Required mitigation |
| --- | --- | --- | --- |
| P0-01 | CRITICAL | `universal_engine.py: schedule_async()` enqueues into an **unbounded in-memory deque**; GUI acknowledgment precedes SQLite persistence. `stop()` does not join the writer. | Bounded durable queue, explicit staged vs committed state, drain/flush handshake, progress and disk failure indication; power-kill recovery test. |
| P0-02 | CRITICAL | `auto_apply.py: poll()` directly calls `ResultStore.get_results()`; SQLite `_db()` has up to 8s lock wait and it runs on Qt timer. | Worker-owned DB reads + queued Qt signal; **zero SQLite operations on GUI thread**, measurable event-loop latency budget. |
| P0-03 | CRITICAL | `auto_apply.py: apply_best_to_file(...save=True)` calls `media_backup()` synchronously; full-file copy + hashing blocks the Picard GUI per file. | Async backup off GUI, original file identity+mtime+size/revalidate, then Qt-thread metadata edit and save, post-save audited confirmation. |
| P0-04 | HIGH | `_work()` iterates all configured sources per track. `HTTPClient` catches 429/503 but `_work()` stores partial `save_result` as complete and deletes job. | Provider-specific retryable state with Retry-After, bounded exponential jitter, last-success and skipped status; do not cache temporary outages as full success. |
| P0-05 | HIGH | `auto_selection.py` uses fixed 93.5% and simple string similarity, without a ground-truth album-edition evaluation dataset. | Golden master curated release cases; candidate graph grouped by edition and tracklist; calibrate thresholds by false positive and ambiguous cases. |
| P0-06 | HIGH | `native_workflow.py` `tag_proposal()` allows updates after scorer check; no full post-save journal, non-transactional async Picard save outcome. | Two-phase state PREVIEW→BACKED_UP→SAVE_REQUESTED→SAVE_CONFIRMED/FAILED; original hash and backup location, idempotent restore by explicit operator command. |
| P1-01 | HIGH | `universal_adapters.py` SoundCloud currently uses a supplied static OAuth token; no PKCE/refresh/expiry lifecycle. | Capability/auth service, refresh once per token, DPAPI+secret redaction; back off when not authorized. |
| P1-02 | HIGH | Spotify adapter assumes dev credentials usable; Spotify's 2026 Premium/limits can reject search. | No-pay credential audit and runtime provider capability probe. Disabled source must not stall entire album or be scored zero as though it returned no matches. |
| P1-03 | HIGH | `query_key` and `_work` are primarily **track-driven**, while user's desired choice is a **release edition**. | Album clustering, local tracklist/edition graph, provider album IDs, edition-specific score; compare across whole album where known. |
| P1-04 | HIGH | `auto_apply.py` relies on a weakref/path snapshot and a one-hour window; concurrent manual edits/native Picard assignment may race. | File identity + generation/version token and explicit ownership lock; invalidate stale automatic proposals if user edited fields. |
| P1-05 | MEDIUM | `auto_apply.py` only stores `~picardwulf_source`/score (private Picard fields) and result cache is query-keyed. | Durable field-level provenance ledger and transparent source-specific confidence. Never present private fields as tags saved to the music file. |
| P1-06 | MEDIUM | Hardcoded install host/user and merely human-confirmed disabled-plugin hot update. | Live deployment preflight for actual running plugin disable state, atomic replace+backup+hash rollback, no restart; strict stop if GUI unresponsive. |
| P1-07 | MEDIUM | Large import can schedule previously known songs as new jobs if tags/identifiers change; no album-indexed cache or scan-once invariant. | Per-file digest, imported-file identity and canonical recording cache; rescan only new/changed objects. |
| P2-01 | MEDIUM | Multiple data sources have different languages, regions, remix/feat credit conventions, reissue and compilations. | Explicit normalization that preserves canonical performer; flag mismatch, avoid "Compilation→VA" and "provider name→albumartist" errors. |
| P2-02 | MEDIUM | No verified runtime integration for Picard 3 Windows in 39k-track scenario, despite local tests. | BMAX disposable copy + actual GUI responsiveness, provider auth and save verification before stable v1.0 declaration. |
| P2-03 | LOW | Multilingual READMEs/manual providers may diverge from runtime UI behavior. | Single capability/status matrix, locale language docs link checks, release documentation gate. |

Severity is a risk assessment, not a statement that a specific user-file corruption or Windows-process crash has occurred.

## 4. Architectural target (one source of truth)

```text
Add Folder / file loaded (Picard GUI; immutable light snapshot only)
  └─ metadata identity + unchanged-file filter
     └─ bounded durable SQLite inbox (one writer; commit/ack)
        └─ adaptive planner: local index → MBID/ISRC/AcoustID → selective provider fan-out
           └─ adapter registry (capabilities, auth, quota, circuit breaker, source status)
              └─ normalized candidate store: recording vs release vs edition graph
                 └─ source-neutral calibrated scorer, album/tracklist consensus and conflict veto
                    ├─ REVIEW_REQUIRED / INCOMPLETE / AMBIGUOUS: leave user data untouched
                    └─ VERIFIED_WINNER: queued Qt UI signal; preview metadata
                       ├─ native MBIDs → Picard native release matching
                       └─ external provider → PicardWulf release view, **no fabricated MBID**
                          └─ optional confirmed save: async backup → verify → save request
                             └─ post-save receipt / error → journal & explicit restore option
```

### Efficiency: avoid provider fan-out until justified
- **Phase A local**: inspect original tags, embedded MBIDs, existing ISRC, album-folder grouping, known 29k cached entries; do not refetch unchanged tracks.
- **Phase B cheap identity**: use local cache of known recordings/releases first; eligible MusicBrainz query limited by global rate budget; AcoustID only if explicitly enabled/available and cost compliant.
- **Phase C selective multi-source**: compare Deezer/iTunes/Spotify/SoundCloud/Last.fm **only where needed**, based on confidence and access. User preference "all providers considered" means each provider has an eligible chance; do not require every provider for every file when already conclusively matched or unavailable.
- **Phase D release verification**: cross-check album-level consistency, competing editions, track numbering/date and artist credits; never group all versions of one recording into a release.
- **Phase E controlled commit**: freeze selection only after eligible providers reach COMPLETE/UNAVAILABLE/TIMEBOXED states; emit exactly one stable automatic proposal; later better evidence goes to review, not repeated overwrites.

### Persistent scheduler and provider state
- Schema version, transactional migration with full backup, `jobs` by file identity and query hash, `provider_tasks` by provider+request+etag, `releases`, `recordings`, `decisions`, `save_journal`, `provider_health`; no secrets stored in SQLite.
- States: `DISCOVERED`, `DURABLE`, `PLANNED`, `RUNNING`, `WAITING_QUOTA`, `PARTIAL`, `REVIEW`, `READY`, `APPLIED_IN_MEMORY`, `BACKED_UP`, `SAVE_PENDING`, `SAVE_CONFIRMED`, `FAILED_RETRYABLE`, `FAILED_FINAL`.
- Fixed bounded RAM, dedicated DB owner, batch writes and commit acknowledgment, resume token, fairness between current import and historical backlog; store total/completed/failed/deferred per source for progress.
- WAL **only after** checking storage is local, lock behavior, current DB integrity and rollback path. Monitor WAL checkpoint, disk budget, busy timeout, corruption recovery. Never delete a live database.

## 5. Candidate quality and confidence

The old fixed score is **not statistically calibrated probability**; label it "match score" rather than "*93.5% certain*". Separate hard veto (conflicting ISRC, known wrong performer, edition ID), recording confidence (ISRC, MBID, acoustic fingerprint, duration) and release confidence (tracklist, title, album artist, date/region, number of tracks, label/edition). Confidence should be calibrated against held-out samples, with abstention for uncertain cases.

**Required golden cases:** Eminem *Curtain Call 2* as artist compilation; different country editions; identical track on *Encore* and greatest-hits albums; multi-disc VA releases; remix featuring different artists; remaster/live/clean/explicit edition; same-title different performers; Unicode/Cyrillic artist aliases; 0-tag filename inference; wrong existing embedded MBID; fake provider artist like "Apple Music"; duplicate files; 29k existing + 10k fresh + 429; user edits during slow provider response.

## 6. Operational and security controls

- Distinguish **provider unavailable** from **no match**; show source status, HTTP code, last successful query and retry eligibility, without logging tokens.
- Legitimate read-only searches only, enforce HTTPS, redirect policy, response size/content-type and schema validation; never download audio or scrape webpages in violation of terms.
- Windows DPAPI credential storage remains local to `megal`; check expiry/rotation and any missing credential UX. No repository secrets.
- Preview source/confidence/field changes before commit; explicit per-provider consent for sending title/artist to external services.
- Atomic installer updates only after plugin disable **verified**, with backup and rollback. Picard itself remains running if it responds.
- Local Legion runner only, no newly charged GitHub Actions, no paid API subscriptions or registration bypass.
- Debug/report bundles redact personal file paths, auth data and potentially copyrighted album content; use synthetic fixture songs where possible.

## 7. Known unknowns / execution gates

1. **BMAX runtime**: Current Picard process state, plugin enabled status, loaded file counts, queue DB consistency, actual API error mix and memory/CPU are unknown because remote desktop quota is exhausted and only Legion agent is online. A Tailscale ping/SSH port proves only host reachability.
2. **Provider authorization**: Spotify 2026 eligibility, Deezer public search and SoundCloud app/token availability must be validated without purchases or bypass.
3. **Native Picard behavior**: Verify whether post-save callback is only emitted on success in the installed Picard 3 build and track async failures via file status/log events.
4. **Unmodified Windows runtime**: Tests on Legion with mocks do not certify Qt event loop or plugin hot reloading on BMAX.
5. **No external releases in native pane**: Upstream only supports authentic MusicBrainz release entities; external release's own representation must stay in a PicardWulf panel unless core Picard API changes.

**Execution plan, acceptance gates and immediate next action:** [V1.0-NEXT-EXECUTION.md](../planning/V1.0-NEXT-EXECUTION.md). This document is research, not an implemented feature list.
