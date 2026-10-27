"""A supported Picard 3 *file context action* for safe, opt-in FLAC import.

It never intercepts Picard's native File.save(), patches a private Picard method,
or changes the active Picard naming preset. It operates on an ALREADY-SAVED
staging file after explicit user confirmation, then reports the result.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .staged_flac_import import import_staged_flac, StagedImportRejected


class SafeImportUnavailable(ValueError):
    pass


def capture_safe_import(file, settings, recovery_dir, tracker=None):
    """Only call on the Picard GUI thread; never share File/Metadata across workers."""
    if tracker is not None and tracker.has_inflight():
        raise SafeImportUnavailable("PicardWulf save verification still pending")
    if not bool(getattr(file, "is_saved", lambda: False)()):
        raise SafeImportUnavailable("Tags must be saved in staging before import")
    if getattr(file, "errors", None):
        raise SafeImportUnavailable("Picard reported file errors")
    source = getattr(file, "filename", None)
    metadata = getattr(file, "metadata", None)
    maker = getattr(file, "make_filename", None)
    if not isinstance(source, str) or not source or metadata is None or not callable(maker):
        raise SafeImportUnavailable("Picard File and active Metadata required")
    if Path(source).suffix.casefold() != ".flac":
        raise SafeImportUnavailable("Only staged FLAC can be imported")
    try:
        enabled = settings["move_files"] is True
        base = settings["move_files_to"]
        overwrite = settings["move_overwrite_existing_files"] is True
        if not enabled or overwrite:
            raise SafeImportUnavailable("Picard must have move enabled and native overwrite OFF")
        library_root = Path(base)
        if not library_root.is_absolute():
            raise SafeImportUnavailable("Configured Picard library root must be absolute")
        destination = maker(source, metadata, settings)
    except (TypeError, KeyError, AttributeError, RuntimeError) as exc:
        raise SafeImportUnavailable("Cannot resolve active Picard naming profile") from exc
    if not isinstance(destination, str) or not destination:
        raise SafeImportUnavailable("Picard did not produce a destination")
    target = Path(destination)
    if target.suffix.casefold() != ".flac":
        raise SafeImportUnavailable("Native naming must produce FLAC")
    # Require separation from the canonical library and recovery. The
    # importer re-checks all paths including symlinks at apply-time.
    if not Path(recovery_dir).is_dir():
        raise SafeImportUnavailable("Select an existing recovery folder")
    if not library_root.is_dir():
        raise SafeImportUnavailable("Configured library root does not exist")
    if not target.is_relative_to(library_root):
        raise SafeImportUnavailable("Picard destination is outside configured library root")
    if target == Path(source):
        raise SafeImportUnavailable("Source is already the target")
    # Classification is based on RELEASE metadata, not a single track's
    # performer or the compilation bit. A fully evidenced 4-way destination
    # overrides only the album DIRECTORY of this explicitly confirmed safe
    # import; retain the filename made by the user's current Preset 3.
    # Ambiguous/incomplete releases keep native Picard behavior. This does
    # not modify a Picard setting or touch data during preview.
    from .album_routing import route_album
    getter = getattr(metadata, 'get', None)
    if callable(getter):
        snapshot = {key: getter(key, '') for key in (
            'album', 'albumartist', 'artist', 'originaldate', 'date',
            'event_date', 'set_date', 'releasetype', '_secondaryreleasetype',
            'sampler_collection', 'sampler_volume', 'is_liveset', 'set_type')}
        getall = getattr(metadata, 'getall', None)
        if callable(getall):
            snapshot['albumartists'] = (getall('albumartists') or
                                        getall('_albumartists'))
        else:
            snapshot['albumartists'] = getter('albumartists', ())
        decision = route_album(snapshot)
        if decision.folder and not decision.review:
            target = library_root.joinpath(
                *decision.folder.split('/'), target.name)
    # The offline importer creates missing album/series subfolders only after
    # explicit confirmation, then rolls back empty created folders on error.
    return {
        "source": str(Path(source)),
        "destination": str(target),
        "staging_root": str(Path(source).parent),
        "library_root": str(library_root),
        "recovery_root": str(Path(recovery_dir)),
    }


_ACTIVE = {}


def stop_safe_imports():
    """Cancel unstarted jobs and suppress callbacks when the plugin unloads."""
    for key, session in tuple(_ACTIVE.items()):
        session["timer"].stop()
        session["pool"].shutdown(wait=False, cancel_futures=True)
        _ACTIVE.pop(key, None)


def show_safe_import(api, selected_files, tracker=None):
    """User explicitly opts into one saved FLAC's collision-checked import."""
    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QFileDialog, QMessageBox

    chosen = tuple(selected_files)
    if len(chosen) != 1:
        QMessageBox.warning(None, "PicardWulf – Sicherer FLAC-Import",
                            "Bitte exakt eine fertig getaggte FLAC-Datei wählen.")
        return False
    file = chosen[0]
    backup_root = QFileDialog.getExistingDirectory(
        api.tagger.window, "Separaten Wiederherstellungsordner wählen")
    if not backup_root:
        return False
    try:
        params = capture_safe_import(file, api.global_config.setting, backup_root, tracker)
    except SafeImportUnavailable as exc:
        QMessageBox.warning(None, "PicardWulf – Sicherer FLAC-Import", str(exc))
        return False

    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="PicardWulf-SafeImport")
    timer = QTimer(api.tagger.window)
    timer.setInterval(150)
    session = {"timer": timer, "pool": pool, "future": None, "phase": "preview",
               "file": file, "params": params, "api": api}
    # dicts cannot be set members. Keep a plain id -> session registry.
    key = object()
    _ACTIVE[key] = session

    def close():
        timer.stop()
        _ACTIVE.pop(key, None)
        pool.shutdown(wait=False, cancel_futures=True)

    def deliver():
        fut = session["future"]
        if fut is None or not fut.done():
            return
        # QMessageBox.question() runs a nested Qt event loop. Stop the timer
        # before it opens so reentrant delivery cannot confirm twice.
        timer.stop()
        try:
            outcome = fut.result()
            if session["phase"] == "preview":
                plan = outcome.get("action", "REVIEW")
                if plan not in ("WOULD_REPLACE", "WOULD_SKIP", "WOULD_CREATE"):
                    QMessageBox.warning(None, "PicardWulf – Sicherer FLAC-Import",
                        "Unklare Aufnahme oder FLAC-Datei. Import verweigert.")
                    close()
                    return
                # Recheck Picard File/profile snapshot immediately before
                # applying; the worker itself repeats actual disk validation.
                if capture_safe_import(file, api.global_config.setting, backup_root, tracker) != params:
                    QMessageBox.warning(None, "PicardWulf – Sicherer FLAC-Import",
                                        "Quelle oder Profil haben sich verändert.")
                    close()
                    return
                question = (
                    f"Prüfergebnis: {plan}\n\n"
                    f"Quelle: {params['source']}\n"
                    f"Ziel: {params['destination']}\n"
                    f"Backup-Ordner: {backup_root}\n\n"
                    "Bei Ersetzung wird die ursprüngliche Ziel-FLAC gesichert. "
                    "Die Eingangsdatei bleibt erhalten. Dies ist nicht Picards "
                    "nativer Speichern-Befehl. Jetzt explizit übernehmen?")
                if QMessageBox.question(
                    None, "PicardWulf – Import bestätigen", question,
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
                    close()
                    return
                session["phase"] = "apply"
                # Bind this confirmation to the exact bytes and collision
                # decision the user was shown, not merely to a filename.
                session["future"] = pool.submit(
                    import_staged_flac, **params, apply=True,
                    expected_preview=outcome)
                timer.start()
                return
            QMessageBox.information(
                None, "PicardWulf – Import abgeschlossen",
                f"Ergebnis: {outcome.get('action', 'REVIEW')}\n"
                f"Ziel: {params['destination']}\n"
                "Die Eingangsdatei bleibt in Picard geladen und auf der Festplatte "
                "vorhanden. Die Zielbibliothek gegebenenfalls neu laden.")
            close()
        except Exception as exc:
            api.logger.warning("PicardWulf safe import failed: %s", type(exc).__name__)
            QMessageBox.warning(None, "PicardWulf – Import nicht verifiziert",
                f"Import nicht bestätigt: {type(exc).__name__}. "
                "Bestehende Backups und Dateien nicht manuell löschen.")
            close()

    timer.timeout.connect(deliver)
    try:
        session["future"] = pool.submit(import_staged_flac, **params, apply=False)
        timer.start()
        return True
    except Exception:
        close()
        raise
