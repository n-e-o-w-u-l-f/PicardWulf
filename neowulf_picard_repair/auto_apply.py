"""Qt-thread-only automatic application of the best cross-provider release.

Background workers write only the result store. Files/Picard/Qt objects are
accessed on Picard's GUI thread via a single QTimer. Automatic disk saves are
OFF by default and require a separately confirmed option and full audio backup.
"""
from dataclasses import dataclass
import time
import weakref

from .native_workflow import UnsafeCandidate, changes_for, media_backup, tag_proposal
from .universal_engine import clean_track, query_key


@dataclass
class Watch:
    file_ref: object
    query: dict
    key: str
    added: float


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
    if q.get('recording_mbid') and candidate.get('source')!='musicbrainz':
        raise UnsafeCandidate('MusicBrainz-Recording bereits gesetzt; Fremdquelle benötigt Bestätigung.')
    if not candidate.get('album'):
        raise UnsafeCandidate('Release-Album fehlt.')
    proposal=tag_proposal(q,candidate)
    return candidate,proposal


def apply_best_to_file(file, q, result, *, save=False, backup_func=media_backup):
    """Only call from the GUI thread. No write occurs until backup succeeds."""
    candidate,proposal=proposal_for_auto(q,result)
    md=getattr(file,'metadata',None)
    if md is None:
        raise UnsafeCandidate('Keine Picard-Dateimetadaten.')
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
        backup=backup_func(file.filename)
    else:
        backup=None
    # Keep old metadata to roll back synchronous failure.
    from picard.plugin3.api import Metadata
    original=Metadata()
    original.copy(md)
    try:
        for key,value in proposal.items():
            md[key]=value
        for key in clear_mbid:
            del md[key]
        # Private/internal Picard fields do not rewrite artist or albumartist.
        md['~picardwulf_source']=candidate['source']
        md['~picardwulf_score']=str(round(100*candidate['release_score'],2))
        md['~picardwulf_release']=candidate['album']
        file.update()
        if backup is not None:
            file.save()  # Picard asynchronous; success is NOT yet confirmed.
    except Exception:
        md.copy(original)
        file.update()
        raise
    return {'source':candidate['source'],'score':candidate['release_score'],
            'album':candidate['album'],'changes':changes,'backup':str(backup) if backup else None,
            'save_started':backup is not None}


class AutoApplyController:
    """One timer for all files, no threads touching mutable Picard objects."""

    def __init__(self, api, engine, snapshot_func):
        from PyQt6.QtCore import QTimer
        self.api=api
        self.engine=engine
        self.snapshot_func=snapshot_func
        self.watches={}
        self.done=set()
        self.stopped=False
        self.timer=QTimer(api.tagger)
        self.timer.setInterval(1400)
        self.timer.timeout.connect(self.poll)
        self.timer.start()

    def watch(self,file,metadata):
        if self.stopped:return
        q=clean_track(metadata)
        if q is None:return
        path=getattr(file,'filename',None)
        if not path or path in self.done:return
        try:ref=weakref.ref(file)
        except TypeError:
            return  # never retain unbounded strong references to Picard files
        self.watches[path]=Watch(ref,q,query_key(q),time.monotonic())

    def poll(self):
        if self.stopped:return
        if not self.api.plugin_config.get('auto_apply_best',True):
            return
        for path,watch in list(self.watches.items())[:24]:
            file=watch.file_ref()
            if file is None or time.monotonic()-watch.added>3600:
                self.watches.pop(path,None)
                continue
            if getattr(file,'filename',None)!=path:
                self.watches.pop(path,None)
                continue
            # When Picard itself loads an MB release, it can change file
            # metadata while providers are still querying. The original tags
            # remain our query reference; an MBID newly added by Picard is
            # recognizable. Without a native MBID, protect concurrent edits.
            current=self.snapshot_func(file)
            current_q=clean_track(current) if current is not None else None
            if current_q is None:
                self.watches.pop(path,None)
                continue
            if query_key(current_q)!=watch.key and not (
                current_q.get('recording_mbid') and not watch.query.get('recording_mbid')
            ):
                self.watches.pop(path,None)
                continue
            if current is not None and current.get('~picardwulf_source',''):
                self.watches.pop(path,None)
                continue
            result=self.engine.store.get_result(watch.key)
            if result is None:continue
            self.watches.pop(path,None)
            self.done.add(path)
            try:
                save=bool(self.api.plugin_config.get('auto_save_with_backup',False))
                report=apply_best_to_file(file,watch.query,result['payload'],save=save)
            except UnsafeCandidate as exc:
                self.api.logger.info('PicardWulf auto: review required (%s)', str(exc))
            except Exception as exc:
                self.api.logger.error('PicardWulf auto failure: %s',type(exc).__name__)
            else:
                self.api.logger.info(
                    'PicardWulf winner: source=%s album=%s score=%.2f save_started=%s',
                    report['source'],report['album'],report['score'],report['save_started'])

    def stop(self):
        self.stopped=True
        self.timer.stop()
        self.watches.clear()
        self.done.clear()
