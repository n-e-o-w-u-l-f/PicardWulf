"""Pure, conservative PicardWulf album-directory classification.

The *release-level* credit controls the folder, never one track performer or
MusicBrainz's 'compilation' bit. This module performs zero I/O. On ambiguity,
it returns REVIEW rather than silently moving albums. Windows filenames and
path traversal are validated before any destination is offered.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import PurePath
import re
import unicodedata
from typing import Mapping

from .wwe_series import wwe_folder

_BAD_COMPONENT = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_YEAR = re.compile(r'^\s*((?:19|20)\d{2})(?:[-/.](\d{2})[-/.](\d{2}))?\b')
_VOL = re.compile(r'^(?P<collection>.+?)\s*[,\-:]?\s*(?:Vol(?:ume)?\.?|Band)\s*(?P<vol>0?[1-9]\d{0,2})\s*$',re.I)
_VA = {'various artists','various','verschiedene interpreten'}
_PROVIDER = {'spotify','soundcloud','deezer','apple music','itunes','last.fm','musicbrainz'}
_LIVE_TITLE = re.compile(
    r'\b(?:DJ\s*Set|Live\s*Set|Boiler\s*Room|Essential\s*Mix|'
    r'Live\s*Mix|Club\s*Set|Radio\s*Set|Festival\s*Set)\b',
    re.I,
)
_RESERVED = {'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))}


@dataclass(frozen=True)
class AlbumRoute:
    kind: str
    folder: str
    reason: str = ''
    review: bool = False


def first(value: object) -> str:
    if isinstance(value,(list,tuple)):
        return first(value[0]) if value else ''
    return str(value or '').strip()


def component(raw: object) -> str:
    """Safe one-level Windows/Posix name, never a path or device label."""
    val = unicodedata.normalize('NFC',first(raw))
    val = _BAD_COMPONENT.sub('_',val).strip().strip('.').rstrip(' .')
    if not val or val in {'.','..'} or val.split('.')[0].upper() in _RESERVED:
        return ''
    return val[:130].rstrip(' .')


def _year(md: Mapping, *, live: bool = False) -> tuple[str,str]:
    fields = (('event_date','set_date','date','originaldate')
              if live else
              ('originaldate','date','_releasegroup_firstreleasedate','release_date'))
    for field in fields:
        m = _YEAR.match(first(md.get(field)))
        if m:
            year=m.group(1)
            full=f'{year}-{m.group(2)}-{m.group(3)}' if m.group(2) and m.group(3) else ''
            if full:
                try: date.fromisoformat(full)
                except ValueError: full=''
            return year,full
    return '',''


def _collaborators(md: Mapping) -> tuple[str,...]:
    """Only authoritative release-wide arrays, never ambiguous '&' splitting.

    Bands like 'Earth, Wind & Fire' and 'Simon & Garfunkel' are ONE artist.
    Featured track performers cannot manufacture an album collaboration.
    """
    artists = md.get('albumartists') or md.get('_albumartists')
    if not isinstance(artists,(tuple,list)):
        return ()
    clean=[first(a) for a in artists]
    if len(clean)<2 or len(clean)>12 or any(not a or a.casefold() in _VA|_PROVIDER for a in clean):
        return ()
    if len({x.casefold() for x in clean}) != len(clean):
        return ()
    return tuple(clean)


def _is_live_set(md: Mapping) -> bool:
    flag=md.get('is_liveset') is True
    typ=first(md.get('set_type')).casefold()
    if flag or typ in {'dj-set','live-set','radio-set','festival-set'}:
        return True
    secondary=md.get('_secondaryreleasetype') or md.get('releasetype') or ''
    words=([first(x).casefold() for x in secondary]
           if isinstance(secondary,(tuple,list)) else
           [x.strip().casefold() for x in re.split('[;,/]',first(secondary))])
    # Secondary 'live' by itself describes conventional live albums as well.
    if 'live' in words and 'dj-mix' in words:
        return True
    if _LIVE_TITLE.search(first(md.get('album'))) and any(
            word in words for word in ('live','dj-mix','broadcast')):
        return True
    return False


def _collection(md: Mapping, title: str) -> tuple[str,str]:
    """Only releases credited VA may be parsed as sampler collections."""
    explicit=first(md.get('sampler_collection') or md.get('collection'))
    if explicit:
        return explicit,''
    m=_VOL.fullmatch(title)
    if m:
        collection=m.group('collection').strip(' -,:.')
        return collection,str(int(m.group('vol')))
    return '',''


def route_album(metadata: Mapping[str,object]) -> AlbumRoute:
    title=first(metadata.get('album'))
    artist=first(metadata.get('albumartist'))
    if not title or not component(title):
        return AlbumRoute('REVIEW','','missing_or_unsafe_album',True)
    wwe=wwe_folder(title,metadata.get('date'),metadata.get('originaldate'))
    if wwe:
        return AlbumRoute('SAMPLER',wwe.relative_folder,
                          'wwe_original_year_conflict' if wwe.year_conflict else 'wwe_series',
                          wwe.year_conflict)
    live=_is_live_set(metadata)
    year,full_date=_year(metadata,live=live)
    if not year:
        return AlbumRoute('REVIEW','','missing_release_year',True)
    if not artist or artist.casefold() in _PROVIDER:
        return AlbumRoute('REVIEW','','unverified_albumartist',True)
    if not component(artist):
        return AlbumRoute('REVIEW','','unsafe_artist',True)
    title_folder=component(title)
    if live:
        # LiveSets are DJs/radio/festival *sets*. Live concerts released as
        # normal live albums stay with artist. Event date if available.
        label=f'{full_date or year} - {title_folder}'
        return AlbumRoute('LIVESET',f'LiveSets/{component(artist)}/{label}',
                          'explicit_live_set_evidence')
    if artist.casefold() in _VA:
        collection,volume=_collection(metadata,title)
        series=component(collection)
        if not series:
            return AlbumRoute('REVIEW','','va_release_collection_unverified',True)
        # Explicit sampler_collection is not a volume number. Extract only
        # trusted numeric metadata or title suffix, never guess Vol. 1.
        if not volume:
            m=_VOL.fullmatch(title)
            if m: volume=str(int(m.group('vol')))
            else:
                raw=first(metadata.get('sampler_volume'))
                if re.fullmatch(r'[1-9]\d{0,2}',raw):
                    volume=str(int(raw))
        title_normalized=title_folder
        if volume:
            # Avoid 'Vol. 38 Vol. 38'; normalize the title's trailing volume.
            title_normalized=_VOL.sub(
                lambda m:component(m.group('collection'))+f' Vol. {volume}',title)
            if not _VOL.fullmatch(title):
                title_normalized=title_folder+f' Vol. {volume}'
        return AlbumRoute('SAMPLER',f'Various Artists/{series}/{year} - {title_normalized}',
                          'release_va_and_series')
    collab=_collaborators(metadata)
    if collab:
        safe=[component(x) for x in collab]
        if any(not s for s in safe):
            return AlbumRoute('REVIEW','','unsafe_collaborator',True)
        name=', '.join(safe[:-1])+' & '+safe[-1]
        if len(name)>160:
            return AlbumRoute('REVIEW','','collaboration_path_too_long',True)
        return AlbumRoute('COLLABORATION',f'Collaborations/{name}/{year} - {title_folder}',
                          'release_wide_multi_artist_credit')
    if isinstance(metadata.get('albumartists'),(list,tuple)) and len(metadata['albumartists'])>1:
        return AlbumRoute('REVIEW','','ambiguous_collaboration_credit',True)
    return AlbumRoute('ARTIST',f'{component(artist)}/{year} - {title_folder}',
                      'confirmed_release_albumartist')


def picard_album_folder(parser, album: str, albumartist: str, originaldate: str = '',
                        date: str = '', secondary: str = '', artists: str = '',
                        collection: str = '', volume: str = '') -> str:
    """Official Picard script: $pw_album_folder(...).

    Semicolon-delimited list must be passed explicitly from genuine album-
    level credit, never inferred from track artist or group name.
    """
    entries=[x.strip() for x in artists.split(';') if x.strip()] if artists else []
    route=route_album({
        'album':album,'albumartist':albumartist,'originaldate':originaldate,
        'date':date,'_secondaryreleasetype':secondary,
        'albumartists':entries,'sampler_collection':collection,
        'sampler_volume':volume,
    })
    return route.folder if not route.review else ''
