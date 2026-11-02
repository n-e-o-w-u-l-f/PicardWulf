# Picard 3.0.2 upstream Save/rename contract for PicardWulf

Checked on 2026-10-18 against the official release tag **`release-3.0.2`**, not the older `release-3.0.0rc4`. Picard 3.0.2 was published 2026-10-11.

## Source pins

- `metabrainz/picard` `release-3.0.2` `picard/file.py`, Git blob SHA **`9a710034b25e8bcb5f15b22530cf6687b9c3349e`**. See `File.save()` (line 474), `File._save_and_rename()`, `File.make_filename()` (line 779), `File._rename()` (line 800).
- `metabrainz/picard` `release-3.0.2` `picard/plugin3/api_impl.py`, Git blob SHA **`9d9ee6214bd46c2cabb431f78947fba34c5c88dc`**. `PluginApi.register_file_pre_save_processor()` around line 1097 accepts a callback that returns `None`, has no documented `cancel` or `redirect` value.
- `metabrainz/picard` `release-3.0.2` `picard/metadata.py`: `Metadata.getall()` returns every tag value, unlike `get()` which joins values. This is consumed by strict PicardWulf gold retirement.
- Official changelog: https://picard.musicbrainz.org/changelog/ (v3.0.2 2026-10-11).

## Verified call chain and collision limitation

On the Qt thread, native `File.save()` calls `self.set_pending()`, invokes `run_file_pre_save_processors(self)` and immediately schedules `_save_and_rename` on Picard's `save_thread_pool`. The pre-save processor notification's return value is not used as a veto. `_save_and_rename` first performs tag saving, then calls `_rename()`. The worker computes the configured destination with `make_filename()`, creates destination directories, then either chooses `get_available_filename()` when `move_overwrite_existing_files` is false or sends the configured canonical target to `_move_with_retry()` when true. Neither native branch chooses the larger of two independently verified FLACs or performs PicardWulf's separate SHA-256 recovery transaction.

**Conclusion:** A standard Picard-3.0.2 plugin's `register_file_pre_save_processor` cannot safely cancel, defer, or redirect native `Ctrl+S`. Setting `move_overwrite_existing_files` to true would bypass FLAC quality checks; setting it to false renames a duplicate with a suffix, not size arbitration. Temporarily toggling a global setting for an asynchronous worker is a race and **not** a correct implementation. No private `File._rename()` monkeypatch is authorized.

## Implemented available behavior in current PicardWulf

`SafeStagedFlacImport` is registered using Picard's **public file context action** API. It calculates a destination using the current real `File.make_filename(..., settings)`, inspects stored FLAC tags/decoder, and presents an explicit choice before a separate verified atomic copy/replace. As of source HEAD `877c6887e25b794ee82c9570e634568dd3a83faa`, the user's acceptance is pinned to exact source/destination SHA-256, `stat` signatures, paths and collision action, rechecked **inside the target lock**. Even if a valid FLAC changes after preview, the original target is retained. PicardWulf-initiated `File.save()` is separately limited to **tag-only** settings so the plugin's own auto/manual paths cannot silently trigger the unsafe native rename.

This is real supported in-app manual integration. **It is not an automatic `Ctrl+S` interception.**

## Necessary upstream/core work for full automatic native Save acceptance

Implement and verify in the upstream Picard 3.0.2 save/move lifecycle (preferably via an agreed, documented upstream extension) an explicit **collision arbitration contract** with:
1. A fully specified, immutable canonical target and tag-save completion boundary in the worker. No mutable Qt/Picard objects in filesystem/background work.
2. A synchronous, cancellable `ABSTAIN / KEEP_EXISTING / REPLACE_WITH_BACKUP / CREATE` result before any native move or overwrite; no bare bool hook that cannot veto.
3. Both recordings/release identity and full FLAC decoding, source/destination digests, separate immutable backup, OS-aware locking, atomic Windows-safe destination transition and recoverable rollback on post-commit verification failure. No unpaired MP3 unlink.
4. Correct Tagger `File.filename`, `tagger.files`, save progress/in-flight events, error state, album Gold UI and resume behavior for KEEP/ABSTAIN/REPLACE; no false `saved` or `gold` result when files were not moved.
5. Disposable Windows acceptance for locked files, cross-volume moves, simultaneous saves and stale/restarted recovery, plus active preset-3 and series naming. Ensure native Picard 3.0.2 upgrade does not silently remove or override the extension.

Do not classify core interception as done until an actual patched/supported source implementation runs through native `File.save()`, with automated integration tests AND verified BMAX user-session acceptance. No BMAX authentication is established by Tailscale PONG alone; latest Remote Desktop Commander remote-call quota remains zero.

## Next

Research an upstream-supported extension point or produce an independently tested **source-level** Picard 3.0.2 SaveCoordinator enhancement with explicit abort/defer and rollback, then validate in a disposable isolated Picard build and BMAX Windows test profile. Never substitute a preview, custom menu shortcut or general configuration toggle for the required automatic native save acceptance. Preserve all public branches and user media until verified.
