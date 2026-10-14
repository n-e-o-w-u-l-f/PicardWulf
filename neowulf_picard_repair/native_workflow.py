"""Native MusicBrainz release matching and explicit, backed-up tag changes.

Pure functions are usable in tests without loading Qt or touching Picard. A
non-MusicBrainz provider is never treated as a MusicBrainz release authority.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import uuid
from datetime import datetime, timezone

from .universal_engine import norm, score, similarity
from .universal_adapters import one

UUID_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$', re.I)
ISRC_RE = re.compile(r'^[A-Z]{2}[A-Z0-9]{3}[0-9]{7}$')
INVALID_ARTISTS = frozenset({'apple music', 'spotify', 'deezer', 'soundcloud', 'last fm', 'itunes', 'musicbrainz'})


class UnsafeCandidate(ValueError):
    pass


def is_uuid(value):
    return bool(UUID_RE.fullmatch(one(value)))


def eligible(q, candidate, *, min_score=0.82):
    """Reject identifier collisions, wrong artists/titles and provenance-as-artist."""
    if norm(candidate.get('artist')) in INVALID_ARTISTS or norm(candidate.get('albumartist')) in INVALID_ARTISTS:
        return False, 'provider in artist field'
    if candidate.get('enrichment_status') in ('CONFLICT','ALBUM_CONFLICT'):
        return False, 'provider detail contradicts candidate'
    s, why = score(q, candidate)
    if s < min_score:
        return False, why if why != 'compatible' else 'insufficient score'
    from .auto_selection import text_similarity, edition_conflicts, version_markers
    if edition_conflicts(q,candidate):return False,'edition conflict'
    if any(version_markers(q.get(k))!=version_markers(candidate.get(k))
           for k in ('title','album') if q.get(k) and candidate.get(k)):
        return False,'recording/release version conflict'
    if text_similarity(q['artist'], candidate['artist']) < 0.90:
        return False, 'artist mismatch'
    if text_similarity(q['title'], candidate['title']) < 0.90:
        return False, 'title mismatch'
    if q.get('album') and candidate.get('album') and similarity(q['album'], candidate['album']) < 0.80:
        return False, 'album mismatch'
    return True, 'compatible'


def native_release_target(q, candidate):
    """Only actual MusicBrainz recording/release pairs may enter Picard's album window."""
    ok, why = eligible(q, candidate)
    if not ok:
        raise UnsafeCandidate(why)
    if candidate.get('source') != 'musicbrainz':
        raise UnsafeCandidate('Nur MusicBrainz darf native Release-MBIDs liefern.')
    release = one(candidate.get('release_mbid')).lower()
    recording = one(candidate.get('recording_mbid')).lower()
    if not is_uuid(release) or not is_uuid(recording):
        raise UnsafeCandidate('Kein nachgewiesenes MusicBrainz-Release/Recording-Paar.')
    if q.get('recording_mbid') and q['recording_mbid'].lower() != recording:
        raise UnsafeCandidate('Recording-MBID stimmt nicht mit Datei überein.')
    if norm(q.get('albumartist')) and norm(candidate.get('albumartist')) == 'various artists' and norm(q['albumartist']) != 'various artists':
        raise UnsafeCandidate('Release-Albumkünstler widerspricht dem Original.')
    return release, recording


def tag_proposal(q, candidate):
    """Build an explicit override delta; never manufacture external release IDs."""
    ok, why = eligible(q, candidate)
    if not ok:
        raise UnsafeCandidate(why)
    new = {'title': one(candidate['title']), 'artist': one(candidate['artist'])}
    if candidate.get('album'):
        new['album'] = one(candidate['album'])
    # Preserve preexisting albumartist unless the verified MB release names
    # the same artist, or the original albumartist is absent.
    existing = one(q.get('albumartist'))
    src_albumartist = one(candidate.get('albumartist'))
    if src_albumartist and norm(src_albumartist) not in INVALID_ARTISTS:
        if candidate.get('source') == 'musicbrainz' and (
            not existing or norm(src_albumartist) == norm(existing) or
            (norm(existing) == 'various artists' and
             norm(src_albumartist) == norm(candidate['artist']) and
             is_uuid(candidate.get('release_mbid')))):
            new['albumartist'] = src_albumartist
        elif candidate.get('source') != 'musicbrainz' and (
            norm(src_albumartist) == norm(existing) or
            (not existing and norm(src_albumartist) == norm(candidate['artist'])
             and norm(src_albumartist) != 'various artists')):
            # Apply an independently catalogued album artist only where it is
            # compatible with existing credits; never turn solo releases into
            # Various Artists or a platform name.
            new['albumartist'] = src_albumartist
    elif existing:
        pass
    elif norm(candidate['artist']) != 'various artists':
        new['albumartist'] = one(candidate['artist'])
    if q.get('albumartist') and norm(q['albumartist']) != 'various artists':
        if norm(new.get('albumartist')) == 'various artists':
            raise UnsafeCandidate('Various-Artists-Konflikt.')
    isrc = one(candidate.get('isrc')).upper()
    if isrc and ISRC_RE.fullmatch(isrc):
        new['isrc'] = isrc
    if candidate.get('source') == 'musicbrainz':
        if is_uuid(candidate.get('recording_mbid')):
            new['musicbrainz_recordingid'] = one(candidate['recording_mbid'])
        if is_uuid(candidate.get('release_mbid')):
            new['musicbrainz_albumid'] = one(candidate['release_mbid'])
    # Preserve the provider's actually returned track/release metadata.
    # These are *ordinary Picard tags*, never invented recording or release IDs.
    # Unknown or incomplete values are not used to erase existing tags.
    for key in ('tracknumber','discnumber','totaltracks','totaldiscs'):
        raw=one(candidate.get(key))
        if raw.isascii() and raw.isdigit() and 0 < int(raw) < (10000 if key=='totaltracks' else 1000):
            new[key]=str(int(raw))
    date=one(candidate.get('release_date'))
    if re.fullmatch(r'(?:19|20|21)\d\d(?:-(?:0[1-9]|1[0-2])(?:-(?:0[1-9]|[12]\d|3[01]))?)?',date):
        new['date']=date
    original=one(candidate.get('originaldate'))
    if re.fullmatch(r'(?:19|20|21)\d\d(?:-(?:0[1-9]|1[0-2])(?:-(?:0[1-9]|[12]\d|3[01]))?)?',original):
        new['originaldate']=original
    for key in ('genre','label','composer'):
        value=one(candidate.get(key))
        if value and norm(value) not in INVALID_ARTISTS:
            new[key]=value
    barcode=one(candidate.get('barcode'))
    if re.fullmatch(r'\d{8}|\d{12,14}',barcode):
        new['barcode']=barcode
    # No source_name or external provider URL is EVER mapped into an artist tag.
    return new


def changes_for(original, proposal):
    return {k: (one(original.get(k)), v) for k, v in proposal.items() if one(original.get(k)) != v}


def media_backup(path, backup_root=None):
    """Create a verified, unique offline copy before writing ANY tags.

    No access to an existing backup can be overwritten. Backups are outside
    the music directory to avoid Picard accidentally importing duplicates.
    """
    src = Path(path)
    if not src.is_file() or src.is_symlink():
        raise UnsafeCandidate('Originaldatei nicht lesbar oder symbolischer Link.')
    app = os.environ.get('LOCALAPPDATA')
    if backup_root is None:
        if not app:
            raise UnsafeCandidate('LOCALAPPDATA fehlt; sicherer Backup-Pfad nicht bekannt.')
        backup_root = Path(app) / 'NEOWULF' / 'PicardWulf-v1.0' / 'Audio-Backups'
    root = Path(backup_root)
    root.mkdir(parents=True, exist_ok=True)
    stat = src.stat()
    # Preflight enough space before opening the backup.
    if shutil.disk_usage(root).free < stat.st_size + 16 * 1024 * 1024:
        raise UnsafeCandidate('Nicht genug freier Speicherplatz für eine vollständige Sicherung.')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    digest = hashlib.sha256(str(src.absolute()).encode('utf8')).hexdigest()[:14]
    target = root / (stamp + '-' + digest + '-' + uuid.uuid4().hex[:8] + '-' + src.name)
    # Create exclusively and verify exact hash; never silently reuse backup.
    src_hash = hashlib.sha256()
    dest_hash = hashlib.sha256()
    try:
        with src.open('rb') as inp, target.open('xb') as out:
            while block := inp.read(1024 * 1024):
                src_hash.update(block)
                dest_hash.update(block)
                out.write(block)
            out.flush()
            os.fsync(out.fileno())
        shutil.copystat(src, target)
        if target.stat().st_size != stat.st_size or src_hash.digest() != dest_hash.digest():
            raise UnsafeCandidate('Audio-Backup nicht vollständig.')
        if src.stat().st_size != stat.st_size or src.stat().st_mtime_ns != stat.st_mtime_ns:
            raise UnsafeCandidate('Quelldatei wurde während der Sicherung geändert.')
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return target


def backup_envelope(path):
    """Worker-only full-audio receipt, independently hash checked."""
    source=Path(path)
    before=source.stat()
    target=media_backup(path)
    # Re-read BOTH sides after the copy; a replace/mutation of the backup
    # between media_backup() and manifest creation must not certify different
    # audio bytes as a good backup. This happens on the worker only.
    digest=hashlib.sha256()
    original_digest=hashlib.sha256()
    with target.open('rb') as handle:
        for block in iter(lambda:handle.read(1024*1024),b''):
            digest.update(block)
    with source.open('rb') as handle:
        for block in iter(lambda:handle.read(1024*1024),b''):
            original_digest.update(block)
    if digest.digest()!=original_digest.digest():
        raise UnsafeCandidate('Sicherungsdatei und Original haben unterschiedliche Prüfsummen.')
    after=source.stat()
    if (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)!=(
            after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns):
        raise UnsafeCandidate('Original während der Hintergrundsicherung geändert.')
    if target.stat().st_size!=before.st_size:
        raise UnsafeCandidate('Backup-Größe während der Verifizierung verändert.')
    receipt={'path': str(path), 'backup': str(target),
             'size':before.st_size,'mtime_ns':before.st_mtime_ns,
             'dev':before.st_dev,'inode':before.st_ino,
             'sha256':digest.hexdigest(),'schema':1}
    # Durable proof survives Picard crashes/reloads. The manifest is adjacent
    # to the uniquely named, non-overwritten backup OUTSIDE the music folder.
    # It contains paths and checksum only, never OAuth/API secrets or tags.
    manifest=target.with_name(target.name+'.receipt.json')
    with manifest.open('x',encoding='utf8') as f:
        json.dump(receipt,f,ensure_ascii=False,sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    receipt['manifest']=str(manifest)
    return receipt
