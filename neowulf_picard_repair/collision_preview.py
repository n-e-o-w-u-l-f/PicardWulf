"""PicardWulf: read-only Picard 3 destination-collision preview.

This is deliberately advisory. Picard's documented plugin pre-save callback
cannot veto File.save(), and the native _rename() runs AFTER tag writing.
Never perform file mutation here; use the exact File.make_filename() result
to preview potential destinations before the user starts a save.
"""
from concurrent.futures import ThreadPoolExecutor
from itertools import islice
import os
from pathlib import Path

from .retention_policy import decide_duplicate


def inspect_collision(source, target, *, native_overwrite=False, inspect=None):
    """Worker-only: compare existing and candidate paths without modifying either."""
    original, destination = Path(source), Path(target)
    try:
        if (not original.is_file() or original.is_symlink()
                or original.suffix.casefold() != ".flac"):
            return {"state": "REVIEW", "reason": "source_not_verified_flac"}
        if destination.is_symlink() or destination.parent.is_symlink():
            return {"state": "REVIEW", "reason": "target_symlink"}
        # Picard's native _rename() creates missing target directories.
        # Their absence is not a collision; do not create them in preview.
        ancestor = destination.parent
        while not ancestor.exists() and ancestor != ancestor.parent:
            ancestor = ancestor.parent
        if not ancestor.is_dir() or ancestor.is_symlink():
            return {"state": "REVIEW", "reason": "destination_ancestor_unsafe"}
        if (os.path.normcase(os.path.abspath(str(original)))
                == os.path.normcase(os.path.abspath(str(destination)))):
            return {"state": "SAME_FILE", "reason": "native_target_is_source"}
        if destination.exists() and os.path.samefile(original, destination):
            return {"state": "SAME_FILE", "reason": "same_inode"}
        if not destination.exists():
            return {"state": "FREE_TARGET", "reason": "no_existing_destination"}
        if not destination.is_file():
            return {"state": "REVIEW", "reason": "occupied_non_file_target"}
        if destination.suffix.casefold() != ".flac":
            return {"state": "REVIEW", "reason": "target_not_flac"}
        if inspect is None:
            outcome = decide_duplicate(destination, original)
        else:
            outcome = decide_duplicate(destination, original, inspect=inspect)
        action = outcome["action"]
        if native_overwrite:
            return {"state": "NATIVE_OVERWRITE_RISK",
                    "reason": "picard_overwrite_enabled; no_safe_veto",
                    "advice": action}
        if action == "REPLACE":
            return {"state": "WOULD_REPLACE", "reason": outcome["reason"]}
        if action == "SKIP":
            return {"state": "WOULD_KEEP_EXISTING", "reason": outcome["reason"]}
        return {"state": "REVIEW", "reason": outcome["reason"]}
    except (OSError, ValueError, TypeError, RuntimeError) as error:
        return {"state": "REVIEW", "reason": type(error).__name__}


def capture_native_targets(files, settings, limit=20):
    """GUI thread ONLY: use Picard File.make_filename and actual profile settings."""
    if not isinstance(limit, int) or limit < 1:
        return ()
    try:
        # All options must be resolved from the active Picard profile, not a
        # fabricated default (preset 3 remains unchanged).
        rename = bool(settings["rename_files"])
        move = bool(settings["move_files"])
        overwrite = bool(settings["move_overwrite_existing_files"])
    except (KeyError, TypeError, ValueError):
        return ()
    snapshots = []
    for file in islice(files, limit):
        path = getattr(file, "filename", None)
        metadata = getattr(file, "metadata", None)
        maker = getattr(file, "make_filename", None)
        if not isinstance(path, str) or not path or metadata is None or not callable(maker):
            continue
        if not (rename or move):
            target = path
        else:
            try:
                target = maker(path, metadata, settings)
            except (OSError, ValueError, TypeError, KeyError, RuntimeError):
                continue
        if not isinstance(target, str) or not target:
            continue
        snapshots.append((path, target, overwrite))
    return tuple(snapshots)


def analyze_native_targets(snapshots, *, inspect=None):
    """Background worker; values passed from GUI are immutable paths/options."""
    rows = []
    for source, target, overwrite in snapshots:
        result = inspect_collision(source, target, native_overwrite=overwrite, inspect=inspect)
        rows.append({"source": source, "target": target, **result})
    return rows


_ACTIVE = set()


def show_collision_preview(api, files):
    """Picard File context action; bounded asynchronous audit, never save/move."""
    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QMessageBox

    try:
        snapshots = capture_native_targets(files, api.global_config.setting)
    except (ValueError, TypeError, RuntimeError):
        snapshots = ()
    if not snapshots:
        QMessageBox.warning(None, "PicardWulf – Dateikollisionen",
                            "Kein prüfbarer Dateiname oder Picard-3-Profil verfügbar.")
        return False
    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="PicardWulf-Collision")
    try:
        future = pool.submit(analyze_native_targets, snapshots)
    except RuntimeError:
        pool.shutdown(wait=False)
        QMessageBox.warning(None, "PicardWulf – Dateikollisionen",
                            "Hintergrundprüfung konnte nicht gestartet werden.")
        return False
    timer = QTimer(api.tagger.window)
    timer.setInterval(150)
    token = (timer, pool, future)
    _ACTIVE.add(token)

    def deliver():
        if not future.done():
            return
        timer.stop()
        _ACTIVE.discard(token)
        try:
            result = future.result()
            names = {"SAME_FILE":"Bestehende Quelldatei",
                     "FREE_TARGET":"Ziel frei",
                     "WOULD_REPLACE":"Größere FLAC würde gewinnen",
                     "WOULD_KEEP_EXISTING":"Vorhandene größere/gleiche FLAC behalten",
                     "NATIVE_OVERWRITE_RISK":"GEFAHR: natives Überschreiben aktiv",
                     "REVIEW":"Manuelle Prüfung erforderlich"}
            lines = []
            for row in result:
                src = Path(row["source"]).name
                dst = Path(row["target"]).name
                lines.append(f"{src} → {dst}: {names.get(row['state'], 'Unklar')}")
            QMessageBox.information(None, "PicardWulf – Kollisionsvorschau",
                "Nur Leseprüfung – KEINE Dateien verändert.\n"
                "Picards Speichervorgang wird hier nicht abgefangen.\n\n" +
                "\n".join(lines))
        except Exception as exc:
            api.logger.warning("PicardWulf collision readback: %s", type(exc).__name__)
            QMessageBox.warning(None, "PicardWulf – Kollisionsvorschau",
                                "Analyse nicht verifiziert; keine Änderungen.")
        finally:
            pool.shutdown(wait=False, cancel_futures=False)
    timer.timeout.connect(deliver)
    timer.start()
    return True


def stop_collision_previews():
    """Stop orphan Qt dialogs on plugin disable; worker only performs reads."""
    for timer, pool, future in tuple(_ACTIVE):
        timer.stop()
        pool.shutdown(wait=False, cancel_futures=True)
        _ACTIVE.discard((timer, pool, future))
