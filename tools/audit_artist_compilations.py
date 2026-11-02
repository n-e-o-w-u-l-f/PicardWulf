"""Read-only audit of scattered Frank Zander, Die Sekte and WWE multi-CD files.

Requires explicit library root(s), Python + Mutagen. Prints JSON; never
changes, moves, deletes, retags, or hashes personal music. 'Not found' only
means 'not identified inside scanned roots', not that files were lost.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
import importlib
import json
import os
from pathlib import Path
import re
import sys
import types

_ROOT = Path(__file__).resolve().parents[1] / "neowulf_picard_repair"
_NAME = "_picardwulf_readonly_artist_audit"
_PKG = types.ModuleType(_NAME)
_PKG.__path__ = [str(_ROOT)]
sys.modules.setdefault(_NAME, _PKG)
_policy = importlib.import_module(_NAME + ".release_scope")
_wwe = importlib.import_module(_NAME + ".wwe_series")
_EXT = frozenset({".flac", ".mp3", ".m4a", ".mp4", ".ogg", ".opus", ".wma"})


def read_tags(path: Path):
    import mutagen
    try:
        audio = mutagen.File(str(path), easy=True)
        if audio is None:
            return None
        def tag(name):
            value = audio.get(name, "")
            if isinstance(value, (list, tuple)):
                return str(value[0]) if value else ""
            return str(value or "")
        return {name: tag(name) for name in (
            "album", "albumartist", "artist", "date", "originaldate",
            "discnumber", "totaldiscs", "musicbrainz_albumid",
            "musicbrainz_releasegroupid", "barcode")}
    except Exception:
        return None


def _redirect(path: Path):
    return path.is_symlink() or (
        hasattr(path, "is_junction") and path.is_junction())


def audit_library(roots, *, read=read_tags, max_audio=250000, examples=12):
    if not roots or max_audio < 1 or examples < 1:
        raise ValueError("Real library root, positive file and example limits required")
    mapped=[]
    for item in roots:
        root=Path(item)
        if _redirect(root) or not root.is_dir():
            raise ValueError(f"Invalid or redirected library directory: {root}")
        root=root.resolve(strict=True)
        if any(root==other or root.is_relative_to(other) or
               other.is_relative_to(root) for other in mapped):
            raise ValueError(f"Overlapping library roots: {root}")
        mapped.append(root)
    result=defaultdict(lambda: {
        "target":"","kind":"","tracks":0,"observed_albums":set(),
        "observed_albumartists":set(),"observed_release_ids":set(),
        "disc_numbers":set(),"observed_directories":set(),
        "source_examples":[],"review":False,"reasons":set()})
    scanned=0
    unreadable=0
    errors=[]
    for root in mapped:
        for folder,dirs,files in os.walk(
                root, followlinks=False, onerror=lambda exc:errors.append(str(exc)[:300])):
            dirs[:]=[name for name in dirs if not _redirect(Path(folder)/name)]
            for name in files:
                path=Path(folder)/name
                if path.suffix.casefold() not in _EXT or _redirect(path):
                    continue
                scanned+=1
                if scanned>max_audio:
                    raise ValueError("Configured maximum number of audio files exceeded")
                try:
                    tags=read(path)
                except ImportError:
                    raise
                except Exception:
                    tags=None
                if not isinstance(tags,dict):
                    unreadable+=1
                    continue
                year=""
                for field in ("originaldate","date"):
                    m=re.match(r"^((?:19|20)\d{2})",str(tags.get(field) or ""))
                    if m:
                        year=m.group(1)
                        break
                scope=_policy.release_artist_scope(tags,year)
                if scope is not None:
                    target=scope.folder
                    kind=scope.kind
                    review=scope.review
                    reason=scope.reason
                else:
                    wwe=_wwe.wwe_folder(
                        tags.get("album"), tags.get("date"), tags.get("originaldate"))
                    if wwe is None:
                        continue
                    target=wwe.relative_folder
                    kind="WWE_MUSIC"
                    review=wwe.year_conflict
                    reason="wwe_series"
                if not target:
                    # Review-required Aggro Ansage VA albums still appear in
                    # the report, but no target path is invented.
                    target="REVIEW_ONLY:" + str(tags.get("album") or "")
                group=result[target]
                group["target"]=target
                group["kind"]=kind
                group["review"] |= review
                group["reasons"].add(reason)
                group["tracks"]+=1
                group["observed_albums"].add(str(tags.get("album") or ""))
                group["observed_albumartists"].add(str(tags.get("albumartist") or ""))
                if tags.get("musicbrainz_albumid"):
                    group["observed_release_ids"].add(str(tags["musicbrainz_albumid"]))
                if tags.get("discnumber"):
                    group["disc_numbers"].add(str(tags["discnumber"]))
                group["observed_directories"].add(str(path.parent))
                if len(group["source_examples"])<examples:
                    group["source_examples"].append(str(path))
    groups=[]
    for group in result.values():
        converted={key:sorted(value) if isinstance(value,set) else value
                   for key,value in group.items()}
        converted["multiple_picard_release_ids"] = (
            len(group["observed_release_ids"])>1)
        converted["split_across_directories"] = (
            len(group["observed_directories"])>1)
        converted["automatic_move_allowed"]=False
        groups.append(converted)
    groups.sort(key=lambda x:x["target"].casefold())
    return {
        "status":"READ_ONLY_INCOMPLETE" if unreadable or errors else "READ_ONLY_NO_MOVES",
        "audio_scanned":scanned,"unreadable_metadata":unreadable,
        "traversal_errors":errors[:examples],
        "music_beyond_roots_not_checked":True,
        "groups":groups,
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("roots", type=Path, nargs="+")
    p.add_argument("--max-audio",type=int,default=250000)
    p.add_argument("--examples",type=int,default=12)
    args=p.parse_args()
    print(json.dumps(
        audit_library(args.roots,max_audio=args.max_audio,examples=args.examples),
        indent=2,ensure_ascii=False))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
