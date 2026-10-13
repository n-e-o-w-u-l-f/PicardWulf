"""Lossless, narrow NEOWULF Picard 3 name-routing migration.

No filesystem or Picard settings mutations in this module.
"""

from copy import deepcopy

RGID = '77c24600-5610-473b-876e-09d8a42296b7'
OLD = (
    '$or($inmulti(%_secondaryreleasetype%,compilation),'
    '$inmulti(%_secondaryreleasetype%,dj-mix),'
    '$rsearch(%album%,CD[0-9]+),'
    '$rsearch(%album%,Mixed By))'
)
NEW = '$eq($lower($strip(%albumartist%)),various artists)'
PROVIDERS = {'apple music', 'spotify', 'deezer', 'soundcloud'}


class RepairNotPossible(ValueError):
    pass


def is_neowulf_script(info):
    if not isinstance(info, dict):
        return False
    body = info.get('script') or ''
    label = info.get('title') or ''
    if not isinstance(body, str) or not isinstance(label, str):
        return False
    return any(marker in body.casefold() for marker in (
        'neowulf_unmatched_fallback', '$neowulfseries(',
        '[--1--musikz------------]', '[-1.2-various-artistz-]'
    )) or 'neowulf' in label.casefold()


def find_candidates(scripts):
    if not isinstance(scripts, dict):
        raise RepairNotPossible('Picard file_renaming_scripts ist kein Dictionary')
    found = []
    for script_id, info in scripts.items():
        if not is_neowulf_script(info):
            continue
        body = info['script']
        if OLD in body or NEW in body:
            found.append((script_id, info))
    return found


def prepare_update(scripts):
    """Returns (new scripts map, candidate id), refusing ambiguous or partial fixes."""
    found = find_candidates(scripts)
    if len(found) != 1:
        raise RepairNotPossible(
            f'Genau ein NEOWULF-Skript erforderlich, {len(found)} gefunden. Keine Änderung.'
        )
    ident, info = found[0]
    body = info['script']
    if NEW in body and OLD not in body:
        raise RepairNotPossible('Skript bereits korrigiert; keine Änderung.')
    if body.count(OLD) != 1 or NEW in body:
        raise RepairNotPossible('Abweichende oder teilweise korrigierte Regel; keine Änderung.')
    updated = body.replace(OLD, NEW, 1)
    if updated.replace(NEW, OLD, 1) != body:
        raise RepairNotPossible('Verlustfreiheitsprüfung fehlgeschlagen.')
    result = deepcopy(scripts)
    result[ident]['script'] = updated
    if len(result) != len(scripts):
        raise RepairNotPossible('Skriptbestand hat sich unerwartet geändert.')
    for k in scripts:
        if k != ident and result[k] != scripts[k]:
            raise RepairNotPossible('Unbeteiligtes Skript verändert.')
    return result, ident


def is_curtain_call_2(metadata):
    """Only MusicBrainz RGID identifies the exact album; no title guessing."""
    get = getattr(metadata, 'get', None)
    if not callable(get):
        return False
    v = get('musicbrainz_releasegroupid', '')
    if isinstance(v, (list, tuple)):
        return any(isinstance(x, str) and x.strip().casefold() == RGID for x in v)
    return isinstance(v, str) and v.strip().casefold() == RGID


def correct_curtain_call_metadata(metadata):
    """Returns True when albumartist was corrected; leaves compilation typing intact."""
    if not is_curtain_call_2(metadata):
        return False
    artist = metadata.get('albumartist', '')
    if isinstance(artist, str) and artist.strip().casefold() == 'eminem':
        return False
    metadata['albumartist'] = 'Eminem'
    return True
