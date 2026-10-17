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

## Picard 3 filename-collision preview continuation (2026-10-17)

- Upstream source for Picard 3.0.0rc4 was reviewed: `File.save()` calls a pre-save processor **without a cancel/redirect API**, then saves via `_save_and_rename`. When rename/move is enabled, `File._rename()` computes its destination via `File.make_filename(...)`. If `move_overwrite_existing_files` is false, Picard chooses an available filename; if true, the target can be overwritten **regardless of the PicardWulf larger/smaller decision**. The pre-save plugin hook cannot reliably veto that native code path. An unsupported monkey-patch was deliberately rejected.
- Added `collision_preview.py` and Picard 3 File context menu action **PicardWulf: Dateikollisionen / FLAC-Größenregel prüfen (nur lesen)**. It derives the anticipated target from the live File object's `make_filename` under the active profile (including preset 3), gathers at most 20 selected files on the GUI thread, and compares actual FLAC tags/duration/size off the GUI thread. Results distinguish unchanged path, free destination, validated larger incoming FLAC, larger/equal existing FLAC, inconsistent identity, and native Picard overwrite-risk. No real file is modified or deleted. Newly created target folders are treated as possible and are not created during preview; symlink targets are rejected.
- Plugin disable stops any outstanding preview Qt timer; installer inventory and test-contract expected action count updated. File selection uses a lazy bounded iterator and does not enumerate a 100,000-track GUI selection. Added 18 isolated collision tests including symlinks, hardlinks, Picard-derived paths, disabled renaming, missing settings, bounding and preset preservation.
- **Legion verification:** `38eff80f78fd50dd2992a579c437cd4af019830d` — **276 Python tests PASS**, compileall PASS, git diff --check PASS. Windows Qt and BMAX runtime NOT RUN. The read-only preview is not the requested automatic skip/replace behavior, and must not be advertised as such.

### Remaining native collision blocker

Picard's native per-save collision behavior cannot be overridden through the documented Picard 3 plugin pre-save extension (it is called before tagging, returns None, and has no documented veto). Safe automatic collision arbitration therefore requires a Picard-supported cancel/rename hook upstream or a separately opt-in organizer whose media handling and GUI synchronization are independently tested. Do not silently change global Picard settings, replace core Picard methods, or delete any incoming file as a shortcut. Existing PR #1 remains draft until end-to-end BMAX and full automatic acceptance.

## Fortsetzung 2026-10-17: Gold-UI-Skalierung und native Picard-Kollision

- Picard-3-Quellcode `picard/metadata.py` (`release-3.0.0rc4`): `Metadata.get()` fügt mehrere Werte zu einem String zusammen; `Metadata.getall()` ist die korrekte Schnittstelle für alle Einzelwerte. Die Gold-Prüfung verwendet `getall()` und liest Mutagen-FLAC-Tags vollständig; auch ein abweichender **zweiter** Genre-/Artist-Wert verhindert die Entfernung. Optional vorhandene `musicbrainz_albumid`, `musicbrainz_recordingid`, ISRC, Datum, Barcode, Label, Genre und Albumartist werden geprüft. Auch ein aus Metadaten entfernnter früherer Release-Identifier verhindert die Entfernung.
- Picards eigenes `remove_complete_albums_after_save` kann die Albumansicht vor PicardWulfs unabhängigem FLAC-Readback entfernen. Bei nativer Option `True` **oder unbekannt** führt PicardWulf daher seine Gold-UI-Entfernung nicht aus. Die Einstellung wird nicht stillschweigend geändert. Der bestehende Menüpunkt **Tag-Speicherstatus** zeigt ausdrücklich `GESPERRT` samt Hinweis auf Picards möglicherweise frühere Entfernung, `NICHT GESTARTET` oder `AKTIV`. Die Prüfung wird nochmals unmittelbar vor der Qt-Entfernung wiederholt.
- Vorher erzeugte der Gold-Controller alle 3 Sekunden `tuple(api.tagger.albums.values())`. Jetzt wird ein fortsetzbarer Iterator mit höchstens 100 Albumprüfungen pro Durchlauf verwendet. Ändert sich die Alben-Dictionary während der Iteration, wird kontrolliert abgebrochen und beim nächsten Timerlauf neu begonnen. Keine Dateizugriffe oder Metadaten-Dekodierung auf dem Qt-GUI-Thread.
- Synthetische Qt-Regressionen prüfen das native Option-Flag (einschließlich Wechsel zwischen Worker und Qt-Rückmeldung), 2.500 geladene Alben ohne Vollmaterialisierung, Mutation der Registry, operatorseitige Statuswarnungen und `Metadata.getall()` mit verschiedenen Mehrfachwerten.
- **PASS:** 304 Python-Tests, `compileall` und `git diff --check`, Legion sauberer Checkout at `6c6c015d1d30097553bf6cbd7e86c2f5a9fd1c9b`. Kein BMAX-Lauftest, kein Release und keine Änderungen am aktiven Picard oder Originalmusik.
- **Offen:** Bei **aktivem** nativen Picard-Gold-Autoremove kann Picard selbst weiterhin vorzeitig entfernen; PicardWulf kontrolliert nur die **eigene** Entfernung. Für strenge Gold-Akzeptanz muss die native Option auf BMAX zunächst verifiziert und deaktiviert sein. Das tatsächliche native FLAC-Kollisions-Veto bleibt unabhängig davon ohne dokumentierten Picard-3-Plugin-Hook. PR #1 bleibt DRAFT.
