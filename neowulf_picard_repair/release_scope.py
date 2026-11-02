"""Release-wide, no-I/O policy for wrongly VA-credited artist compilations.

Evidence hierarchy: a verified *release* identity or the user's narrowly
specified album wins over individual featured track performers. Conversely,
a mixed-artist Aggro Ansage sampler is NOT silently attributed to Die Sekte.
All paths are relative to BMAX's verified music master root.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata
from typing import Mapping

from .album_routing import component, first

VA_ROOT = "![-1.2-VARiOUS-ARTiSTz-]!"
_VA = {"various artists", "verschiedene interpreten", "verschiedene künstler",
       "diverse interpreten", "various", "v.a.", "va"}
_SEKTE = {"die sekte", "alles ist die sekte", "a.i.d.s.", "a.i.d.s",
          "aids (alles ist die sekte)"}
_FRANK = re.compile(
    r"^(?:(?:frank\s+zander)\s*[-–:]\s*)?meine\s+coolsten\s+hits"
    r"(?:\s*[,\[(]?\s*(?:cd|disc|disk)\s*([1-3])\s*[\])]?\s*)?$",
    re.I)
_AGGRO = re.compile(r"^aggro\s+ansage(?:\s+(?:nr\.?|nummer|no\.?)\s*([1-9]))?"
                    r"(?:\s*[:\-].*)?$", re.I)
_WWE_ENTRANCE = re.compile(
    r"^(?:wwe|wwf)\s+(?:superstar\s+)?entrance\s+themes"
    r"(?:\s*[,\[(]?\s*(?:cd|disc|disk)\s*[1-9]\s*[\])]?\s*)?$", re.I)
_WWE_ANTHOLOGY = re.compile(
    r"^wwe\s+anthology(?:\s*[,\[(]?\s*(?:cd|disc|disk)\s*[1-3]"
    r"\s*[\])]?\s*)?$", re.I)


@dataclass(frozen=True)
class Scope:
    kind: str
    folder: str
    reason: str
    review: bool = False
    coherent_discs: bool = False


def _norm(value: object) -> str:
    text = unicodedata.normalize("NFKC", first(value)).casefold().strip()
    return " ".join(text.replace("–", "-").replace("—", "-").split())


def release_artist_scope(md: Mapping[str,object], year: str) -> Scope | None:
    """Only the three evidenced artist/release families override bad VA tags.

    A None result delegates to the normal classifier; a REVIEW result blocks
    any later blanket VA fallback.  No tag mutation or file operations.
    """
    title = first(md.get("album"))
    title_norm = _norm(title)
    credit = _norm(md.get("albumartist"))
    release_names = md.get("albumartists") or md.get("_albumartists") or ()
    if isinstance(release_names,(list,tuple)):
        credits = {_norm(a) for a in release_names}
    else:
        credits = set()

    if _FRANK.fullmatch(title):
        # This is the actual Frank Zander 2022 2-CD compilation, not three
        # multi-artist volumes. Guests and aliases on individual tracks are
        # no reason to change its release-wide albumartist.
        if year and year != "2022":
            return Scope("REVIEW","","frank_zander_edition_year_conflict",True)
        return Scope("ARTIST","Frank Zander/2022 - Meine coolsten Hits",
                     "user_confirmed_frank_zander_2022_2cd",coherent_discs=True)

    # Solo and group compilations remain with their confirmed album artist
    # even when _secondaryreleasetype includes 'compilation'.
    sekte_credit = credit in _SEKTE or bool(credits & _SEKTE)
    if sekte_credit:
        if not year:
            return Scope("REVIEW","","sekte_year_needed",True)
        label = component(title)
        if not label:
            return Scope("REVIEW","","unsafe_sekte_album_title",True)
        return Scope("ARTIST",f"Die Sekte/{year} - {label}",
                     "release_wide_die_sekte_credit",
                     coherent_discs=True)

    if title_norm in {"ihr nutten", "die sekte"}:
        if title_norm == "ihr nutten" and year not in ("", "2001"):
            return Scope("REVIEW","","sekte_release_year_conflict",True)
        if title_norm == "die sekte" and year not in ("", "2009"):
            return Scope("REVIEW","","sekte_release_year_conflict",True)
        assigned_year = year or ("2001" if title_norm == "ihr nutten" else "2009")
        return Scope("ARTIST",f"Die Sekte/{assigned_year} - {component(title)}",
                     "catalogue_named_die_sekte_album",coherent_discs=True)

    if _AGGRO.fullmatch(title) and credit in _VA:
        # MusicBrainz records Aggro Ansage Nr. 1 as Various Artists. Some
        # sources credit 'Aggro Berlin präsentiert'. Album title alone is not
        # evidence that all its performers belong to Die Sekte.
        return Scope("REVIEW","","aggro_ansage_mixed_artist_credit_review",True)

    # WWE volume numbers already handled in wwe_series.py, not duplicated
    # here; Anthology and Entrance Themes are distinct, coherent albums.
    if _WWE_ANTHOLOGY.fullmatch(title):
        if year and year!="2002":
            return Scope("REVIEW","","wwe_anthology_edition_year_conflict",True)
        return Scope("SAMPLER",
                     f"{VA_ROOT}/WWE Anthology/2002 - WWE Anthology",
                     "official_wwe_anthology_three_cd",coherent_discs=True)

    if _WWE_ENTRANCE.fullmatch(title):
        if not year:
            return Scope("REVIEW","","wwe_entrance_themes_release_year_needed",True)
        return Scope("SAMPLER",
                     f"{VA_ROOT}/WWE Entrance Themes/{year} - WWE Entrance Themes",
                     "user_confirmed_entrance_theme_disc_group",
                     coherent_discs=True)
    return None


def disc_subfolder(original_relative: str, discnumber: object,
                   totaldiscs: object, *, allowed: bool) -> str:
    """Non-destructive disc grouping for confirmed 2+ disc editions.

    Never rewrite a filename containing its own disc marker. If the
    existing path has CD 01 already, preserve it. Only add CD nn when a
    validated explicit album-wide totaldisc and discnumber are available.
    """
    original = original_relative.replace("\\","/")
    parts=original.split("/")
    if len(parts)>1 and re.fullmatch(r"(?:CD|Disc|Disk)\s*0?[1-9]\d?",parts[-2],re.I):
        return parts[-2]+"/"+parts[-1]
    leaf=parts[-1] if parts else ""
    if not allowed:
        return leaf
    d=first(discnumber)
    n=first(totaldiscs)
    if not re.fullmatch(r"[1-9]\d?",d) or not re.fullmatch(r"[2-9]\d?",n):
        return leaf
    if int(d)>int(n):
        return leaf
    if re.match(r"^(?:CD|Disc|Disk)\s*0?[1-9]\d?\b",leaf,re.I):
        return leaf
    return f"CD {int(d):02d}/{leaf}"
