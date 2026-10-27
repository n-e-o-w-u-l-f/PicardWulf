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

# The command must work on BMAX's standalone Python where PyQt6/Picard
# are NOT importable. Import only this pure helper; package __init__ starts
# Picard plugin dependencies that an offline, read-only audit must not need.
from importlib.util import module_from_spec, spec_from_file_location
import sys

_module_path = Path(__file__).resolve().parents[1] / "neowulf_picard_repair" / "wwe_series.py"
_spec = spec_from_file_location("_picardwulf_wwe_series_inventory", _module_path)
_series = module_from_spec(_spec)
sys.modules[_spec.name] = _series
_spec.loader.exec_module(_series)
route_metadata = _series.route_metadata
wwe_folder = _series.wwe_folder
wwe_folder_hint = _series.wwe_folder_hint
wwe_volume = _series.wwe_volume

AUDIO_EXTENSIONS = frozenset({
    ".flac", ".mp3", ".m4a", ".mp4", ".aac", ".ogg", ".opus", ".wma"
})


def read_album_tags(path: Path) -> dict[str, str]:
    # Missing dependency is a hard error, not a false "zero missing albums"
    # report. On BMAX Python 3.14, mutagen was previously verified present.
    import mutagen
    try:
        audio = mutagen.File(str(path), easy=True)
        if audio is None:
            return None
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
    except Exception:
        # Not a successfully decoded audio tag set. Report failure separately
        # from valid media that merely lacks the ALBUM metadata field.
        return None


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
        "directories": defaultdict(int),
        "conflicting_evidence": 0,
        "folder_only_evidence": 0,
    })
    scanned = 0
    errors = 0
    without_album_tag = 0
    unreadable_examples = []
    traversal_errors = []
    artist_in_va = defaultdict(lambda: {
        "album": "", "albumartist": "", "directory": "",
        "tracks": 0, "examples": [],
    })
    validated_roots = []
    # Review, never rewrite: albumartist explicitly says Various Artists,
    # yet three or more independently named tracks in one physical release
    # directory share the same performer. This is evidence to INSPECT,
    # not proof that the release credit should be overwritten.
    credit_groups = defaultdict(lambda: {
        "artists": set(), "tracks": 0, "examples": [],
        "album": "", "directory": "",
    })
    def redirected(path):
        # Modern Windows Python detects NTFS junctions separately from
        # symbolic links; never traverse reparse points outside user root.
        return path.is_symlink() or (
            hasattr(path, "is_junction") and path.is_junction())

    for item in roots:
        root = Path(item)
        if redirected(root) or not root.is_dir():
            raise ValueError(f"Library root is not a real directory: {root}")
        root = root.resolve(strict=True)
        if any(root == prior or root.is_relative_to(prior) or
               prior.is_relative_to(root) for prior in validated_roots):
            raise ValueError(f"Duplicate or overlapping library roots: {root}")
        validated_roots.append(root)

        def on_walk_error(exc):
            traversal_errors.append(str(exc)[:300])

        for folder, dirs, files in os.walk(
                root, followlinks=False, onerror=on_walk_error):
            # Don't traverse symlink/junctioned directories.
            dirs[:] = [d for d in dirs if not redirected(Path(folder) / d)]
            for name in files:
                path = Path(folder) / name
                if path.suffix.casefold() not in AUDIO_EXTENSIONS or redirected(path):
                    continue
                scanned += 1
                if scanned > max_audio:
                    raise ValueError("Read-only inventory exceeded configured audio-file limit")
                try:
                    tags = reader(path)
                except ImportError:
                    # Missing Mutagen is a fatal setup fault; an empty report
                    # would wrongly suggest the user's library is incomplete.
                    raise
                except Exception:
                    tags = None
                read_ok = isinstance(tags, dict)
                if not read_ok:
                    errors += 1
                    if len(unreadable_examples) < sample_limit:
                        unreadable_examples.append(str(path))
                    tags = {}
                title = str(tags.get("album") or "").strip()
                if not title and read_ok:
                    without_album_tag += 1
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
                rel_parts = path.relative_to(root).parts
                if (title and albumartist and
                        albumartist.casefold() not in
                        {"various artists", "various", "verschiedene interpreten"}
                        and wwe_volume(title) is None and
                        (root.name.casefold() == "various artists" or
                         rel_parts[0].casefold() == "various artists")):
                    # Stronger evidence than track artist: tags explicitly
                    # name a solo/credited album artist in a VA directory.
                    key = (str(path.parent).casefold(), title.casefold(),
                           albumartist.casefold())
                    group = artist_in_va[key]
                    group["album"] = title
                    group["albumartist"] = albumartist
                    group["directory"] = str(path.parent)
                    group["tracks"] += 1
                    if len(group["examples"]) < sample_limit:
                        group["examples"].append(str(path))
                # Folder names, including already-canonical YYYY - Volume N,
                # are only secondary evidence. Never silently override a
                # different WWE volume explicitly tagged in the media.
                hint = next((candidate for namepart in reversed(path.parent.parts)
                             if (candidate := wwe_folder_hint(
                                  namepart, tags.get("date"), tags.get("originaldate")))
                             is not None), None)
                classified = route_metadata(tags) if title else {}
                tags_route = classified if classified.get("state") == "WWE_SERIES" else None
                if tags_route:
                    route = tags_route
                    evidence = "album_tags"
                    conflicting = bool(
                        hint and (hint.volume != tags_route["volume"] or
                                  hint.year != tags_route["year"] or
                                  hint.year_conflict))
                elif hint:
                    route = {"volume": hint.volume, "year": hint.year,
                             "folder": hint.relative_folder,
                             "needs_review": hint.year_conflict}
                    evidence = "folder_only" if not title else "folder_vs_non_wwe_tags"
                    conflicting = bool(title)
                else:
                    continue
                slot = summary[str(route["volume"])]
                slot["audio_files"] += 1
                slot["albums"].add(title or path.parent.name)
                slot["directories"][str(path.parent)] += 1
                if evidence != "album_tags":
                    slot["folder_only_evidence"] += 1
                if conflicting:
                    slot["conflicting_evidence"] += 1
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
                        "evidence": evidence,
                        "tag_folder_conflict": conflicting,
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
    artist_groups = [{
        "album": g["album"], "albumartist": g["albumartist"],
        "current_directory": g["directory"], "track_count": g["tracks"],
        "sample_paths": g["examples"],
        "action": "CHECK_AND_REPAIR_PATH_ONLY_AFTER_RELEASE_VERIFICATION",
    } for g in artist_in_va.values()]
    artist_groups.sort(key=lambda g: (g["albumartist"].casefold(),
                                     g["album"].casefold(), g["current_directory"].casefold()))
    scanned_volumes = sorted(int(k) for k in summary)
    return {
        "status": "READ_ONLY_INCOMPLETE" if errors or traversal_errors
                  else "READ_ONLY_NO_MOVES",
        "audio_files_scanned": scanned,
        "unreadable_metadata": errors,
        "unreadable_examples": unreadable_examples,
        "audio_without_album_tag": without_album_tag,
        "traversal_errors": traversal_errors[:sample_limit],
        "identified_volumes": scanned_volumes,
        "volumes_not_identified": [n for n in range(1, 11) if n not in scanned_volumes],
        "volume_absence_is_not_proven": True,
        "potentially_misfiled_artist_compilations": review,
        "artist_albums_in_various_directories": artist_groups,
        "by_volume": {
            key: {
                **{k: v for k, v in value.items() if k != "directories"},
                "albums": sorted(value["albums"]),
                "observed_directory_count": len(value["directories"]),
                "observed_directories": [
                    {"path": directory, "audio_files": count}
                    for directory, count in sorted(value["directories"].items())
                ][:max(sample_limit, 1)],
            }
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
