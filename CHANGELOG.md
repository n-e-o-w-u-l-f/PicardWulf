# Changelog

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
