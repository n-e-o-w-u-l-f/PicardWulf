"""Conservative, user-specified BMAX Preset 3 corrections; no I/O.

The display names of collections and artists are kept exactly as requested.
No old files or Picard settings are modified by this module.
"""
from __future__ import annotations
from dataclasses import dataclass
import re
import unicodedata
from typing import Mapping

VA_FOLDER = '![-1.2-VARiOUS-ARTiSTz-]!'
COLLAB_FOLDER = '![-1.1-COLLABORATiVEz--]!'
SOUNDTRACK_FOLDER = '[--3--SOUNTRACKz--]'
W_AND_W = 'W&W X AXMO X André Schnura feat. Lucenzo & Don Omar'
_VA = {'various artists', 'verschiedene interpreten', 'various', 'verschiedene künstler'}
_NORDIC = re.compile(r'^nordic rave(?:\s+(?P<volume>\d{1,2}))?$', re.I)
_ENZYME = re.compile(r'^enzyme injection(?:\s+part\s+(?P<volume>\d{1,2}))?$', re.I)
_KNOWN_FLAT = {
    '... like a raging bull', 'a² records unleashed',
    'dawn of paranoia', 'social teknology 12', 'necrochasm',
}

@dataclass(frozen=True)
class Correction:
    kind: str
    folder: str
    reason: str
    album: str = ''
    albumartist: str = ''
    review: bool = False


def _str(value):
    if isinstance(value, (tuple, list)):
        return _str(value[0]) if value else ''
    return str(value or '').strip()


def _norm(value):
    return ' '.join(unicodedata.normalize('NFKC', _str(value)).casefold()
                    .replace('–', '-').replace('—', '-').replace('_', ' ').split())


def classify(metadata: Mapping[str, object], year: str) -> Correction | None:
    """Return exact corrections only when year is trusted, otherwise abstain."""
    if not re.fullmatch(r'(19|20)\d{2}', _str(year)):
        return None
    album = _str(metadata.get('album'))
    credit = _str(metadata.get('albumartist'))
    performer = _str(metadata.get('artist'))
    title = _norm(album)
    aa = _norm(credit)
    artist = _norm(performer)
    if title.startswith('aladdin ') and (
        'deutscher original film-soundtrack' in title or
        'deutscher original-film-soundtrack' in title
    ):
        return Correction('SOUNDTRACK',
            f'{SOUNDTRACK_FOLDER}/{year} - Aladdin (Deutscher Original Film-Soundtrack)',
            'disney_aladdin_german_ost',
            'Aladdin (Deutscher Original Film-Soundtrack)')
    if title == 'dr. dre & friends':
        return Correction('ARTIST', f'Dr. Dre/{year} - Dr. Dre & Friends',
                          'dr_dre_named_release', album, 'Dr. Dre')
    if 'rolfs liederkalender' in title and 'jahresuhr' in title:
        return Correction('ARTIST', f'Rolf Zuckowski/{year} - Die Jahresuhr',
                          'rolf_jahresuhr_album', 'Die Jahresuhr', 'Rolf Zuckowski')
    if aa == 'so klingt weihnachten!' and artist == 'rolf zuckowski':
        if not album:
            return None
        from .album_routing import component
        return Correction('ARTIST',
            f'Rolf Zuckowski/{year} - {component(album)}',
            'rolf_incorrect_albumartist', album, 'Rolf Zuckowski')
    if aa == _norm(W_AND_W):
        if not album:
            return None
        from .album_routing import component
        return Correction('COLLABORATION',
            f'{COLLAB_FOLDER}/{W_AND_W}/{year} - {component(album)}',
            'exact_user_confirmed_collaboration', album, credit)
    if aa in _VA:
        n = _NORDIC.fullmatch(title)
        if n:
            vol = n.group('volume')
            standard = f'Nordic Rave {int(vol)}' if vol else 'Nordic Rave'
            return Correction('SAMPLER',
                f'{VA_FOLDER}/Nordic Rave/{year} - {standard}',
                'nordic_rave_series', standard, 'Various Artists')
        e = _ENZYME.fullmatch(title)
        if e:
            vol = e.group('volume')
            standard = f'Enzyme Injection Part {int(vol)}' if vol else 'Enzyme Injection'
            return Correction('SAMPLER',
                f'{VA_FOLDER}/Enzyme Injection/{year} - {standard}',
                'enzyme_injection_series', standard, 'Various Artists')
        if title in _KNOWN_FLAT:
            from .album_routing import component
            return Correction('SAMPLER',
                f'{VA_FOLDER}/{year} - {album if title == "... like a raging bull" else component(album)}',
                'explicit_user_list_individual_sampler', album, 'Various Artists')
    return None


def route_preset3(metadata: Mapping[str, object]):
    """Return an AlbumRoute using exactly BMAX's existing folder prefixes.

    This adapter leaves neutral classifier behavior unchanged for other users.
    The output excludes the track leaf: only the album folder is proposed.
    """
    from .album_routing import AlbumRoute, _year, route_album, component
    album = _str(metadata.get('album'))
    artist = _str(metadata.get('albumartist'))
    year, _ = _year(metadata)
    correction = classify(metadata, year)
    if correction:
        return AlbumRoute(correction.kind, correction.folder,
                          correction.reason, correction.review)
    if not year or not album:
        return AlbumRoute('REVIEW', '', 'missing_year_or_album', True)
    if _norm(artist) == 'verschiedene interpreten':
        # German credited VA is just as canonical as English VA. Unknown
        # release groups still go into a VA flat album, not into an
        # incorrectly named "Verschiedene Interpreten" artist directory.
        return AlbumRoute('SAMPLER',
            f'{VA_FOLDER}/{year} - {component(album)}',
            'german_various_artists_canonical')
    normal = route_album(metadata)
    if not normal.folder or normal.review:
        return normal
    if normal.kind == 'SAMPLER' and normal.folder.startswith('Various Artists/'):
        return AlbumRoute(normal.kind, VA_FOLDER + normal.folder[len('Various Artists'):],
                          normal.reason, normal.review)
    if normal.kind == 'COLLABORATION' and normal.folder.startswith('Collaborations/'):
        return AlbumRoute(normal.kind, COLLAB_FOLDER + normal.folder[len('Collaborations'):],
                          normal.reason, normal.review)
    return normal


def picard_preset3_folder(parser, album: str, albumartist: str,
                          originaldate: str = '', date: str = '',
                          artist: str = '', secondary: str = '',
                          albumartists: str = '', collection: str = '',
                          volume: str = '') -> str:
    """Picard function provides album DIRECTORY only, not the track leaf."""
    artists = [x.strip() for x in albumartists.split(';') if x.strip()]
    result = route_preset3({
        'album': album, 'albumartist': albumartist, 'artist': artist,
        'originaldate': originaldate, 'date': date,
        '_secondaryreleasetype': secondary,
        'albumartists': artists, 'sampler_collection': collection,
        'sampler_volume': volume,
    })
    return result.folder if result.folder and not result.review else ''


_WRAPPER_MARKER = '$pw_preset3_retarget('
_MASTER = '[--1--MUSiKz------------]'
_DISC = re.compile(r'^(?:CD|Disc|Disk)\s*\d{1,2}$', re.I)


class Preset3Unsafe(ValueError):
    pass


def retarget_original(original: str, album: str, albumartist: str,
                      originaldate: str = '', date: str = '',
                      artist: str = '', secondary: str = '',
                      albumartists: str = '', collection: str = '',
                      volume: str = '') -> str:
    """Retain the original evaluated track filename and disc subdirectory.

    Unrecognized releases return the PRECISE ORIGINAL SCRIPT OUTPUT.
    """
    value = _str(original)
    md = {
        'album': album, 'albumartist': albumartist,
        'originaldate': originaldate, 'date': date,
        'artist': artist, '_secondaryreleasetype': secondary,
        'albumartists': [s.strip() for s in albumartists.split(';') if s.strip()],
        'sampler_collection': collection, 'sampler_volume': volume,
    }
    route = route_preset3(md)
    if not route.folder or route.review:
        return original
    # Picard file naming scripts are relative, without Windows drive roots.
    # Reject absolute values and traversal rather than constructing an
    # unverified new destination.
    normalized = value.replace('\\', '/')
    if (not normalized or normalized.startswith(('/', '//')) or
            re.match(r'^[A-Za-z]:', normalized)):
        return original
    parts = normalized.split('/')
    if (len(parts) < 2 or any(part in ('', '.', '..') for part in parts)
            or not parts[-1]):
        return original
    prefix = (_MASTER + '/') if parts[0].casefold() == _MASTER.casefold() else ''
    # Preserve per-disc folders if the original script explicitly emitted one.
    leaf = '/'.join(parts[-2:]) if len(parts) > 2 and _DISC.fullmatch(parts[-2]) else parts[-1]
    return prefix + route.folder + '/' + leaf


def picard_preset3_retarget(parser, original: str, album: str,
                            albumartist: str, originaldate: str = '',
                            date: str = '', artist: str = '',
                            secondary: str = '', albumartists: str = '',
                            collection: str = '', volume: str = '') -> str:
    return retarget_original(
        original, album, albumartist, originaldate, date, artist,
        secondary, albumartists, collection, volume)


def prepare_active_preset3(scripts: dict, active_id: str) -> dict:
    """Copy/patch ONLY the selected live Preset 3; rejects ambiguous scripts.

    The caller must hold the live Picard config, back it up and parse+verify
    the generated script using the exact runtime before committing changes.
    """
    from copy import deepcopy
    if not isinstance(scripts, dict) or not isinstance(active_id, str):
        raise Preset3Unsafe('Invalid selected script collection')
    if active_id not in scripts or not isinstance(scripts[active_id], dict):
        raise Preset3Unsafe('Active script ID not present')
    info = scripts[active_id]
    title = _str(info.get('title'))
    body = info.get('script')
    if not (re.fullmatch(r'Preset\s*3', title, re.I) or
            re.fullmatch(r'Preset\s*3', active_id, re.I)):
        raise Preset3Unsafe('Active script is not verified as Preset 3')
    if not isinstance(body, str) or not body.strip():
        raise Preset3Unsafe('Active Preset 3 is empty')
    if _WRAPPER_MARKER in body:
        raise Preset3Unsafe('Preset 3 already wrapped; no second patch')
    if len(body) > 16000:
        raise Preset3Unsafe('Unexpected overly long script; manual audit required')
    # No duplicate or loss of existing naming code: the first evaluated
    # argument is the entire exact OLD script.
    wrapper = (
        '$pw_preset3_retarget(' + body +
        ',%album%,%albumartist%,%originaldate%,%date%,%artist%,' +
        '$join(%_secondaryreleasetype%,;),$join(%albumartists%,;),' +
        '%sampler_collection%,%sampler_volume%)'
    )
    result = deepcopy(scripts)
    result[active_id]['script'] = wrapper
    assert result[active_id]['script'].count(body) == 1
    for key in scripts:
        if key != active_id and result[key] != scripts[key]:
            raise Preset3Unsafe('Unrelated script changed')
    return result
