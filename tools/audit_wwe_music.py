"""Read-only recovery inventory for WWE/WWF The Music volumes.

Never edits tags, deletes, moves, or deduplicates user media. Run with the
actual library root(s) as explicit arguments; no implicit drive scanning.
Audio metadata is read via installed Mutagen with easy=True. Each returned
path is informational only, and a suggested target is NOT an authorization
to move files.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from collections import defaultdict

from neowulf_picard_repair.wwe_series import route_metadata, wwe_folder, wwe_volume

AUDIO_EXTENSIONS = frozenset({
    ".flac", ".mp3", ".m4a", ".mp4", ".aac", ".ogg", ".opus", ".wma"
})


def read_album_tags(path: Path) -> dict[str, str]:
    try:
        import mutagen
        audio = mutagen.File(str(path), easy=True)
        if not audio:
            return {}
        def value(k):
            raw = audio.get(k, "")
            if isinstance(raw, list):
                return str(raw[0]) if raw else ""
            return str(raw or "")
        return {
            "album": value("album"),
            "artist": value("artist"),
            "albumartist": value("albumartist"),
            "date": value("date") or value("year"),
            "originaldate": value("originaldate") or value("originalyear"),
        }
    except (OSError, ValueError, TypeError, Exception):
        # Some media may be damaged or inaccessible. Never abort a whole
        # read-only recovery search on one unparseable audio file.
        return {}


def scan_library(roots, *, max_audio=250000, sample_limit=20, reader=read_album_tags):
    if not roots:
        raise ValueError("At least one explicit library root is required")
    if max_audio < 1 or sample_limit < 1:
        raise ValueError("Invalid bounded scanner limits")
    summary = defaultdict(lambda: {
        "audio_files": 0,
        "misplaced_candidates": 0,
        "examples": [],
        "albums": set(),
    })
    scanned = 0
    errors = 0
    # Review, never rewrite: albumartist explicitly says Various Artists,
    # yet three or more independently named tracks in one physical release
    # directory share the same performer. This is evidence to INSPECT,
    # not proof that the release credit should be overwritten.
    credit_groups = defaultdict(lambda: {
        "artists": set(), "tracks": 0, "examples": [],
        "album": "", "directory": "",
    })
    for item in roots:
        root = Path(item)
        if root.is_symlink() or not root.is_dir():
            raise ValueError(f"Library root is not a real directory: {root}")
        root = root.resolve(strict=True)
        for folder, dirs, files in os.walk(root, followlinks=False):
            # Don't traverse symlink/junctioned directories.
            dirs[:] = [d for d in dirs if not (Path(folder) / d).is_symlink()]
            for name in files:
                path = Path(folder) / name
                if path.suffix.casefold() not in AUDIO_EXTENSIONS or path.is_symlink():
                    continue
                scanned += 1
                if scanned > max_audio:
                    raise ValueError("Read-only inventory exceeded configured audio-file limit")
                tags = reader(path)
                if not isinstance(tags, dict):
                    errors += 1
                    tags = {}
                title = str(tags.get("album") or "").strip()
                artist = str(tags.get("artist") or "").strip()
                albumartist = str(tags.get("albumartist") or "").strip()
                if (title and artist and albumartist.casefold() in
                        {"various artists", "various", "verschiedene interpreten"}
                        and wwe_volume(title) is None):
                    # Never fuse different releases merely because their
                    # title is the same in different directories.
                    key = (str(path.parent).casefold(), title.casefold())
                    group = credit_groups[key]
                    group["tracks"] += 1
                    group["artists"].add(artist.casefold())
                    group["album"] = title
                    group["directory"] = str(path.parent)
                    if len(group["examples"]) < sample_limit:
                        group["examples"].append(str(path))
                folder_hint = next(
                    (p for p in reversed(path.parent.parts)
                     if wwe_volume(p) is not None), "")
                # Prefer album tags; never assert matches from artist/track alone.
                classified = route_metadata(tags) if title else {}
                route = classified if classified.get("state") == "WWE_SERIES" else None
                if route is None:
                    candidate = wwe_folder(folder_hint, tags.get("date"), tags.get("originaldate"))
                    if candidate:
                        route = {"volume": candidate.volume, "year": candidate.year,
                                 "folder": candidate.relative_folder,
                                 "needs_review": candidate.year_conflict}
                if route is None:
                    continue
                slot = summary[str(route["volume"])]
                slot["audio_files"] += 1
                slot["albums"].add(title or folder_hint)
                # Root-relative path is used to avoid a symlink escape and to
                # detect misplaced volumes without inspecting or changing data.
                relative = path.relative_to(root).as_posix().casefold()
                expected = str(route["folder"]).casefold() + "/"
                misplaced = not relative.startswith(expected)
                if misplaced:
                    slot["misplaced_candidates"] += 1
                if len(slot["examples"]) < sample_limit:
                    slot["examples"].append({
                        "path": str(path),
                        "current_relative_path": str(path.relative_to(root)),
                        "expected_album_folder": str(root / Path(route["folder"])),
                        "source_album": title,
                        "misplaced_candidate": misplaced,
                        "year_requires_review": bool(route.get("needs_review")),
                    })
    review = [{
        "album": group["album"],
        "current_directory": group["directory"],
        "track_count": group["tracks"],
        "artist": next(iter(group["artists"])),
        "sample_paths": group["examples"],
        "action": "CHECK_RELEASE_CREDIT_MANUALLY_NO_AUTOMATIC_RETAG",
    } for group in credit_groups.values()
        if group["tracks"] >= 3 and len(group["artists"]) == 1]
    review.sort(key=lambda entry: (entry["album"].casefold(),
                                  entry["current_directory"].casefold()))
    return {
        "status": "READ_ONLY_NO_MOVES",
        "audio_files_scanned": scanned,
        "unreadable_metadata": errors,
        "potentially_misfiled_artist_compilations": review,
        "by_volume": {
            key: {**value, "albums": sorted(value["albums"])}
            for key, value in sorted(summary.items(), key=lambda x: int(x[0]))
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", type=Path, nargs="+")
    parser.add_argument("--max-audio", type=int, default=250000)
    parser.add_argument("--sample-limit", type=int, default=20)
    args = parser.parse_args()
    result = scan_library(args.roots, max_audio=args.max_audio,
                          sample_limit=args.sample_limit)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
