# Changelog

## 1.0.1 bulk-import responsiveness hotfix — 2026-10-14 (BMAX runtime pending)

- Removed per-file SQLite read/write from the Picard file-load and bulk-refresh GUI hooks; work is batched and durably enqueued by a dedicated writer thread.
- Added bounded, fair GUI result polling with one batch SQLite read instead of up to 24 individual database opens per timer tick.
- Added pause/resume for metadata provider requests without terminating Picard. Pause state is saved in plugin config, and unfinished database backlog remains durable.
- Automatically pause an existing backlog above 2,000 jobs at plugin re-enable to avoid immediate large-scale requests after a live update.
- Added `Install-PicardWulf-Live.cmd` requiring explicit operator confirmation that PicardWulf is disabled before changing any plugin files; does not terminate or restart the running Picard process.
- Stress-tested 10,000 synthetic imported tracks and durable SQLite recovery, in addition to preexisting tests.
- **Not a claim of live repair:** no executable BMAX remote-control session is available; user-session GUI health and hot-reload still need direct confirmation.

## 1.0.0 source-ranking update — 2026-10-14 (runtime candidate)

- Added automatic best-release selection after Add Folder: MusicBrainz has no built-in ranking priority.
- Source-neutral matching compares artist/title/album/album artist/duration, exact ISRC/MBID conflicts and release-specific corroboration.
- Added high-confidence auto-apply in Picard metadata, protected against ambiguous editions and concurrent native MusicBrainz assignment.
- Added optional explicitly enabled automatic audio-tag saving; every save requires a verified complete media backup first. It is OFF by default.
- Added Deezer, Spotify, Apple catalogue release identifiers and bounded Last.fm album enrichment.
- Exposed winning source/score/album, fixed result table clearing on periodic refresh, and kept native Picard album matching restricted to real MBIDs.
- Installer now includes two new modules and recognizes unmodified v1.0, v2 and v3 predecessors with pinned hashes; no force-upgrade of unknown edits.
- Added 11 cross-linked READMEs (English, German, Russian, French, Spanish, Italian, Portuguese-BR, Polish, Ukrainian, Japanese, Simplified Chinese).
- Local tests expanded to 110; BMAX Windows runtime, live provider responses and asynchronous tag writing remain NOT VERIFIED.

## 1.0.0 — 2026-10-14 (candidate; BMAX runtime gate pending)

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
