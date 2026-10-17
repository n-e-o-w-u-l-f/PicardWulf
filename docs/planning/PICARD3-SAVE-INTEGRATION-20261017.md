# PicardWulf — integration into Picard 3 and BMAX verification

**Date:** 2026-10-17 · **Status:** PLUGIN ACTION IMPLEMENTED / TESTED ON LEGION / BMAX INSTALLATION AND CTRL+S AUTOMATION STILL OPEN
**Branch:** `feature/picard3-retention-policy-20261017` · PR #1 (draft)

## Parent acceptance and objective

The requested final result is **native Picard 3 behavior**, not source-only code: on save, recognize the *actual same recording/release* using artist/title/album/track, duration, optional MusicBrainz recording and release IDs/ISRC, verify FLAC decode, keep the larger lossless file (retaining the prior file in an independent backup), keep existing equal/larger, never delete unpaired MP3, keep preset 3 and series paths, and remove gold albums **only from Picard's UI** after strict independent verified readback.

## Implemented application-level invocation

- Registered a supported Picard-3 `BaseAction` using `api.register_file_action(SafeStagedFlacImport)` in `neowulf_picard_repair/__init__.py`, with the visible label **„PicardWulf: FLAC sicher in Musikbibliothek übernehmen (mit Backup)“**.
- `picard_safe_import.py` calls `File.make_filename(..., current_settings)` on the GUI thread. No invented naming profile, no changed Picard.ini, no override of private `File._rename()`.
- The action is for **one already saved, fully tagged FLAC from an independent staging folder**. Picard's `move_files` must be on with an existing **absolute** `move_files_to` library root and `move_overwrite_existing_files` must be **off**. A selected outside-library backup root is required. The action refuses unsaved, in-flight and error files. It does not move/rename the Picard File object or alter the original staging file.
- A worker first computes read-only `WOULD_CREATE`, `WOULD_SKIP`, `WOULD_REPLACE`; ambiguous/invalid tracks fail closed. An explicit confirmation and renewed File/profile snapshot check precede the second worker call, which performs the independently verified backend operation. The UI reports the actual completed action. The source remains in the Picard view until the user refreshes/reloads it.
- `staged_flac_import.py` now supports nested not-yet-existing **series/album folders** below the trusted library root: create only on apply, reject redirected/symlink targets, remove newly created empty folders on failure. New exclusive target uses atomic hardlink from fully verified temporary copy; matching smaller existing FLAC is backed up (independent SHA-256 checked) then atomically replaced; existing equal/larger preserved. Entire FLAC decoder check required on both sides. No source file unlinks.
- Installer's `Install-NEOWULF.ps1` manifest inventories the new plugin module; disable() terminates pending view timers. All implementation in draft branch; nothing installed on BMAX yet.

## Live infrastructure evidence

From connected SentinelX `legion` under process identity `sentinelx` on 2026-10-17:
- OS is Arch Linux, Tailscale daemon `Running`; BMAX-B6 appears as a peer.
- `bmax-b6` DNS resolved to `100.87.234.27`; TCP/22 reachable.
- No SSH authentication agent available and no visible SSH `*.pub` file in `sentinelx`'s home. `ssh -G megal@bmax-b6` shows standard publickey auth and key search paths. **No successful authenticated login to BMAX was observed**. Earlier failed login is not retried blindly. RDC monthly remote tool quota observed 0%.
- A TCP response or connected Tailscale peer is **not** evidence of BMAX OS/Picard/FLAC executable runtime, user `megal` session or permission to modify media. Do not try other users, arbitrary key files or remote permission bypass.

## Verified and unverified acceptance matrix

| Gate | State | Evidence / NEXT |
|---|---|---|
| Source collision decision + safe rollback | **SOURCE/LEGION PASS** | independent importer tests, generated real FLAC |
| Picard-3 GUI action dispatch | **MOCK/LEGION PASS** | file action registered; GUI confirmation/abort/async tests |
| Native Picard `Ctrl+S` interception | **OPEN** | upstream `register_file_pre_save_processor` returns no veto/redirect; core save writes tags then chooses rename. Requires a supported upstream extension or full validated lifecycle design |
| New target folder creation | **LEGION PASS** | nested series/album folder and empty-folder rollback |
| Real BMAX authenticated login | **BLOCKED/AUTH UNKNOWN** | peer and TCP reachable, `sentinelx` holds no usable SSH identity |
| Installed Windows Picard/PyQt6 runtime and actual native preset 3 | **NOT RUN** | must inspect authenticated `megal` user environment |
| Actual Windows source/destination volume locks and recovery | **NOT RUN** | only disposable, independent file copies after verified access |
| Production enabled / source music modified | **NO** | no original media change authorized by source-only validation |
| Gold UI-only retirement | **SOURCE/LEGION TESTED, BMAX OPEN** | independent tag-readback controller exists; native remove-complete must be off during acceptance |

## Execution plan (governance §28.2)

1. Recheck permitted BMAX route through a legitimately authorized SSH key/agent belonging to the chosen executing identity, or a restored remote connector quota. Do **not** treat "no key in sentinelx home" as permission to read other users' secrets or generate an unauthorized account.
2. In a read-only BMAX session, verify actual OS build/user, installed Picard 3 build, Python/Qt/plugin API, `flac` and Mutagen, Picard current profile, preset 3 resolved script, current move/overwrite and native remove-complete settings. Do not silently change any of these.
3. Install the reviewed draft plugin in an isolated Windows test Picard profile or copy, not over the owner's active plugin/session. On disposable real FLAC files verify GUI event loop, available paths, new album folders, equal/bigger/collision, snapshots, rollback and file locks. Publish red/green evidence.
4. To make **normal native File.save()/Ctrl+S fully automatic** with the user's larger-FLAC policy, research/implement a supported upstream collision-decision extension or a separately tested Picard SaveCoordinator with consistent Picard File/Tagger identity and post-save rollback. Native pre-save callbacks cannot currently abort/redirect; a new menu action is not equivalent. Do not install a private monkey-patch to close the gap cosmetically.
5. Repeat target-runtime acceptance on BMAX and only then change PR from draft, merge, version and enable, protecting original music. Persist current state and each material PRE/POST in PicardWulf and global governance.

## Failure and governance feedback

A previous source-only stopping pattern was insufficient: code existed but there was no Picard registration nor live host diagnosis. The new canonical `governance/workflows/execution.md` §28.2 requires automatic current-state discovery, implementation of missing invocation, actual target-runtime verification and durable DELTA/NEXT whenever that state is encountered. It explicitly forbids claiming a mock test or open SSH port means deployment; it is an on-encounter rule, not an always-on unattended process.

**Source tests:** 318 PASS (Legion), `compileall` PASS, `git diff --check` PASS at tested code `92e562cc890cceb59afa817be5efe1825dd76ca3`. Windows runtime and native `Ctrl+S` remain unverified.
