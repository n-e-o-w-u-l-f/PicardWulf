"""BMAX PicardWulf music-folder convention and verified release exceptions.

Source-only, no media operations. Returns a *relative* folder rooted beneath
G:\\[--1--MUSiKz------------] (Picard's move_files_to setting). Real user
Preset 3 must be read and backed up before activating this routing function.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Mapping

from .album_routing import route_album, AlbumRoute, component, first

VA_ROOT = "![-1.2-VARiOUS-ARTiSTz-]!"
COLLAB_ROOT = "![-1.1-COLLABORATiVEz--]!"
SOUNDTRACK_ROOT = "[--3--SOUNTRACKz--]"
LIVE_ROOT = "LiveSets"

VA_NAMES = frozenset({
    "various artists", "various", "verschiedene interpreten",
    "verschiedene künstler", "diverse interpreten", "v.a.", "va"
})
_ROLF = re.compile(
    r"^(?:rolfs\s+liederkalender(?:\s*[/_–-]\s*die\s+jahresuhr)?"
    r"|die\s+jahresuhr|so\s+klingt\s+weihnachten!?)$", re.I)
_DR_DRE = re.compile(r"^dr\.?\s+dre\s*(?:&|and)\s*friends$", re.I)
_NORDIC = re.compile(r"^nordic\s+rave(?:\s+(?P<n>[1-9]\d?))?$", re.I)
_ENZYME = re.compile(r"^enzyme\s+injection\s*(?::|-)?\s*part\s*(?P<n>[1-9]\d?)$",re.I)
_ALADDIN = re.compile(
    r"^aladdin\s*\(deutscher\s+original\s+film[- ]soundtrack\)$",re.I)
_WW = re.compile(
    r"^w&w\s+[x×]\s+axmo\s+[x×]\s+andr[eé]\s+schnura\s+"
    r"feat\.?\s+lucenzo\s*&\s*don\s+omar$", re.I)
_MULTI_X = re.compile(r"\s+[x×]\s+",re.I)
_TRAILING = re.compile(r"(?:[ .]+)$")
_OTHER_VA = {
    "like a raging bull", "a² records unleashed", "dawn of paranoia",
    "social teknology 12", "necrochasm",
}
_SOUNDTRACK_TYPES = {"soundtrack", "film soundtrack", "original soundtrack"}


@dataclass(frozen=True)
class NamingDecision:
    category: str
    relative_folder: str
    reason: str
    requires_review: bool = False


def _year(md: Mapping[str,object]) -> str:
    for tag in ("originalyear", "originaldate", "date", "year"):
        value=first(md.get(tag))
        match=re.match(r"^((?:19|20)\d{2})(?=$|[-/ .])",value)
        if match: return match.group(1)
    return ""


def classify_bmax(md: Mapping[str,object]) -> NamingDecision:
    """User-approved exact-target exceptions precede generic release logic.

    A wrong tagged albumartist is not propagated for known release aliases.
    Unknown releases never rewrite the albumartist. Missing year is REVIEW
    except for release-specific dates the user has explicitly provided.
    """
    title=first(md.get("album"))
    artist=first(md.get("albumartist"))
    if not title:
        return NamingDecision("REVIEW","","missing_album",True)
    year=_year(md)
    clean=component(title)
    if not clean:
        return NamingDecision("REVIEW","","unsafe_album",True)
    if _ROLF.fullmatch(title):
        if title.casefold().startswith("rolfs liederkalender") or "jahresuhr" in title.casefold():
            clean="Die Jahresuhr"
        if clean=="Die Jahresuhr":
            year="2001"  # User's actual physical copy, not early master release
        elif not year:
            return NamingDecision("REVIEW","","rolf_year_needed",True)
        return NamingDecision("ARTIST",f"Rolf Zuckowski/{year} - {clean}","known_rolf_release")
    if _DR_DRE.fullmatch(title):
        return NamingDecision("ARTIST",f"Dr. Dre/{year or '2003'} - Dr. Dre & Friends",
                              "known_dr_dre_release")
    if _WW.fullmatch(artist):
        if not year:
            return NamingDecision("REVIEW","","collaboration_year_needed",True)
        return NamingDecision("COLLABORATION",
            f"{COLLAB_ROOT}/{component(artist)}/{year} - {clean}",
            "verified_ww_axmo_credit")
    if _ALADDIN.fullmatch(title):
        return NamingDecision("SOUNDTRACK",
            f"{SOUNDTRACK_ROOT}/1993 - Aladdin (Deutscher Original Film-Soundtrack)",
            "user_verified_aladdin_copy_year")
    m=_NORDIC.fullmatch(title)
    if m and artist.casefold() in VA_NAMES:
        n=m.group('n')
        year="1996"  # All three confirmed physical series releases
        album_name=f"Nordic Rave {int(n)}" if n else "Nordic Rave"
        return NamingDecision("SAMPLER",
            f"{VA_ROOT}/Nordic Rave/{year} - {album_name}",
            "verified_nordic_rave_series")
    m=_ENZYME.fullmatch(title)
    if m and artist.casefold() in VA_NAMES:
        year=("2003" if m.group('n') == "2" else year)
        if not year:
            return NamingDecision("REVIEW","","enzyme_year_needed",True)
        album_name=f"Enzyme Injection Part {int(m.group('n'))}"
        return NamingDecision("SAMPLER",
            f"{VA_ROOT}/Enzyme Injection/{year} - {album_name}",
            "verified_enzyme_injection_series")
    # General soundtrack, with conservative release-level evidence.
    secondary=first(md.get("_primaryreleasetype") or md.get("releasetype"))
    if secondary.casefold() in _SOUNDTRACK_TYPES:
        if not year:
            return NamingDecision("REVIEW","","soundtrack_year_needed",True)
        return NamingDecision("SOUNDTRACK",
            f"{SOUNDTRACK_ROOT}/{year} - {clean}",
            "release_soundtrack_type")
    normalized_artist="Various Artists" if artist.casefold() in VA_NAMES else artist
    # Do not make up a sampler collection from a one-off album title.
    if normalized_artist=="Various Artists" and not year:
        return NamingDecision("REVIEW","","va_year_needed",True)
    if normalized_artist=="Various Artists" and title.casefold().lstrip(". ") in _OTHER_VA:
        return NamingDecision("SAMPLER",f"{VA_ROOT}/{year} - {clean}",
                              "verified_oneoff_va_collection")
    # Explicit multiple " x " separators in the *release* albumartist
    # are collaboration evidence. Do not split W&W or other fixed '&' names.
    if artist and len(_MULTI_X.split(artist))>=3:
        if not year:
            return NamingDecision("REVIEW","","collab_year_needed",True)
        return NamingDecision("COLLABORATION",
            f"{COLLAB_ROOT}/{component(artist)}/{year} - {clean}",
            "explicit_collaboration_x_credit")
    # Keep existing deterministic four-way logic for WWE, DJ sets, and
    # explicitly release-credited collaborations.
    payload=dict(md)
    payload["albumartist"]=normalized_artist
    route=route_album(payload)
    if route.folder and not route.review:
        if route.kind=="SAMPLER":
            if route.folder.startswith("Various Artists/"):
                folder=VA_ROOT+"/"+route.folder[len("Various Artists/"):]
            else:
                folder=VA_ROOT+"/"+route.folder
        elif route.kind=="COLLABORATION":
            folder=COLLAB_ROOT+"/"+route.folder.removeprefix("Collaborations/")
        elif route.kind=="LIVESET":
            folder=LIVE_ROOT+"/"+route.folder.removeprefix("LiveSets/")
        else:
            folder=route.folder
        return NamingDecision(route.kind,folder,route.reason)
    # Generic one-off compilation with a verified Various Artists credit:
    # No arbitrary series folder, but never use 'Verschiedene Interpreten'.
    if normalized_artist=="Various Artists" and year:
        return NamingDecision("SAMPLER",f"{VA_ROOT}/{year} - {clean}",
                              "oneoff_various_artists")
    return NamingDecision("REVIEW","","insufficient_release_evidence",True)


def picard_bmax_folder(parser, album: str, albumartist: str,
                       originaldate: str = "", date: str = "",
                       release_type: str = "", albumartists: str = "",
                       collection: str = "", volume: str = "") -> str:
    names=[part.strip() for part in albumartists.split(";") if part.strip()]
    item=classify_bmax({
        "album":album, "albumartist":albumartist,
        "originaldate":originaldate, "date":date,
        "_primaryreleasetype":release_type,
        "albumartists":names,
        "sampler_collection":collection, "sampler_volume":volume,
    })
    return item.relative_folder if not item.requires_review else ""


def picard_bmax_fullpath(parser, old_relative: str, album: str,
                        albumartist: str, originaldate: str = "",
                        date: str = "", release_type: str = "",
                        albumartists: str = "", collection: str = "",
                        volume: str = "") -> str:
    """Wrap an entire legacy Preset-3 script, preserving its file leaf.

    A documented Picard scripting function receives the fully evaluated
    legacy script as its FIRST argument. Reuse its leaf filename unchanged;
    replace ONLY the music album directory if evidence supports a policy
    correction. Ambiguous releases retain original output.
    """
    original=str(old_relative or "").strip().replace("\\","/")
    if not original or original.startswith("/") or ".." in original.split("/"):
        return ""
    segments=original.split("/")
    if not segments or not segments[-1] or segments[-1] in {".",".."}:
        return ""
    if any(x in segments[-1] for x in '<>:"\\|?*\x00'):
        return ""
    target=picard_bmax_folder(parser,album,albumartist,originaldate,date,
                              release_type,albumartists,collection,volume)
    if not target:
        return old_relative
    return target+"/"+segments[-1]
