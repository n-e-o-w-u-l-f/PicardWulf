"""Qt-thread-only automatic application of the best cross-provider release.

Background workers write only the result store. Files/Picard/Qt objects are
accessed on Picard's GUI thread via a single QTimer. Automatic disk saves are
OFF by default and require a separately confirmed option and full audio backup.
"""
from dataclasses import dataclass
from collections import deque
import json
import time
import weakref

from .native_workflow import UnsafeCandidate, changes_for, tag_proposal
from .background_io import create_gui_io
from .universal_engine import clean_track, query_key


@dataclass
class Watch:
    file_ref: object
    query: dict
    key: str
    added: float
    identity: int
    baseline: str
    admitted: bool = False
    force: bool = False


def proposal_for_auto(q, result):
    """Pure decision gate: no MusicBrainz priority; respect source winner."""
    decision = result.get('auto') or {}
    if decision.get('state') != 'ready':
        raise UnsafeCandidate(decision.get('reason','Keine eindeutige Release-Zuordnung.'))
    candidate = decision.get('candidate')
    if not isinstance(candidate,dict):
        raise UnsafeCandidate('Gewinnerdaten fehlen.')
    # Existing recording ID must not be re-credited to an unrelated streaming
    # release. Keep the previous MB assignment for explicit manual review.
    if (q.get('recording_mbid') or q.get('release_mbid')) and candidate.get('source')!='musicbrainz':
        raise UnsafeCandidate('MusicBrainz-Recording bereits gesetzt; Fremdquelle benötigt Bestätigung.')
    if not candidate.get('album'):
        raise UnsafeCandidate('Release-Album fehlt.')
    proposal=tag_proposal(q,candidate)
    # Existing disc/track position may describe a different edition. A
    # competing provider can STILL win ranking; conflicting positions require
    # human review instead of silent auto-application.
    for key in ('tracknumber','discnumber'):
        original=str(q.get(key) or '').strip()
        proposed=proposal.get(key,'')
        if original and proposed and original!=proposed:
            raise UnsafeCandidate('Widersprüchliche %s – Edition manuell prüfen.' % key)
    # Do not erase/overwrite locally curated optional fields merely because
    # a catalogue has a different genre, label or composer spelling.
    for key in ('genre','label','composer','barcode','date','originaldate'):
        original=str(q.get(key) or '').strip()
        if original and key in proposal and original.casefold()!=str(proposal[key]).casefold():
            proposal.pop(key)
    return candidate,proposal


def apply_best_to_file(file, q, result, *, save=False, verified_backup=None, save_tracker=None):
    """Only call from the GUI thread. No write occurs until backup succeeds."""
    candidate,proposal=proposal_for_auto(q,result)
    md=getattr(file,'metadata',None)
    if md is None:
        raise UnsafeCandidate('Keine Picard-Dateimetadaten.')
    from .auto_selection import decision_identity, MODEL
    decision_key=decision_identity(candidate)
    previous=md.get('~picardwulf_decision','')
    if previous and previous!=decision_key:
        raise UnsafeCandidate('Späterer Release-Konflikt: feste Entscheidung bleibt erhalten; Prüfung erforderlich.')
    if previous:
        raise UnsafeCandidate('Release-Entscheidung bereits angewendet; keine erneute Übernahme.')
    changes=changes_for(md,proposal)
    # Picard may have filled in a native MBID after Add Folder while other
    # providers were still searching. That ID does not describe the selected
    # external catalogue release. Clear only IDs introduced *after* the
    # original disk snapshot; a preexisting MBID requires manual review.
    clear_mbid=[]
    if candidate.get('source')!='musicbrainz' and not q.get('recording_mbid'):
        for field in ('musicbrainz_albumid','musicbrainz_recordingid'):
            if md.get(field):
                clear_mbid.append(field)
                changes[field]=(str(md[field]),'[remove stale MusicBrainz assignment]')
    if save and changes:
        if not getattr(file,'can_save',True) or not getattr(file,'can_edit_tags',True):
            raise UnsafeCandidate('Datei nicht beschreibbar.')
        from .save_tracking import check_backup_receipt
        check_backup_receipt(verified_backup,file.filename)
        if save_tracker is None:
            raise UnsafeCandidate('Picard Post-Save-Prüfung nicht verfügbar.')
        backup=verified_backup['backup']
    else:
        backup=None
    # Keep old metadata to roll back synchronous failure.
    from picard.plugin3.api import Metadata
    original=Metadata()
    original.copy(md)
    save_token=None
    try:
        for key,value in proposal.items():
            md[key]=value
        for key in clear_mbid:
            del md[key]
        # Private/internal Picard fields do not rewrite artist or albumartist.
        md['~picardwulf_source']=candidate['source']
        md['~picardwulf_score']=str(round(100*candidate['release_score'],2))
        md['~picardwulf_score_kind']='matching_points'
        md['~picardwulf_model']=MODEL
        md['~picardwulf_decision']=decision_key
        md['~picardwulf_release']=candidate['album']
        file.update()
        if backup is not None:
            save_token=save_tracker.register(file,verified_backup,proposal)
            file.save()  # Picard asynchronous; completion requires post-save event.
    except Exception:
        if save_token is not None:
            save_tracker.abort(file,save_token)
        md.copy(original)
        file.update()
        raise
    return {'source':candidate['source'],'score':candidate['release_score'],
            'album':candidate['album'],'changes':changes,'backup':str(backup) if backup else None,
            'save_started':backup is not None}


class AutoApplyController:
    """One timer for all files, no threads touching mutable Picard objects."""

    def __init__(self, api, engine, snapshot_func, ingest_snapshot_func=None, save_tracker=None):
        from PyQt6.QtCore import QTimer
        self.api=api
        self.engine=engine
        self.snapshot_func=snapshot_func
        self.ingest_snapshot_func=ingest_snapshot_func or snapshot_func
        self.watches={}
        self.done=set()
        self._round_robin=deque()
        self._backup_wait=None
        self._refresh_iterator=None
        self._refresh_force=False
        self.io=create_gui_io(api.tagger, engine)
        self.save_tracker=save_tracker
        self.stopped=False
        self.timer=QTimer(api.tagger)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self.poll)
        self.timer.start()

    def watch(self,file,metadata,force=False):
        if self.stopped:return
        q=clean_track(metadata)
        if q is None:return
        path=getattr(file,'filename',None)
        identity=(path,id(file))
        if not path or (identity in self.done and not force):return
        if force:
            self.done.discard(identity)
            self.io.invalidate(query_key(q))
        try:ref=weakref.ref(file)
        except TypeError:
            return  # never retain unbounded strong references to Picard files
        if identity not in self.watches:self._round_robin.append(identity)
        baseline=json.dumps(dict(getattr(file,'metadata',{})),sort_keys=True)
        admitted=self.engine.schedule_async(q,force=force)
        self.watches[identity]=Watch(ref,q,query_key(q),time.monotonic(),id(file),baseline,admitted,force)

    def refresh(self, files, force=False):
        self._refresh_iterator=iter(files)
        self._refresh_force=force

    def poll(self):
        if self.stopped:return
        self._finish_backup()
        if self._refresh_iterator is not None:
            for _ in range(16):
                try:file=next(self._refresh_iterator)
                except StopIteration:
                    self._refresh_iterator=None
                    break
                snapshot=self.snapshot_func if self._refresh_force else self.ingest_snapshot_func
                metadata=snapshot(file)
                if metadata is not None:self.watch(file,metadata,force=self._refresh_force)
        # Retry overflow through weak file identities, even while search is
        # paused. Pause affects dispatch, never durability of newly added files.
        selected=[]
        for _ in range(min(32,len(self._round_robin))):
            identity=self._round_robin.popleft()
            watch=self.watches.get(identity)
            if watch is None:continue
            selected.append(identity)
            self._round_robin.append(identity)
        expired=[]
        keys=[]
        for identity in selected:
            path,_=identity
            watch=self.watches.get(identity)
            if watch is None:continue
            file=watch.file_ref()
            if file is None or getattr(file,'filename',None)!=path or id(file)!=watch.identity:
                expired.append(identity)
            else:
                if not watch.admitted:
                    watch.admitted=self.engine.schedule_async(watch.query,force=watch.force)
                keys.append(watch.key)
        for identity in expired:self.watches.pop(identity,None)
        self.io.read(keys)
        if self.engine.paused or not self.api.plugin_config.get('auto_apply_best',True):return
        completed=self.io.results
        for identity in selected:
            path,_=identity
            watch=self.watches.get(identity)
            if watch is None:continue
            result=completed.get(watch.key) if watch.admitted else None
            if result is None:continue
            file=watch.file_ref()
            if file is None:
                self.watches.pop(identity,None)
                continue
            # Picard may have loaded a MusicBrainz release during the request.
            # Protect unrelated live edits, permit recognizably introduced MBIDs.
            current=self.snapshot_func(file)
            current_q=clean_track(current) if current is not None else None
            if current_q is None:
                self.watches.pop(identity,None)
                continue
            compatible=dict(current_q)
            compatible['recording_mbid']=watch.query.get('recording_mbid','')
            compatible['release_mbid']=watch.query.get('release_mbid','')
            if query_key(current_q)!=watch.key and query_key(compatible)!=watch.key:
                self.watches.pop(identity,None)
                continue
            baseline=json.loads(watch.baseline)
            live=dict(file.metadata)
            for field in ('musicbrainz_recordingid','musicbrainz_albumid'):
                if field not in baseline:live.pop(field,None)
            if json.dumps(live,sort_keys=True)!=watch.baseline:
                self.watches.pop(identity,None)
                continue
            if current is not None and current.get('~picardwulf_source',''):
                from .auto_selection import decision_identity
                decision=result['payload'].get('auto',{})
                previous=file.metadata.get('~picardwulf_decision','')
                candidate=decision.get('candidate')
                if previous and decision.get('state') in ('ready','review','ambiguous','no_match') and (
                                  decision.get('state')!='ready' or not candidate or
                                  decision_identity(candidate)!=previous):
                    file.metadata['~picardwulf_review']='LATER_RELEASE_CONFLICT'
                    file.update()
                    self.api.logger.info('PicardWulf: spätere Release-Daten benötigen Prüfung; Entscheidung erhalten.')
                self.watches.pop(identity,None)
                continue
            try:
                save=bool(self.api.plugin_config.get('auto_save_with_backup',False))
                proposal_for_auto(watch.query,result['payload'])
                if save:
                    if self._backup_wait is not None:continue
                    token='backup:auto'
                    if not self.io.backup(token,path):continue
                    self._backup_wait=(identity,watch,result,
                                       json.dumps(dict(file.metadata),sort_keys=True))
                    continue
                report=apply_best_to_file(file,watch.query,result['payload'])
            except UnsafeCandidate as exc:
                self.api.logger.info('PicardWulf auto: review required (%s)',str(exc))
            except Exception as exc:
                self.api.logger.error('PicardWulf auto failure: %s',type(exc).__name__)
            else:
                self.api.logger.info(
                    'PicardWulf winner: source=%s album=%s score=%.2f save_started=%s',
                    report['source'],report['album'],report['score'],report['save_started'])
            self.watches.pop(identity,None)
            self.done.add(identity)

    def _finish_backup(self):
        if self._backup_wait is None:return
        receipt=self.io.backups.pop('backup:auto',None)
        if receipt is None:return
        identity,watch,result,baseline=self._backup_wait
        self._backup_wait=None
        file=watch.file_ref()
        if (file is None or self.watches.get(identity) is not watch or
                getattr(file,'filename',None)!=identity[0] or id(file)!=watch.identity or
                json.dumps(dict(file.metadata),sort_keys=True)!=baseline or
                not self.api.plugin_config.get('auto_save_with_backup',False) or
                not self.api.plugin_config.get('auto_apply_best',True)):
            if self.watches.get(identity) is watch:self.watches.pop(identity,None)
            return
        try:
            if 'error' in receipt:raise UnsafeCandidate('Hintergrundsicherung fehlgeschlagen.')
            apply_best_to_file(file,watch.query,result['payload'],save=True,
                               verified_backup=receipt['value'],save_tracker=self.save_tracker)
        except Exception as exc:
            self.api.logger.warning('PicardWulf backup/save: %s',type(exc).__name__)
        self.watches.pop(identity,None)
        self.done.add(identity)

    def stop(self):
        self.stopped=True
        self.timer.stop()
        self.io.stop()
        self._backup_wait=None
        self._refresh_iterator=None
        self._round_robin.clear()
        self.watches.clear()
        self.done.clear()
