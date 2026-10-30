"""Native Picard 3.0.2 collision coordinator -- worker-thread-only adapter.

This module does NOT intercept Picard's File.save() by itself. Its contract
is consumed only by a *separately patched and tested* upstream Picard core,
which must provide a public file-move-collision processor registration API.

The caller must pass plain filesystem paths and a frozen native settings
snapshot; do not pass Picard File/Tagger/Qt objects into this worker callback.
"""
from __future__ import annotations

from pathlib import Path

from .retention_policy import _digest
from .staged_flac_import import (
    StagedImportRejected,
    import_staged_flac,
)


def arbitrate_native_flac_move(
    source, destination, settings, recovery_root,
    *, destination_loaded=False, import_fn=import_staged_flac,
):
    """Return a validated native core outcome (never a generic overwrite flag).

    UNHANDLED: not a managed FLAC/independent-library move; Picard can apply
               its original behavior, which must retain its own safeguards.
    KEEP:      source stays loaded at its original name. Target untouched.
    COMMITTED: target has the byte-identical verified FLAC; source remains.
               The core may rebind the File to destination ONLY when it has
               proved that no other File already owns the target.
    """
    src, dst = Path(source), Path(destination)
    if src.suffix.casefold() != ".flac" or dst.suffix.casefold() != ".flac":
        return {"action": "UNHANDLED"}

    # Native overwrite bypasses arbitration on other code paths. Only opt in
    # with Picard native overwrite OFF and a fixed absolute library root.
    try:
        if (settings["move_files"] is not True
                or settings["move_overwrite_existing_files"] is not False):
            return {"action": "KEEP", "reason": "unsupported_native_move_settings"}
        root = Path(settings["move_files_to"])
        if not root.is_absolute() or not root.is_dir():
            return {"action": "KEEP", "reason": "library_root_unverified"}
        if (src == dst or dst.is_relative_to(src.parent)
                or not dst.is_relative_to(root)):
            return {"action": "KEEP", "reason": "invalid_native_target"}
        if destination_loaded:
            return {"action": "KEEP", "reason": "target_owned_by_loaded_file"}
        recovery = Path(recovery_root)
        if not recovery.is_absolute() or not recovery.is_dir():
            return {"action": "KEEP", "reason": "independent_recovery_unavailable"}
    except (KeyError, TypeError, ValueError, OSError):
        return {"action": "KEEP", "reason": "native_profile_not_verified"}

    try:
        # The imported operation locks the destination, validates both streams,
        # uses atomic copy/replace, and retains a separate SHA-256 backup.
        out = import_fn(
            str(src), str(dst),
            staging_root=str(src.parent),
            library_root=str(root),
            recovery_root=str(recovery),
            apply=True,
        )
    except StagedImportRejected:
        # A failed post-commit rollback may leave the destination requiring
        # human recovery. Do NOT mask as a successful Picard save.
        raise
    if out.get("action") in ("REVIEW", "SKIPPED"):
        return {"action": "KEEP", "reason": out.get("reason", out["action"])}
    if out.get("action") not in ("CREATED", "REPLACED"):
        raise StagedImportRejected("Unexpected native collision result")

    if (not src.is_file() or not dst.is_file()
            or _digest(src) != _digest(dst)):
        raise StagedImportRejected("Committed native destination not independently verified")
    return {
        "action": "COMMITTED",
        "destination": str(dst),
        "source_preserved": str(src),
        "backup": out.get("backup"),
        "sha256": _digest(dst),
    }
