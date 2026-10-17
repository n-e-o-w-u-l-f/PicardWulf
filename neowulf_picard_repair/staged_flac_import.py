"""Offline, fail-closed import of staged FLAC into a canonical music library.

This module deliberately DOES NOT hook or cancel Picard File.save() / _rename().
Import from an independent staging directory after files are fully tagged.
Source files are NEVER deleted, renamed or moved by this module.

No automatic Picard UI tracking changes; do not run against open Picard-managed
files or a live library until the Windows staged-file/locking gate has passed.
"""
from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
import os
from pathlib import Path
import shutil
import tempfile

from .retention_policy import (
    RetentionRejected,
    _digest,
    _flac_decode_ok,
    _signature,
    decide_duplicate,
    inspect_audio,
    replace_smaller_flac,
)


class StagedImportRejected(RetentionRejected):
    pass


def _within(path, root):
    try:
        return path.relative_to(root) != Path(".")
    except ValueError:
        return False


def _checked_path(path, root, *, must_exist):
    """Validate lexically AND canonically below root; refuse any symlink component."""
    root = Path(os.path.abspath(root))
    path = Path(os.path.abspath(path))
    if not root.is_dir() or root.is_symlink() or not _within(path, root):
        raise StagedImportRejected("Missing root, root symlink, or path outside root")
    relative = path.relative_to(root)
    probe = root
    for part in relative.parts:
        probe = probe / part
        if probe.is_symlink():
            raise StagedImportRejected("Symlink component is not permitted")
    if not _within(path.resolve(strict=False), root.resolve(strict=True)):
        raise StagedImportRejected("Path leaves its trusted root")
    if must_exist:
        if not path.is_file() or path.is_symlink():
            raise StagedImportRejected("Source FLAC missing or not regular")
    elif path.exists() and not path.is_file():
        raise StagedImportRejected("Existing destination is not regular")
    if path.suffix.casefold() != ".flac":
        raise StagedImportRejected("Only actual .flac file paths are allowed")
    return path


def _roots(staging_root, library_root, recovery_root):
    roots = tuple(Path(os.path.abspath(p)) for p in
                  (staging_root, library_root, recovery_root))
    for root in roots:
        if not root.is_dir() or root.is_symlink():
            raise StagedImportRejected("All three root directories must already exist")
    for i, root in enumerate(roots):
        for other in roots[i + 1:]:
            if (root == other or _within(root.resolve(), other.resolve())
                    or _within(other.resolve(), root.resolve())):
                raise StagedImportRejected("Staging, library, and recovery roots must not overlap")
    return roots


@contextmanager
def _target_lock(recovery_root, target):
    """Cross-process exclusive marker. Stale crash locks fail closed, never stolen."""
    key = sha256(str(target).casefold().encode("utf-8")).hexdigest()
    marker = Path(recovery_root) / ("picardwulf-" + key + ".lock")
    try:
        with marker.open("xb") as lock:
            lock.write(b"PicardWulf staged import in progress\n")
            lock.flush()
            os.fsync(lock.fileno())
            own_lock = os.fstat(lock.fileno())
    except FileExistsError:
        raise StagedImportRejected("Target import already locked; review stale lock manually") from None
    try:
        yield
    finally:
        try:
            current = marker.lstat()
            if (current.st_dev, current.st_ino) == (own_lock.st_dev, own_lock.st_ino):
                marker.unlink()
        except FileNotFoundError:
            pass


def _valid_flac(path, inspect, decode):
    try:
        details = inspect(path)
        if (details.get("extension") != ".flac"
                or not isinstance(details.get("identity"), tuple)
                or not all(details["identity"])
                or details.get("size", 0) <= 0
                or details.get("seconds", 0) <= 0):
            raise StagedImportRejected("Incomplete FLAC identity and duration")
        if not decode(path):
            raise StagedImportRejected("FLAC full-stream decoding failed")
        return details
    except StagedImportRejected:
        raise
    except (OSError, ValueError, ImportError, AttributeError, TypeError) as exc:
        raise StagedImportRejected("FLAC validation unavailable: " + type(exc).__name__) from exc


def _create_target_parents(library, target):
    """Create missing subdirectories only below verified library root.

    On failure clean up only directories created by this call, if still empty.
    Never remove an existing parent or follow a known symlink/junction.
    """
    created = []
    current = Path(library)
    try:
        for part in target.relative_to(library).parts[:-1]:
            current = current / part
            _checked_path(current / "future.flac", library, must_exist=False)
            if not current.exists():
                try:
                    current.mkdir()
                except FileExistsError:
                    pass
                else:
                    created.append(current)
            if (not current.is_dir() or current.is_symlink()
                    or not _within(current.resolve(strict=True), library.resolve(strict=True))):
                raise StagedImportRejected("Destination directory unsafe or redirected")
        return tuple(created)
    except Exception:
        for directory in reversed(created):
            try:
                directory.rmdir()
            except OSError:
                pass
        raise


def _install_new_exclusively(source, target, *, inspect, decode):
    """No overwrite even under concurrent unrelated file creation.

    The same-directory hard link installs the fully fsynced stage atomically.
    Source remains untouched, and an unknown FileExistsError is review-only.
    """
    start = _signature(source)
    digest = _digest(source)
    temporary = None
    try:
        fd, filename = tempfile.mkstemp(
            prefix=".picardwulf-staged-", suffix=".flac", dir=str(target.parent))
        temporary = Path(filename)
        with os.fdopen(fd, "wb") as output, source.open("rb") as incoming:
            shutil.copyfileobj(incoming, output, length=1024 * 1024)
            output.flush()
            os.fsync(output.fileno())
        if (_signature(source) != start or _digest(source) != digest
                or _digest(temporary) != digest):
            raise StagedImportRejected("Source changed while staging; nothing installed")
        _valid_flac(temporary, inspect, decode)
        if target.exists() or target.is_symlink():
            raise StagedImportRejected("Destination appeared during staging; not overwritten")
        try:
            os.link(temporary, target, follow_symlinks=False)
        except FileExistsError:
            raise StagedImportRejected("Concurrent destination appeared; not overwritten") from None
        except OSError as exc:
            raise StagedImportRejected(
                "Atomic no-overwrite hard-link unsupported: " + type(exc).__name__) from exc
        return {"action": "CREATED", "destination": str(target),
                "sha256": digest, "source_preserved": str(source)}
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def import_staged_flac(source, destination, *,
                       staging_root, library_root, recovery_root,
                       apply=False, inspect=inspect_audio, decode=_flac_decode_ok):
    """Dry-run by default; apply must be explicitly True.

    REPLACED: canonical FLAC replaced with a verified larger incoming copy,
    and original retained in the independent recovery root.
    SKIPPED: canonical equal/larger was untouched. The incoming original is
    retained in staging, never silently deleted.
    CREATED: absent destination installed exclusively; staging original kept.
    REVIEW: neither original nor canonical changed on unresolved identity.
    """
    staging, library, recovery = _roots(staging_root, library_root, recovery_root)
    original = _checked_path(source, staging, must_exist=True)
    target = _checked_path(destination, library, must_exist=False)
    if original.resolve() == target.resolve():
        raise StagedImportRejected("Source and destination cannot be the same")
    if target.exists() and os.path.samefile(original, target):
        raise StagedImportRejected("Source and destination refer to the same inode")
    _valid_flac(original, inspect, decode)

    with _target_lock(recovery, target) if apply else _null_lock():
        created_folders = ()
        try:
            if apply:
                created_folders = _create_target_parents(library, target)
            target = _checked_path(target, library, must_exist=False)
            if target.exists():
                _valid_flac(target, inspect, decode)
                decision = decide_duplicate(target, original, inspect=inspect)
                if decision["action"] == "REVIEW":
                    return {"action": "REVIEW", "reason": decision["reason"]}
                action = ("REPLACE" if decision["action"] == "REPLACE"
                          else "SKIP")
            else:
                action = "CREATE"
            if not apply:
                return {"action": "WOULD_" + action, "source_preserved": str(original)}
            if action == "SKIP":
                return {"action": "SKIPPED", "destination": str(target),
                        "source_preserved": str(original)}
            if action == "CREATE":
                return _install_new_exclusively(original, target,
                                                inspect=inspect, decode=decode)
            # Full decoder validation belongs INSIDE the replacement
            # transaction so a failing post-commit stream restores the prior
            # canonical FLAC rather than merely leaving a backup behind.
            try:
                result = replace_smaller_flac(target, original, recovery,
                                              inspect=inspect, decode=decode)
            except RetentionRejected as exc:
                # Give the calling Picard action one documented failure class
                # while preserving the root cause and independent backup.
                raise StagedImportRejected(str(exc)) from exc
            if result.get("action") != "REPLACED":
                raise StagedImportRejected("Collision changed before replacement")
            return dict(result, source_preserved=str(original))

        except Exception:
            for directory in reversed(created_folders):
                try:
                    directory.rmdir()
                except OSError:
                    pass
            raise

@contextmanager
def _null_lock():
    yield
