"""Conservative naming for the WWE/WWF The Music sampler series.

This module only *suggests* a relative album directory. It never writes
audio tags or moves any media. Release-wide credits must be evaluated apart
from track performers: WWE music often has a single composer (Jim Johnston)
or featured performer but belongs to the VA sampler series.

Historical title variants and years are limited to documented releases.
For the ambiguous 'Full Metal' volume 1, trust only a supplied 1995/1996
release date, rather than inventing one.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Mapping

# Original release years, not an arbitrary remaster or local file timestamp.
# Volume 1 / Full Metal is variously dated 1995 vs 1996: require metadata.
ORIGINAL_YEARS = {
    2: 1997, 3: 1998, 4: 1999, 5: 2001, 6: 2004,
    7: 2007, 8: 2008, 9: 2009, 10: 2010,
}
_VOLUMES = re.compile(
    r"^\s*(?:(?:ThemeAddict|Voices)\s*[:\-]\s*)?"
    r"(?:WWF|WWE)\s*[:\-]?\s*The\s+Music\s*"
    r"(?:,|:|\-|\s)*\s*Vol(?:ume)?\.?\s*"
    r"(?P<volume>0?[1-9]|10)"
    r"(?:\s*[\[(]\s*(?:Deluxe(?: Edition)?|2-CD Deluxe Edition|"
    r"Special Edition|Japan(?:ese)? Edition|Remaster(?:ed)?|Disc\s*[12])\s*[\])])?"
    r"\s*$",
    re.IGNORECASE,
)
_NEW_DAY = re.compile(
    r"^\s*WWE\s*[:\-]?\s*The\s+Music\s*:\s*A\s+New\s+Day"
    r"\s*,?\s*Vol(?:ume)?\.?\s*10\s*$",
    re.IGNORECASE,
)
_FULL_METAL = re.compile(
    r"^\s*WWF\s+Full\s+Metal\s*:\s*The\s+Album\s*$",
    re.IGNORECASE,
)
_YEAR = re.compile(r"^\s*(19\d{2}|20\d{2})\b")
_CANONICAL_FOLDER = re.compile(
    r"^\s*(?P<year>(?:19|20)\d{2})\s*-\s*WWE\s+The\s+Music"
    r"\s+Volume\s+(?P<volume>10|[1-9])\s*$", re.IGNORECASE,
)
_VA = {"various artists", "various", "verschiedene interpreten"}
_PROVIDER = {"spotify", "apple music", "deezer", "soundcloud", "itunes"}


@dataclass(frozen=True)
class SeriesFolder:
    volume: int
    year: int
    relative_folder: str
    year_conflict: bool = False


def _first(value: object) -> str:
    if isinstance(value, (tuple, list)):
        return _first(value[0]) if value else ""
    return str(value or "").strip()


def wwe_volume(album: object) -> int | None:
    title = _first(album)
    if len(title) > 220 or not title:
        return None
    if _FULL_METAL.fullmatch(title):
        return 1
    if _NEW_DAY.fullmatch(title):
        return 10
    # Avoid "The Music, Vol. 9" nested inside unrelated artist names; only
    # exact known series tokens and not WWE Uncaged, Originals, Tough Enough.
    hit = _VOLUMES.search(title)
    return int(hit.group("volume")) if hit else None


def wwe_folder(album: object, date: object = "", originaldate: object = "") -> SeriesFolder | None:
    """Canonical 'Various Artists/WWE The Music/YYYY - WWE The Music Volume N'.

    Do not silently invent year for Full Metal Volume 1. Original release
    years for the named series 2-10 are fixed despite reissue metadata.
    """
    volume = wwe_volume(album)
    if volume is None:
        return None
    supplied_year = None
    for candidate in (originaldate, date):
        m = _YEAR.match(_first(candidate))
        if m:
            supplied_year = int(m.group(1))
            break
    year = ORIGINAL_YEARS.get(volume)
    if year is None:
        if supplied_year not in (1995, 1996):
            return None
        year = supplied_year
    relative = f"Various Artists/WWE The Music/{year} - WWE The Music Volume {volume}"
    return SeriesFolder(
        volume=volume,
        year=year,
        relative_folder=relative,
        year_conflict=supplied_year is not None and supplied_year != year,
    )



def wwe_folder_hint(folder: object, date: object = "", originaldate: object = "") -> SeriesFolder | None:
    """Recognize both original release labels and year-prefixed canonical folders.

    Media lacking album tags can still be inventoried if already under a
    '2009 - WWE The Music Volume 9' folder. A year/volume conflict is flagged.
    """
    label = _first(folder)
    match = _CANONICAL_FOLDER.fullmatch(label)
    if match:
        folder_year = int(match.group("year"))
        volume = int(match.group("volume"))
        if volume == 1:
            if folder_year not in (1995, 1996):
                return None
            year = folder_year
        else:
            year = ORIGINAL_YEARS[volume]
        return SeriesFolder(
            volume=volume, year=year,
            relative_folder=f"Various Artists/WWE The Music/{year} - WWE The Music Volume {volume}",
            year_conflict=folder_year != year,
        )
    return wwe_folder(label, date, originaldate)

def route_metadata(metadata: Mapping[str, object]) -> dict[str, object]:
    """Preview only, never change audio tags or active Picard naming options.

    VA for WWE is explicitly guaranteed by series, regardless of track artist.
    Non-WWE records use *release* albumartist, not the track artist or
    'compilation' flag. A suspicious/unknown VA artist credit is reviewed,
    never rewritten from a single track (real samplers have solo tracks).
    """
    album = _first(metadata.get("album"))
    artist = _first(metadata.get("artist"))
    albumartist = _first(metadata.get("albumartist"))
    found = wwe_folder(album, metadata.get("date"), metadata.get("originaldate"))
    if found:
        return {
            "state": "WWE_SERIES",
            "folder": found.relative_folder,
            "volume": found.volume,
            "year": found.year,
            "needs_review": found.year_conflict,
            "albumartist_for_folder": "Various Artists",
        }
    if not album:
        return {"state": "REVIEW", "reason": "missing_album", "needs_review": True}
    if not albumartist or albumartist.casefold() in _PROVIDER:
        return {"state": "REVIEW", "reason": "unverified_albumartist", "needs_review": True}
    if albumartist.casefold() in _VA:
        # Cannot infer a release's genuine albumartist from one solo track!
        return {
            "state": "VA_OR_REVIEW",
            "needs_review": artist.casefold() not in _VA and bool(artist),
            "reason": "verify_release_wide_artist_credit",
            "albumartist_for_folder": "Various Artists",
        }
    # These *artist* compilations stay with the credited album artist,
    # even if _secondaryreleasetype contains 'compilation' or 'dj-mix'.
    return {"state": "ARTIST_ALBUM", "needs_review": False,
            "albumartist_for_folder": albumartist}


def picard_wwe_folder(parser, album: str, date: str = "", originaldate: str = "") -> str:
    """Picard native naming function: $pw_wwe_folder(%album%,%date%,%originaldate%).

    Returns empty for non-WWE, which allows the user's existing naming
    branches to remain completely unchanged until an explicitly reviewed
    script update. Returns relative directory WITHOUT track filename.
    """
    found = wwe_folder(album, date, originaldate)
    return found.relative_folder if found else ""
