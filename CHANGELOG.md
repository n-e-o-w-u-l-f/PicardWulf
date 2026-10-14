# Changelog

### 2026-10-14 — v1.0 S3 release ranking (source milestone)

- Add edition/date/region/barcode/track/disc guards, recording/release MBID separation, production snapshot preservation and context-sensitive release-v2 cache keys.
- Preserve version and credit distinctions, expose matching-point contributions and all sorted alternatives, abstain on missing evidence, and resolve compatible edition ties only with verified distinct sibling-recording consensus.
- Freeze applied previews and reopen review on later conflicts without replacing tags. Preserve preexisting native release IDs and source-neutral Deezer/Spotify winners.
- Validate the 41-case curated synthetic corpus (10 correct automatic proposals, 31 abstentions, zero incorrect assignments), unit/Qt regressions and 39k synthetic load. BMAX, full tracklists/unverified transliteration and S4/S5 acceptance remain separately limited. [Evidence](docs/planning/S3-EXECUTION-2026-10-14.md).

### 2026-10-14 — v1.0 S2 provider policy (source milestone)

- Add explicit provider capabilities/consent, persisted request budgets/cooldowns/circuit state, bounded retries and operator controls. Partial/error responses cannot auto-apply or masquerade as empty successful searches.
- Preserve source-neutral ranking while reusing complete local cache decisions, pacing multi-request adapters, selectively enriching Last.fm and retaining exact recording/ISRC lookup.
- Guard existing Spotify access and SoundCloud's quota-reserved single-use refresh with encrypted acknowledgement; move credential updates off-GUI and preserve current rotated vault data.
- Harden schemas, redirects, response bounds, secret-safe reason codes and iTunes JSON MIME handling; cache no artwork or authentication payloads.
- Validate 145 tests, real Qt load/operator probes and anonymous MusicBrainz/Deezer/iTunes catalogue responses. Credentialed providers and BMAX remain unverified. [Evidence and limits](docs/planning/S2-EXECUTION-2026-10-14.md).

### 2026-10-14 — v1.0 S1 durable background scheduler (source milestone)

- Bound uncommitted admission to 2,048 jobs, including in-flight batches; retry overflow through weak Picard file identities and display staged versus committed state.
- Move SQLite initialization, migration, status/result reads and all full-media backup work off GUI callbacks. Serialize runtime DB operations through one leased writer and deliver immutable receipts with queued Qt signals.
- Add transactional schema v2 migration with consistent SQLite backup, per-provider progress, revision fencing, restart recovery, bounded retries and fair dispatch for new files alongside historical backlog.
- Make disable/enable wait for a background flush acknowledgement; preserve failed batches and reject stale force-result/backup completions and edited/renamed targets.
- Validate 129 unit/contract tests, real SQLite BUSY/FULL, abrupt helper termination with 39k retained jobs, and real Qt load/backup/refresh regressions. See [S1 evidence](docs/planning/S1-EXECUTION-2026-10-14.md).
- BMAX runtime and deployment remain OPEN. No stable release, Picard restart, original music change, new paid service or repeated Deep Research.

## PicardWulf v1.0 — Target release (Windows runtime acceptance pending)

All changes below belong to the **same v1.0 development target**. A completed local fix is a development milestone, not a new product release. The version remains v1.0 until all release acceptance criteria have been met.

### 2026-10-14 — Source-neutral 75% similar album context lookup and safe unknown-version upgrade

- Register Picard 3 album/cluster context actions for all enabled authorized provider searches and rank selectable release suggestions with >=75% confidence and >=75% track coverage.
- Keep MusicBrainz/Deezer/SoundCloud/Spotify/Last.fm/Apple release identities separate, without invented MusicBrainz IDs or automatic audio writes. Search respects provider credentials, quotas and SQLite work limits.
- Explicit -AllowUnrecognizedExisting allows UUID-verified prior plugin with a second approval and FULL retained rollback directory, not silent overwriting.
- Unit and real Qt offscreen dialog tests passed; BMAX live deployment and authenticated provider acceptance remain unverified. Target is v1.0.

### 2026-10-14 — Fix skipped provider comparisons for newly imported tracks

- Corrected an early return: a strong match in an album-local cache was not proof that each enabled provider had been consulted for this newly imported recording.
- Removed Last.fm early omission after an already strong MusicBrainz/Deezer hit. Completed exact-query checkpoints and source caches remain reusable; API limits and retries remain respected.
- Four new synthetic tests cover both previously failing paths, SoundCloud vs Deezer/MusicBrainz and completed checkpoint reuse. 180 Legion tests PASS. [Evidence](docs/planning/V1.0-PROVIDER-COMPLETENESS-2026-10-14.md). Target remains v1.0.

### 2026-10-14 — Full source metadata and provider access

- Public Deezer detail enrichment for one strong match: track/album endpoints with a shared quota and strict numeric URL allowlist; collect ISRC, track/disc numbers, label, barcode, album artist and dates where available; no artwork cached.
- Extend provider candidate/tag proposals with real track numbers, totals, release dates, label, genre, composer and barcode; preserve curated user fields automatically and never forge an external MusicBrainz ID.
- Add inverse ranking regression: MusicBrainz can win over Deezer just as Deezer may win over MusicBrainz. Contradictory details veto automatic acceptance.
- Correct unwanted auto-pause when backlog exceeds 2,000 entries: it is now a visible warning, while explicit user pause remains authoritative and provider requests are still bounded.
- Invalidate prior full-metadata result/album cache keys to prevent replaying old incomplete adapter results. No BMAX running session changed.
- Public providers verified from Legion; SoundCloud/Spotify/Last.fm app credentials require user-specific registration/eligibility; no purchase attempted. See docs/planning/V1.0-PROVIDER-ACCESS.md.

### 2026-10-14 — Bulk-import responsiveness and live plugin update

- Removed per-file SQLite read/write from the Picard file-load and bulk-refresh GUI hooks; work is batched and durably enqueued by a dedicated writer thread.
- Added bounded, fair GUI result polling with one batch SQLite read instead of up to 24 individual database opens per timer tick.
- Added pause/resume for metadata provider requests without terminating Picard. Pause state is saved in plugin config, and unfinished database backlog remains durable.
- The previous large-backlog auto-pause has been superseded by the warning-only behavior described above.
- Added `Install-PicardWulf-Live.cmd` requiring explicit operator confirmation that PicardWulf is disabled before changing any plugin files; does not terminate or restart the running Picard process.
- Stress-tested 10,000 synthetic imported tracks and durable SQLite recovery, in addition to preexisting tests.
- **Not a claim of live repair:** no executable BMAX remote-control session is available; user-session GUI health and hot-reload still need direct confirmation.

### 2026-10-14 — Cross-provider release ranking

- Added automatic best-release selection after Add Folder: MusicBrainz has no built-in ranking priority.
- Source-neutral matching compares artist/title/album/album artist/duration, exact ISRC/MBID conflicts and release-specific corroboration.
- Added high-confidence auto-apply in Picard metadata, protected against ambiguous editions and concurrent native MusicBrainz assignment.
- Added optional explicitly enabled automatic audio-tag saving; every save requires a verified complete media backup first. It is OFF by default.
- Added Deezer, Spotify, Apple catalogue release identifiers and bounded Last.fm album enrichment.
- Exposed winning source/score/album, fixed result table clearing on periodic refresh, and kept native Picard album matching restricted to real MBIDs.
- Installer now includes two new modules and recognizes unmodified v1.0, v2 and v3 predecessors with pinned hashes; no force-upgrade of unknown edits.
- Added 11 cross-linked READMEs (English, German, Russian, French, Spanish, Italian, Portuguese-BR, Polish, Ukrainian, Japanese, Simplified Chinese).
- Local tests expanded to 110; BMAX Windows runtime, live provider responses and asynchronous tag writing remain NOT VERIFIED.

### 2026-10-14 — Base plugin and native matching

- Added Picard-native MusicBrainz release/recording linking from shared candidate review.
- Added explicit tag-field diff preview, opt-in native saving and hash-verified full audio backups.
- Added right-click action for selected Picard files; kept Tools > NEOWULF legacy actions.
- Preserved unified MusicBrainz/Deezer/iTunes/Spotify/SoundCloud/Last.fm search adapters.
- Fixed MusicBrainz HTTP endpoint allowlist and added ISRC→official MB recording cross-lookup.
- Preserved SQLite queue/caching, rate limits, retry status and artist/album confidence safeguards.
- Upgraded installer to recognize and preserve unmodified v2 and v3 source before replacing.
- Preserved existing plugin UUID and never invoked incomplete frozen `picard-cli.exe`.
- Added source-level regression tests for native matching, conflicting MBIDs, provenance and full-media backup.

Live BMAX Picard 3 plugin runtime, API auth, album matching and tag writes have **not** been verified yet.
