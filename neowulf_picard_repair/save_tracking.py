"""S4 Picard save receipts: post-save event + off-GUI disk verification.

An asynchronous File.save() call is NOT a successful disk write. A successful
post-save processor event is a completion signal, not independent verification.
Backups remain untouched on success, failure, timeout, or plugin disable.
"""
from collections import deque
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import threading
import time
import weakref

from .native_workflow import UnsafeCandidate


def _sha256(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as inp:
        for block in iter(lambda:inp.read(1024*1024),b''):
            digest.update(block)
    return digest.hexdigest()


def check_backup_receipt(backup, source_path):
    """Pure receipt validation, never reads a music file on the GUI thread."""
    if not isinstance(backup,dict) or backup.get('path')!=str(source_path):
        raise UnsafeCandidate('Hintergrundsicherung gehört nicht zur gewählten Originaldatei.')
    if not isinstance(backup.get('backup'),str) or not backup['backup']:
        raise UnsafeCandidate('Backup-Pfad fehlt.')
    digest=backup.get('sha256','')
    if not isinstance(digest,str) or len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):
        raise UnsafeCandidate('SHA-256-Quittung der Audiosicherung fehlt.')
    for key in ('size','mtime_ns'):
        value=backup.get(key)
        if not isinstance(value,int) or isinstance(value,bool) or value<0:
            raise UnsafeCandidate('Backup-Identitätsnachweis unvollständig.')
    return True


def verify_pre_save_identity(backup, source_path):
    """Worker-only fail-closed verification immediately before requesting File.save().

    The backup was verified after creation, but the original may have changed
    while a Qt signal waited for delivery. Recheck the persistent identity
    AND the actual bytes on a worker. Do not use this from a GUI callback.
    """
    check_backup_receipt(backup, source_path)
    for key in ('dev', 'inode'):
        value = backup.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise UnsafeCandidate('Datei-Identitätsnachweis fehlt; nicht speichern.')
    source=Path(source_path)
    copy=Path(backup['backup'])
    if not source.is_file() or source.is_symlink():
        raise UnsafeCandidate('Originaldatei fehlt oder ist jetzt ein Link.')
    if not copy.is_file() or copy.is_symlink():
        raise UnsafeCandidate('Audio-Backup fehlt oder ist jetzt ein Link.')
    def identity(stat):
        return stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns
    expected=(backup['dev'],backup['inode'],backup['size'],backup['mtime_ns'])
    if identity(source.stat())!=expected:
        raise UnsafeCandidate('Originaldatei nach Sicherung verändert; nicht speichern.')
    # An unchanged size/timestamp is not proof that the bytes are unchanged.
    if _sha256(source)!=backup['sha256'] or _sha256(copy)!=backup['sha256']:
        raise UnsafeCandidate('Originaldatei oder Backup stimmt nicht mit SHA-256 überein.')
    if identity(source.stat())!=expected:
        raise UnsafeCandidate('Originaldatei während der Nachprüfung verändert.')
    return True


def verify_saved_tags(path, expected, backup):
    """Background ONLY: audio-file existence, independent tag readback, backup hash.

    Easy tag mappings vary by container. An unreadable or unsupported field is
    UNVERIFIED, never a fabricated successful receipt. Different actual values
    are MISMATCH. The original backup is never auto-restored or overwritten.
    """
    try:
        saved=Path(path)
        if not saved.is_file() or saved.is_symlink():
            return {'state':'MISSING','reason':'saved_file_missing'}
        saved_stat=saved.stat()
        if saved_stat.st_size<=0:
            return {'state':'UNVERIFIED','reason':'saved_file_empty'}
        if _sha256(backup['backup'])!=backup['sha256']:
            return {'state':'BACKUP_INVALID','reason':'backup_hash_mismatch'}
        from mutagen import File
        audio=File(str(saved),easy=True)
        if audio is None or audio.tags is None:
            return {'state':'UNVERIFIED','reason':'unsupported_audio_tags'}
        uncertain=[]
        differences=[]
        verified=0
        for key,value in expected.items():
            if key.startswith('~'):continue
            expected_value=str(value).strip()
            if not expected_value:continue
            received=audio.tags.get(key)
            if received is None:
                uncertain.append(key)
                continue
            if isinstance(received,(list,tuple)):
                received=received[0] if received else ''
            actual=str(received).strip()
            if key in ('tracknumber','discnumber','totaltracks','totaldiscs'):
                # EasyID3 frequently stores 3/12 in a single tracknumber field.
                actual=actual.split('/',1)[0]
            if key in ('title','artist','album','albumartist'):
                equal=' '.join(actual.casefold().split())==' '.join(expected_value.casefold().split())
            else:equal=actual==expected_value
            if not equal:differences.append(key)
            else:verified+=1
        if differences:
            return {'state':'MISMATCH','reason':'tag_values_differ','fields':differences}
        if uncertain:
            return {'state':'UNVERIFIED','reason':'tags_not_exposed_by_format','fields':uncertain,
                    'verified_fields':verified}
        if not verified:
            return {'state':'UNVERIFIED','reason':'no_verifiable_fields'}
        return {'state':'VERIFIED','verified_fields':verified}
    except (OSError, ValueError, KeyError, ImportError) as exc:
        return {'state':'UNVERIFIED','reason':type(exc).__name__}


def load_backup_manifest(path):
    """Read an on-disk receipt before a separately confirmed restore."""
    manifest=Path(path)
    if not manifest.is_file() or manifest.is_symlink() or manifest.stat().st_size>4096:
        raise UnsafeCandidate('Sicherungsbeleg ist nicht lesbar oder unsicher.')
    try:
        data=json.loads(manifest.read_text(encoding='utf8'))
    except (ValueError,UnicodeError,OSError):
        raise UnsafeCandidate('Sicherungsbeleg ist beschädigt.') from None
    if not isinstance(data,dict) or data.get('schema')!=1:
        raise UnsafeCandidate('Unbekanntes Sicherungsbeleg-Format.')
    check_backup_receipt(data,data.get('path'))
    if manifest.name!=Path(data['backup']).name+'.receipt.json':
        raise UnsafeCandidate('Backup-Beleg passt nicht zur Sicherungsdatei.')
    if Path(data['backup']).parent.resolve()!=manifest.parent.resolve():
        raise UnsafeCandidate('Backup-Beleg liegt nicht bei der Sicherungsdatei.')
    return data


def restore_from_manifest(manifest,new_destination):
    """Worker-only: verify persistent backup and make an exclusive new copy."""
    receipt=load_backup_manifest(manifest)
    return restore_backup_copy(receipt,new_destination)


def restore_backup_copy(backup, new_destination):
    """Worker-only restoration to a NEW pathname, never overwrite an original.

    This is an explicit recovery primitive, not an automatic rollback.
    Validate the immutable receipt's backup digest before creating anything.
    Use exclusive creation; delete only the incomplete new destination.
    """
    if not isinstance(backup,dict) or not isinstance(backup.get('sha256'),str) or (
            len(backup['sha256'])!=64):
        raise UnsafeCandidate('Kein verifizierbarer Backup-Beleg.')
    source=Path(backup['backup'])
    destination=Path(new_destination)
    if not source.is_file() or source.is_symlink():
        raise UnsafeCandidate('Gesicherte Audiodatei nicht mehr vorhanden.')
    if destination.exists() or destination.is_symlink():
        raise UnsafeCandidate('Wiederherstellung darf keine Datei überschreiben.')
    if source.resolve()==destination.resolve():
        raise UnsafeCandidate('Ziel entspricht der Sicherungsdatei.')
    if _sha256(source)!=backup['sha256']:
        raise UnsafeCandidate('Backup-SHA-256 stimmt nicht überein.')
    if source.stat().st_size!=backup.get('size'):
        raise UnsafeCandidate('Backup-Größe stimmt nicht überein.')
    if not destination.parent.is_dir() or destination.parent.is_symlink():
        raise UnsafeCandidate('Wiederherstellungsordner muss existieren.')
    written=False
    try:
        with source.open('rb') as incoming, destination.open('xb') as outgoing:
            written=True
            copied=hashlib.sha256()
            for block in iter(lambda:incoming.read(1024*1024),b''):
                copied.update(block)
                outgoing.write(block)
            outgoing.flush()
            os.fsync(outgoing.fileno())
        if copied.hexdigest()!=backup['sha256']:
            raise UnsafeCandidate('Kopie hat andere Prüfsumme; neue Datei wird entfernt.')
    except Exception:
        if written:
            destination.unlink(missing_ok=True)
        raise
    return {'state':'RESTORED_COPY','path':str(destination),
            'sha256':backup['sha256'],'size':destination.stat().st_size}


class SaveTracker:
    """State machine; File/Qt objects stay on Picard callback thread."""

    def __init__(self, max_pending=32, save_timeout=600):
        self._lock=threading.RLock()
        self._pending={}
        self._last=deque(maxlen=80)
        self._pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='PicardWulf-TagReadback')
        self._closed=False
        self._verifying=0
        self._restoring=0
        self.max_pending=max_pending
        self.save_timeout=save_timeout

    def register(self,file,backup,expected):
        check_backup_receipt(backup,getattr(file,'filename',None))
        if not isinstance(expected,dict) or not expected:
            raise UnsafeCandidate('Keine Tag-Änderungen für Nachprüfung vorhanden.')
        key=id(file)
        with self._lock:
            if self._closed or len(self._pending)>=self.max_pending or key in self._pending:
                raise UnsafeCandidate('Ein Speichervorgang läuft bereits oder die Prüfung ist ausgelastet.')
            entry={'ref':weakref.ref(file),'path':str(file.filename),
                   'backup':dict(backup),'expected':{str(k):str(v) for k,v in expected.items()},
                   'started':time.monotonic()}
            self._pending[key]=entry
        return key

    def abort(self,file,key):
        with self._lock:
            if self._pending.get(key,{}).get('ref',lambda:None)() is file:
                entry=self._pending.pop(key)
                self._last.append({'state':'START_FAILED','backup':entry['backup']['backup']})

    def post_save(self,file):
        """Picard v3 callback: invoked ONLY after Picard reports file saved."""
        key=id(file)
        with self._lock:
            entry=self._pending.get(key)
            if entry is None or entry['ref']() is not file:return False
            self._pending.pop(key)
            path=str(getattr(file,'filename',''))
            if not path:
                self._last.append({'state':'UNVERIFIED','reason':'missing_destination',
                                   'backup':entry['backup']['backup']})
                return True
            self._last.append({'state':'VERIFYING','backup':entry['backup']['backup']})
            self._verifying+=1
        # No disk I/O or metadata traversal on the callback thread.
        try:
            future=self._pool.submit(verify_saved_tags,path,entry['expected'],entry['backup'])
        except RuntimeError:
            with self._lock:
                self._verifying-=1
                self._last.append({'state':'UNVERIFIED','reason':'verification_worker_stopped',
                                   'backup':entry['backup']['backup']})
            return True
        future.add_done_callback(lambda task,b=entry['backup']['backup']:self._completed(task,b))
        return True

    def _completed(self,future,backup):
        try:result=future.result()
        except Exception as exc:result={'state':'UNVERIFIED','reason':type(exc).__name__}
        with self._lock:
            self._verifying-=1
            self._last.append(dict(result,backup=backup))

    def request_restore(self, manifest, new_destination):
        """Non-blocking request after explicit operator confirmation in UI."""
        with self._lock:
            if self._closed or self._restoring:
                raise UnsafeCandidate('Wiederherstellung ist gerade nicht verfügbar.')
            if not manifest or not new_destination:
                raise UnsafeCandidate('Sicherungsbeleg und neuer Zielpfad erforderlich.')
            self._restoring+=1
            self._last.append({'state':'RESTORE_PENDING'})
        try:
            future=self._pool.submit(restore_from_manifest,str(manifest),str(new_destination))
        except RuntimeError:
            with self._lock:self._restoring-=1
            raise UnsafeCandidate('Wiederherstellungs-Worker ist gestoppt.') from None
        future.add_done_callback(self._restore_completed)
        return True

    def _restore_completed(self,future):
        try:result=future.result()
        except Exception as exc:result={'state':'RESTORE_REJECTED','reason':type(exc).__name__}
        with self._lock:
            self._restoring-=1
            self._last.append(result)

    def status(self):
        with self._lock:
            now=time.monotonic()
            for key,entry in list(self._pending.items()):
                if now-entry['started']>self.save_timeout:
                    self._last.append({'state':'UNKNOWN_TIMEOUT','backup':entry['backup']['backup']})
                    del self._pending[key]
            return {'pending':len(self._pending),
                    'verifying':self._verifying,
                    'restoring':self._restoring,
                    'recent':list(self._last)[-12:]}

    def close(self):
        with self._lock:
            self._closed=True
            for entry in self._pending.values():
                self._last.append({'state':'UNKNOWN_AFTER_DISABLE',
                                   'backup':entry['backup']['backup']})
            self._pending.clear()
        self._pool.shutdown(wait=False,cancel_futures=False)
