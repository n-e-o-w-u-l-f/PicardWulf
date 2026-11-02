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
    r"(?:\s*[,\[(]?\s*(?:cd|disc|disk)\s*([1-2])\s*[\])]?\s*)?$",
    re.I)
_AGGRO = re.compile(r"^aggro\s+ansage(?:\s+(?:nr\.?|nummer|no\.?)\s*([1-9])x?)?"
                    r"(?:\s*[:\-].*)?$", re.I)
_FRANK_EXCESS_DISC = re.compile(
    r"^(?:(?:frank\s+zander)\s*[-–:]\s*)?meine\s+coolsten\s+hits"
    r"(?:\s*[,\[(]?\s*(?:cd|disc|disk)\s*([3-9])\s*[\])]?\s*)$", re.I)
_AGGRO_ORIGINAL_YEARS = {1: "2002", 2: "2003", 3: "2003", 4: "2004", 5: "2005"}
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

    if _FRANK_EXCESS_DISC.fullmatch(title):
        return Scope("REVIEW", "", "frank_zander_2022_only_two_discs", True)
    if _FRANK.fullmatch(title):
        # Official 2022 edition is precisely TWO CDs (40 tracks). This local
        # archive mapping is an ALBUM folder decision; guest track performers
        # must never create extra compilation release directories.
        if year and year != "2022":
            return Scope("REVIEW","","frank_zander_edition_year_conflict",True)
        disc = first(md.get("discnumber"))
        total = first(md.get("totaldiscs") or md.get("disctotal"))
        if ((disc and disc not in {"1","2","01","02"}) or
                (total and total not in {"2","02"})):
            return Scope("REVIEW","","frank_zander_disc_set_mismatch",True)
        # Grouping is only allowed when disc values are internally coherent.
        # The actual safe importer separately checks the complete pair.
        coherent = total in {"2","02"} and disc in {"1","2","01","02"}
        return Scope("ARTIST","Frank Zander/2022 - Meine coolsten Hits",
                     "verified_frank_zander_2022_2cd",
                     coherent_discs=coherent)

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

    match_aggro = _AGGRO.fullmatch(title)
    if match_aggro and credit in _VA:
        # Official catalogues describe these as Aggro Berlin / VA samplers.
        # User explicitly wants this family under Die Sekte in their own
        # BMAX archive; change ONLY the filename folder, never artist tags.
        # Each numbered release remains its own distinct album directory.
        n = match_aggro.group(1)
        known = _AGGRO_ORIGINAL_YEARS.get(int(n)) if n else None
        if year and known and year not in {known, "2006"}:
            return Scope("REVIEW","","aggro_ansage_edition_year_conflict",True)
        assigned = year or known
        if not assigned:
            return Scope("REVIEW","","aggro_ansage_year_needed",True)
        label = component(title)
        if not label:
            return Scope("REVIEW","","aggro_ansage_title_unsafe",True)
        return Scope("ARTIST",f"Die Sekte/{assigned} - {label}",
                     "explicit_user_local_archive_override_not_artist_retag",
                     coherent_discs=False)

    # WWE volume numbers already handled in wwe_series.py, not duplicated
    # here; Anthology and Entrance Themes are distinct, coherent albums.
    if _WWE_ANTHOLOGY.fullmatch(title):
        if year and year!="2002":
            return Scope("REVIEW","","wwe_anthology_edition_year_conflict",True)
        disc=first(md.get("discnumber"))
        total=first(md.get("totaldiscs") or md.get("disctotal"))
        if ((disc and disc not in {"1","2","3","01","02","03"}) or
                (total and total not in {"3","03"})):
            return Scope("REVIEW","","wwe_anthology_original_three_disc_conflict",True)
        coherent=bool(disc in {"1","2","3","01","02","03"} and total in {"3","03"})
        return Scope("SAMPLER",
                     f"{VA_ROOT}/WWE Anthology/2002 - WWE Anthology",
                     "official_wwe_anthology_three_cd",coherent_discs=coherent)

    if _WWE_ENTRANCE.fullmatch(title):
        if not year:
            return Scope("REVIEW","","wwe_entrance_themes_release_year_needed",True)
        disc=first(md.get("discnumber"))
        total=first(md.get("totaldiscs") or md.get("disctotal"))
        if ((disc and not re.fullmatch(r"0?[1-9]\d?",disc)) or
                (total and not re.fullmatch(r"0?[2-9]\d?",total)) or
                (disc and total and int(disc)>int(total))):
            return Scope("REVIEW","","wwe_entrance_themes_disc_conflict",True)
        coherent=bool(disc and total and int(disc)<=int(total))
        return Scope("SAMPLER",
                     f"{VA_ROOT}/WWE Entrance Themes/{year} - WWE Entrance Themes",
                     "user_confirmed_entrance_theme_disc_group",
                     coherent_discs=coherent)
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
    if not re.fullmatch(r"0?[1-9]\d?",d) or not re.fullmatch(r"0?[2-9]\d?",n):
        return leaf
    if int(d)>int(n):
        return leaf
    if re.match(r"^(?:CD|Disc|Disk)\s*0?[1-9]\d?\b",leaf,re.I):
        return leaf
    return f"CD {int(d):02d}/{leaf}"
