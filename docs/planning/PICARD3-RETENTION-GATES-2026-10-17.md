# PicardWulf / Picard 3: FLAC retention & completed-album removal

Date: 2026-10-17 (Europe/Berlin)  
Status: SOURCE-ONLY / SYNTHETIC + REAL GENERATED AUDIO TESTED ON LEGION / BMAX RUNTIME NOT VERIFIED  
Target remains PicardWulf **v1.0**; no new release tag or Windows rollout.

## Request and acceptance

1. Two files proven to represent the exact same recording: replace a smaller existing FLAC with a larger incoming FLAC, retaining an independently checksum-verified rollback; skip the incoming file when the existing one is equal or larger. Uncertain identities are not duplicates.
2. FLAC-only destination: reject blind MP3 deletion. After a FLAC write has genuinely completed and tags have independently been re-read, a **same-directory, same-stem** MP3 can be removed only when actual formats, artist/title/album/disc/track, durations and complete FLAC decoding are verified. Before MP3 unlink, keep an independently verified recovery backup outside the library. Unique/unpaired MP3 is preserved and reported for conversion/acquisition, never silently discarded.
3. Fully processed gold albums: remove only the album object from the Picard UI, never delete/move any music files or use the recycle bin. Picard 3 already provides **Options -> General -> Remove complete albums after saving**; this requires all release tracks matched and all files saved. Native option still needs live BMAX confirmation and an additional zero-discrepancy/PicardWulf-readback gate if required.

## Implemented in this source branch

- `retention_policy.py`: fail-closed format and identity checks, explicit size decision, rollback-protected atomic FLAC replacement primitive, permanent MP3 removal only with verified FLAC decoder pass.
- `save_tracking.py`: optional worker-only retention callback *after* post-save tag readback VERIFIED. Never execute filesystem cleanup directly from Picard GUI hooks. Skip cleanup after MISMATCH, UNVERIFIED, or missing post-save signal.
- `__init__.py`: `flac_only_cleanup=True` default for PicardWulf-initiated, backup-protected, *verified FLAC saves*; independently backs up same-stem MP3 before attempting deletion. If `flac` command is unavailable, or no matching MP3 is found, no deletion.
- Installer integrity inventory includes the new module.
- 240 Python tests PASS on Legion, including synthetic duplicate/worker regressions and a generated real FLAC/MP3 audio integration test (full decoder, MP3 recovery receipt and atomic FLAC replacement). GitHub branch and Legion fresh checkout; tested commit logged separately in project LAST.

## Explicitly OPEN (not accepted)

- **Automatic duplicate interception during Picard's own rename/move/save** is NOT wired. The source primitive is directly tested but currently does not run from the Picard save pipeline. Picard file-naming scripts cannot decide by disk file size.
- **Gold status auto-retirement** is not enabled on BMAX. Native Picard general option can remove complete saved albums, but it is distinct from independent PicardWulf tag readback.
- **MP3 cleanup coverage** is limited to exact same-stem files on the same directory, and only after PicardWulf verified auto/manual saves. Pre-existing gold albums, different file names, unsaved tracks and library-wide MP3 scanning are not covered.
- No genuine BMAX/Picard-3 plugin activation, FLAC decoder availability, renamed destinations, Windows file locks, metadata padding, symlinks, or production music acceptance test.
- Generated disposable synthetic audio was encoded/tested/deleted inside an isolated temporary test directory on Legion. No personal media deleted, moved or rewritten by this source task. No BMAX deployment/restart, no paid CI.

## Next safe gates

1. Acquire authorized BMAX-B6 `megal` Picard-3 runtime, preserve current Picard session and active preset 3; confirm native general setting, target naming-script/profile, FLAC binary, and backup location.
2. Implement **pre-save planned destination collision interception** (do not let Picard silently create a `(1)` copy or overwrite). Test the correct destination with current move/rename settings and match identity; integrate size decision outside the GUI thread.
3. Define UI gold removal only on zero-conflict completion **after** PicardWulf readback; test both pre-existing and newly-saved gold albums using disposable files.
4. Test real FLAC/MP3 sample copies under Windows with full FLAC decode, backup/rollback and collision cases; verify no MP3 is touched without matched FLAC.
5. Preserve source HEAD, tests, logs and state; only after all gates PASS merge/release/deploy and independently verify live behavior.

Documentation: https://picard-docs.musicbrainz.org/en/v3.0/config/options_general.html

## Continuation: strict gold UI-retirement source gate (2026-10-17)

- Verified actual upstream **Picard 3.0.0rc4** code: `Tagger._remove_album_if_complete` checks complete + no unsaved immediately in its own post-save hook. This is NOT independent FLAC/PicardWulf tag readback. A native auto-removal setting already enabled on BMAX can therefore remove an album before the stricter plugin gate; disable the built-in **Remove complete albums after saving** option during strict-mode acceptance and let PicardWulf's own gold controller perform the retirement. The source branch deliberately does not silently change the owner's existing Picard.ini or preset 3.
- New `gold_retirement.py` `capture_gold` requires loaded and current album identity, all tracks matched, no unsaved/unmatched or errors, one distinct saved FLAC per track, no PicardWulf conflict flag, and exact original/current metadata consistency. The worker reads actual FLAC content/tags via Mutagen off the GUI thread; success is rechecked after queued Qt delivery, then `api.tagger.window.panel.remove([album])` is used (the same UI-only entry point as Picard's native remover). **No audio unlink or recycling is performed by gold retirement.**
- `SaveTracker` provides bounded path-specific verification outcomes and in-flight detection. A pending, unverified, mismatched, timed-out or failed save blocks gold retirement. The controller uses bounded round-robin scans of all albums (at most 100 per tick) and 60-second retry backoff on failed disk readback; no file I/O on the GUI thread. The plugin starts/stops the controller during normal enable/disable only with a real Qt window; installer module inventory updated.
- Synthetic Qt queued-delivery tests check that a worker completion alone never removes an album; only GUI delivery after renewed eligibility does. Concurrent saves, later mismatches and albums removed elsewhere abort retirement. A generated **real FLAC** was used to validate successful and mismatched tag readback; same disposable integration also tests FLAC/MP3 retention.
- **Verified on Legion source HEAD `ce9e3f4721ca651b13e8460541198f461ab44558`:** 258 Python tests PASS, compileall PASS, git diff --check PASS. Added live SaveTracker path-status regressions (VERIFIED/MISMATCH/UNKNOWN_TIMEOUT). Initial mock Qt test failure was a test-only nested Python class scoping `NameError`; corrected the stub and reran the complete suite. No external paid CI used.

### Remaining production gates

- **BMAX-B6, user `megal`**: active preset/profile, Picard 3 build, running plugin version, native auto-album removal setting, PyQt6 queued delivery, FLAC command and Windows file locks remain unverified due missing authenticated live access and RDC quota.
- **Automatic destination collision resolution** is still NOT installed into Picard's native save path. The public pre-save hook does not itself provide a documented cancel/skip/redirect mechanism; do not monkey-patch private `File._save_and_rename` or pretend that a size decision file helper intercepts a native `(1)` rename. Needs explicit upstream-compatible integration and Windows disposable-file tests.
- Source checks do not authorize deployment, merge, release or deletion of personal MP3 media. Leave PR as DRAFT until live verification of all requested behavior.
