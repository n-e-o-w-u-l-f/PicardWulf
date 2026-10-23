"""Strict FLAC-only, zero-discrepancy Picard 3 album UI retirement.

File/album Qt objects are inspected only on the GUI thread. A worker performs
actual on-disk tag readback; the UI is changed only after an unchanged
second Picard eligibility check. NO filesystem write or media deletion here.
"""
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import time


_FIELDS = ("artist", "title", "album", "tracknumber", "discnumber")
_OPTIONAL = ("albumartist", "musicbrainz_albumid", "musicbrainz_recordingid",
             "isrc", "date", "originaldate", "barcode", "genre", "label")


def native_gold_retirement_allowed(api):
    """Disallow plugin UI retirement while Picard native auto-removal is enabled.

    Do not silently change the owner\'s Picard.ini or active naming preset.
    """
    try:
        # A native staged FLAC copy deliberately keeps Picard's File bound
        # to staging. Until canonical-library + Qt acceptance is proven,
        # it must not trigger Gold UI retirement based on the staging copy.
        if api.plugin_config.get("native_move_auto", False):
            return False
        return api.global_config.setting["remove_complete_albums_after_save"] is False
    except (AttributeError, KeyError, TypeError, ValueError):
        return False


def _text(metadata, name):
    getter = getattr(metadata, "get", None)
    if getter is None:
        return ""
    value = getter(name, "")
    if isinstance(value, (list, tuple)):
        value = value[0] if value else ""
    return str(value or "").strip()


def _values(metadata, name):
    # Real Picard Metadata.get() joins multi-valued tags into one string.
    # getall() is the documented source of their individual values.
    getall = getattr(metadata, "getall", None)
    if callable(getall):
        raw = getall(name)
    else:
        getter = getattr(metadata, "get", None)
        if getter is None:
            return ()
        value = getter(name, "")
        raw = value if isinstance(value, (list, tuple)) else (value,)
    return tuple(str(item).strip() for item in raw
                 if item is not None and str(item).strip())


def _same_tag(name, observed, expected):
    """Compare ALL FLAC tag values rather than silently accepting only the first."""
    lhs = observed if isinstance(observed, (list, tuple)) else (observed,)
    rhs = expected if isinstance(expected, (list, tuple)) else (expected,)
    def normal(values):
        cleaned = []
        for value in values:
            text = str(value or "").strip()
            if name in ("tracknumber", "discnumber"):
                text = text.split("/", 1)[0]
            if text:
                cleaned.append(" ".join(text.casefold().split()))
        return tuple(cleaned)
    return normal(lhs) == normal(rhs)


def capture_gold(album, tagger, tracker=None):
    """Snapshot GUI-only objects, fail closed on pending or divergent data."""
    albums = getattr(tagger, "albums", None)
    album_id = getattr(album, "id", None)
    if not isinstance(albums, dict) or not album_id or albums.get(album_id) is not album:
        return None
    if getattr(album, "loaded", None) is not True or getattr(album, "errors", None):
        return None
    try:
        tracks = tuple(album.tracks)
        if (not tracks or len(tracks) > 250
                or not album.is_complete()
                or album.get_num_unmatched_files() != 0
                or album.get_num_unsaved_files() != 0
                or album.get_num_matched_tracks() != len(tracks)
                or any(not track.is_complete() for track in tracks)):
            return None
        files = tuple(album.iterfiles())
        if len(files) != len(tracks):
            return None
        records = []
        unique = set()
        if tracker is not None and tracker.has_inflight():
            return None
        for file in files:
            filename = getattr(file, "filename", None)
            if not isinstance(filename, str) or not filename or Path(filename).suffix.casefold() != ".flac":
                return None
            key = os.path.normcase(os.path.abspath(filename))
            if key in unique:
                return None
            unique.add(key)
            if not file.is_saved() or getattr(file, "errors", None):
                return None
            if tracker is not None and tracker.path_state(filename) not in (None, "VERIFIED"):
                return None
            metadata = getattr(file, "metadata", None)
            original = getattr(file, "orig_metadata", None)
            if metadata is None or original is None or _text(metadata, "~picardwulf_review"):
                return None
            if _text(metadata, "~picardwulf_decision") in ("review", "conflict", "abstain"):
                return None
            values = tuple((key, _values(metadata, key)) for key in _FIELDS + _OPTIONAL
                           if key in _FIELDS or _values(metadata, key)
                           or _values(original, key))
            if any(not val for key, val in values if key in _FIELDS):
                return None
            if any(not _same_tag(key, _values(original, key), val) for key, val in values):
                return None
            records.append((filename, values))
        return album_id, tuple(records)
    except (TypeError, ValueError, AttributeError, RuntimeError):
        return None


def verify_gold_files(snapshot):
    """Worker ONLY. Never create, modify, move, or delete any audio file."""
    album_id, records = snapshot
    try:
        from mutagen import File
        from mutagen.flac import FLAC
        for filename, values in records:
            path = Path(filename)
            if not path.is_file() or path.is_symlink() or path.suffix.casefold() != ".flac":
                return False
            before = path.stat()
            if before.st_size <= 0:
                return False
            audio = File(str(path), easy=True)
            if audio is None or not isinstance(audio, FLAC) or audio.tags is None:
                return False
            if float(getattr(getattr(audio, "info", None), "length", 0) or 0) <= 0:
                return False
            for name, expected in values:
                actual = audio.tags.get(name)
                if actual is None:
                    return False
                if not _same_tag(name, actual, expected):
                    return False
            after = path.stat()
            if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
                    after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
                return False
        return bool(records)
    except (OSError, ValueError, TypeError, ImportError, RuntimeError):
        return False


def start_gold_retirement(api, tracker):
    """Install bounded GUI polling + off-GUI readback on an active Picard 3 UI."""
    from PyQt6.QtCore import QObject, QTimer, Qt, pyqtSignal

    class Controller(QObject):
        finished = pyqtSignal(object)

        def __init__(self):
            super().__init__(api.tagger.window)
            self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="PicardWulf-Gold")
            self._closed = False
            self._pending = None
            self._failures = {}
            self._scan_iter = None
            self._native_warned = False
            self.finished.connect(self._complete, Qt.ConnectionType.QueuedConnection)
            self._timer = QTimer(self)
            self._timer.setInterval(3000)
            self._timer.timeout.connect(self.tick)
            self._timer.start()
            QTimer.singleShot(0, self.tick)

        def tick(self):
            if self._closed:
                return
            if not native_gold_retirement_allowed(api):
                self._scan_iter = None
                if not self._native_warned:
                    api.logger.warning(
                        "PicardWulf gold retirement inactive: Picard native "
                        "remove_complete_albums_after_save must be explicitly OFF.")
                    self._native_warned = True
                return
            self._native_warned = False
            if self._pending is not None or tracker.has_inflight():
                return
            # Never materialize all loaded albums on Qt. Album registry
            # mutations invalidate a dict iterator; safely restart next tick.
            if self._scan_iter is None:
                self._scan_iter = iter(api.tagger.albums.values())
            for _ in range(100):
                try:
                    album = next(self._scan_iter)
                except StopIteration:
                    self._scan_iter = None
                    break
                except RuntimeError:
                    self._scan_iter = None
                    return
                snap = capture_gold(album, api.tagger, tracker)
                if snap is None:
                    continue
                failure = self._failures.get(snap[0])
                if failure is not None and failure[0] == snap and time.monotonic() < failure[1]:
                    continue
                self._pending = (album, snap)
                try:
                    future = self._pool.submit(verify_gold_files, snap)
                    future.add_done_callback(self._deliver)
                except RuntimeError:
                    self._pending = None
                return

        def _deliver(self, future):
            if self._closed:
                return
            try:
                valid = bool(future.result())
                self.finished.emit(valid)
            except (RuntimeError, OSError):
                # QObject might have been destroyed during shutdown.
                return

        def _complete(self, valid):
            pending = self._pending
            self._pending = None
            if self._closed or pending is None:
                return
            album, snapshot = pending
            if not valid:
                self._failures[snapshot[0]] = (snapshot, time.monotonic() + 60)
                if len(self._failures) > 2048:
                    self._failures.pop(next(iter(self._failures)))
                return
            # Re-check on the GUI thread after asynchronous readback. Never
            # interact with File or Album objects in the worker thread.
            if (not native_gold_retirement_allowed(api) or tracker.has_inflight()
                    or capture_gold(album, api.tagger, tracker) != snapshot):
                return
            try:
                # Same Picard UI-removal entry point used by native 3.0 code.
                api.tagger.window.panel.remove([album])
                api.logger.info("PicardWulf: verified gold album removed from UI: %s", snapshot[0])
            except Exception as exc:
                api.logger.warning("PicardWulf gold UI removal failed: %s", type(exc).__name__)

        def stop(self):
            self._closed = True
            self._scan_iter = None
            self._timer.stop()
            self._pool.shutdown(wait=False, cancel_futures=True)

    return Controller()
