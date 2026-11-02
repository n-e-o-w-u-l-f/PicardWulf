"""Fail-closed PicardWulf file-retention primitives for Picard 3.

Not called automatically by the plugin until the BMAX runtime/deletion gate passes.
Only compare genuinely identified audio, never decide solely by a filename.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import uuid


class RetentionRejected(ValueError):
    pass


def _digest(path):
    h = sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _signature(path):
    stat = Path(path).stat()
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns


def _one(tags, key):
    value = tags.get(key, "")
    if isinstance(value, (list, tuple)):
        value = value[0] if value else ""
    return str(value).strip().casefold()


def _identity(tags):
    # Missing track identity is a review case, never a positive duplicate.
    keys = ("artist", "title", "album", "discnumber", "tracknumber")
    values = tuple(_one(tags, key).split("/")[0] if key in ("discnumber", "tracknumber")
                   else _one(tags, key) for key in keys)
    if not all(values):
        return None
    return values


def inspect_audio(path):
    """Inspect actual format + tags; the filename extension is not proof."""
    path = Path(path)
    if not path.is_file() or path.is_symlink():
        raise RetentionRejected("Audio file missing or symbolic link")
    from mutagen import File
    from mutagen.flac import FLAC
    from mutagen.mp3 import MP3
    audio = File(str(path), easy=True)
    expected = {".flac": FLAC, ".mp3": MP3}.get(path.suffix.casefold())
    if expected is None or not isinstance(audio, expected):
        raise RetentionRejected("Unsupported extension or inconsistent audio format")
    info = getattr(audio, "info", None)
    seconds = float(getattr(info, "length", 0) or 0)
    if seconds <= 0:
        raise RetentionRejected("Invalid or missing audio duration")
    identity = _identity(audio)
    if identity is None:
        raise RetentionRejected("Incomplete tags; cannot verify track identity")
    # If a provider/edition identifier is present, a missing or conflicting
    # identifier in the counterpart is NOT positive evidence of identity.
    evidence_keys = ("musicbrainz_recordingid", "musicbrainz_albumid", "isrc",
                     "barcode", "date", "albumartist", "releasestatus")
    evidence = tuple((key, _one(audio, key)) for key in evidence_keys)
    return {"path": path, "extension": path.suffix.casefold(),
            "size": path.stat().st_size, "identity": identity, "seconds": seconds,
            "evidence": evidence}


def _match(left, right):
    if not (left["identity"] == right["identity"] and
            abs(left["seconds"] - right["seconds"]) <= 1.5):
        return False
    left_evidence = dict(left.get("evidence") or ())
    right_evidence = dict(right.get("evidence") or ())
    # Do not merge different editions/recordings when an explicit source tag
    # supplies identity evidence on either side. Unmatched fields fail closed.
    for key in left_evidence.keys() | right_evidence.keys():
        old = str(left_evidence.get(key, "") or "")
        new = str(right_evidence.get(key, "") or "")
        if (old or new) and old != new:
            return False
    return True


def decide_duplicate(existing, incoming, *, inspect=inspect_audio):
    """REPLACE only for a verified larger FLAC with identical track identity."""
    a, b = Path(existing), Path(incoming)
    if a.resolve() == b.resolve():
        return {"action": "SKIP", "reason": "same_path"}
    if a.suffix.casefold() != ".flac" or b.suffix.casefold() != ".flac":
        return {"action": "REVIEW", "reason": "requires_two_flac_files"}
    try:
        x, y = inspect(a), inspect(b)
    except (OSError, ValueError, ImportError) as exc:
        return {"action": "REVIEW", "reason": type(exc).__name__}
    if x["extension"] != ".flac" or y["extension"] != ".flac" or not _match(x, y):
        return {"action": "REVIEW", "reason": "unverified_audio_identity"}
    if y["size"] > x["size"]:
        return {"action": "REPLACE", "reason": "verified_larger_flac"}
    return {"action": "SKIP", "reason": "existing_equal_or_larger"}


def _flac_decode_ok(path):
    """Require full FLAC stream verification before permanent MP3 deletion."""
    exe = shutil.which("flac")
    if not exe:
        return False
    try:
        result = subprocess.run([exe, "-t", "--silent", "--", str(path)],
                                capture_output=True, timeout=180, check=False)
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def decide_mp3_removal(mp3_path, flac_path, *, inspect=inspect_audio, decode=_flac_decode_ok):
    """Only same-folder, same-stem verified replacements qualify for removal."""
    mp3, flac = Path(mp3_path), Path(flac_path)
    if (mp3.suffix.casefold() != ".mp3" or flac.suffix.casefold() != ".flac"
            or mp3.parent.resolve() != flac.parent.resolve()
            or mp3.stem.casefold() != flac.stem.casefold()):
        return {"action": "REVIEW", "reason": "unpaired_file"}
    try:
        a, b = inspect(mp3), inspect(flac)
    except (OSError, ValueError, ImportError) as exc:
        return {"action": "REVIEW", "reason": type(exc).__name__}
    if a["extension"] != ".mp3" or b["extension"] != ".flac" or not _match(a, b):
        return {"action": "REVIEW", "reason": "unverified_audio_identity"}
    if not decode(flac):
        return {"action": "REVIEW", "reason": "flac_decode_not_verified"}
    return {"action": "REMOVE", "reason": "verified_flac_counterpart"}


def require_native_tag_only(settings):
    """Fail closed before PicardWulf-initiated native File.save().

    Picard 3 saves tags and then performs its private native _rename(), which
    cannot be vetoed from a public file-pre-save plugin processor. Avoid any
    automated native rename/move until collision arbitration can be integrated
    with Picard's supported lifecycle. Normal Picard Ctrl+S remains outside
    this plugin guard.
    """
    try:
        if settings["rename_files"] is not False or settings["move_files"] is not False:
            raise RetentionRejected(
                "PicardWulf save requires tag-only Picard options: "
                "disable native rename/move for this operation; use verified "
                "staging import for destination transfers.")
    except (KeyError, TypeError, AttributeError) as exc:
        raise RetentionRejected(
            "Picard active rename/move settings unavailable; refusing save") from exc
    return True


def replace_smaller_flac(existing, incoming, backup_dir, *,
                         inspect=inspect_audio, decode=None,
                         expected_existing_sha256=None,
                         expected_incoming_sha256=None):
    """Atomic replacement, independent retained backup, rechecked bytes/identity.

    Only for files already mapped by Picard to the same *verified* recording.
    The incoming file is kept until the caller separately handles its lifecycle.
    """
    old, new, root = Path(existing), Path(incoming), Path(backup_dir)
    decision = decide_duplicate(old, new, inspect=inspect)
    if decision["action"] != "REPLACE":
        return decision
    before_old, before_new = _signature(old), _signature(new)
    original_digest = _digest(old)
    incoming_digest = _digest(new)
    # Reject changes between the Picard GUI's reviewed dry-run and the
    # actual replacement; never apply a confirmation to different bytes.
    if ((expected_existing_sha256 is not None
         and original_digest != expected_existing_sha256)
        or (expected_incoming_sha256 is not None
            and incoming_digest != expected_incoming_sha256)):
        raise RetentionRejected("Canonical FLAC or source changed after preview")
    if old.is_symlink() or new.is_symlink():
        raise RetentionRejected("Symbolic link not permitted")
    root.mkdir(parents=True, exist_ok=True)
    if root.resolve() == old.parent.resolve():
        raise RetentionRejected("Backup must be outside destination directory")
    backup = root / (uuid.uuid4().hex + "-" + old.name)
    stage = None
    try:
        with old.open("rb") as src, backup.open("xb") as dst:
            shutil.copyfileobj(src, dst, length=1024 * 1024)
            dst.flush()
            os.fsync(dst.fileno())
        if (_digest(backup) != original_digest or
                _digest(old) != original_digest):
            raise RetentionRejected("Existing-file backup mismatch")
        fd, name = tempfile.mkstemp(prefix=".picardwulf-", suffix=".flac",
                                   dir=str(old.parent))
        stage = Path(name)
        with os.fdopen(fd, "wb") as dst, new.open("rb") as src:
            shutil.copyfileobj(src, dst, length=1024 * 1024)
            dst.flush()
            os.fsync(dst.fileno())
        if (_digest(stage) != incoming_digest or
                _digest(new) != incoming_digest):
            raise RetentionRejected("Incoming file copy mismatch")
        if _signature(old) != before_old or _signature(new) != before_new:
            raise RetentionRejected("Audio changed during replacement")
        if decide_duplicate(old, stage, inspect=inspect)["action"] != "REPLACE":
            raise RetentionRejected("Staged file identity mismatch")
        os.replace(stage, old)
        stage = None
        try:
            committed = (_digest(old) == incoming_digest
                         and _digest(new) == incoming_digest)
            # The staged importer supplies the complete FLAC decoder here.
            # Decode must be part of the transaction: checking only AFTER
            # this function returned would skip its automatic rollback.
            if committed and decode is not None:
                committed = bool(decode(old))
        except (OSError, ValueError, RuntimeError):
            committed = False
        if not committed:
            # After native os.replace the former destination no longer exists
            # at its path. A backup receipt alone is not rollback. Materialize
            # the verified backup beside the destination, then atomically
            # restore it. Never consume/rename/delete the recovery copy.
            restore = None
            try:
                fd, restore_name = tempfile.mkstemp(
                    prefix=".picardwulf-restore-", suffix=".flac",
                    dir=str(old.parent))
                restore = Path(restore_name)
                with os.fdopen(fd, "wb") as out, backup.open("rb") as src:
                    shutil.copyfileobj(src, out, length=1024 * 1024)
                    out.flush()
                    os.fsync(out.fileno())
                if (_digest(backup) != original_digest
                        or _digest(restore) != original_digest):
                    raise RetentionRejected("Rollback source hash mismatch")
                os.replace(restore, old)
                restore = None
                if _digest(old) != original_digest:
                    raise RetentionRejected("Rollback destination hash mismatch")
            except Exception as error:
                raise RetentionRejected(
                    "Replacement integrity failed; automatic rollback unverified; "
                    "independent backup preserved") from error
            finally:
                if restore is not None:
                    restore.unlink(missing_ok=True)
            raise RetentionRejected(
                "Replacement integrity failed; original restored from backup")
        return {"action": "REPLACED", "backup": str(backup), "destination": str(old)}
    finally:
        if stage is not None:
            stage.unlink(missing_ok=True)


def remove_verified_mp3(mp3, flac, backup_receipt=None, *,
                        inspect=inspect_audio, decode=_flac_decode_ok):
    """Permanent unlink only with a verified independent recovery copy."""
    mp3 = Path(mp3)
    status = decide_mp3_removal(mp3, flac, inspect=inspect, decode=decode)
    if status["action"] != "REMOVE":
        return status
    if not isinstance(backup_receipt, dict):
        raise RetentionRejected("Verified independent MP3 backup receipt required")
    backup = Path(str(backup_receipt.get("backup", "")))
    if (backup_receipt.get("path") != str(mp3) or
            not backup.is_file() or backup.is_symlink() or
            backup.resolve() == mp3.resolve()):
        raise RetentionRejected("Unsafe or missing MP3 recovery backup")
    before = _signature(mp3)
    old_hash = _digest(mp3)
    if (old_hash != backup_receipt.get("sha256") or
            old_hash != _digest(backup) or _signature(mp3) != before or
            _digest(mp3) != old_hash):
        raise RetentionRejected("MP3 or recovery copy changed during verification")
    mp3.unlink()
    return {"action": "REMOVED", "reason": "verified_flac_counterpart",
            "removed_sha256": old_hash, "backup": str(backup)}
