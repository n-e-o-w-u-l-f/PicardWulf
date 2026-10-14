"""PicardWulf v1.0: native album association and opt-in, backed-up tag saves.

All Qt callbacks run on the Picard UI thread. Background catalogue workers only
write to the SQLite cache; they never touch Picard File, Album or Qt objects.
"""
from .native_workflow import (
    UnsafeCandidate, changes_for, native_release_target, tag_proposal,
)
from .background_io import create_gui_io
import json
import weakref
from .universal_engine import clean_track, query_key
from .universal_adapters import one


def show_native_window(api, aggregator, files, snapshot_func, save_tracker=None):
    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import (
        QAbstractItemView, QComboBox, QDialog, QHBoxLayout, QLabel, QMessageBox,
        QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
    )
    from picard.plugin3.api import Metadata

    files = [f for f in files if getattr(f, 'metadata', None) is not None]
    if not files:
        QMessageBox.information(None, 'PicardWulf 1.0',
            'Keine geladenen Audiodateien. Zuerst über Datei → Ordner hinzufügen laden.')
        return
    dlg = QDialog(None)
    io = create_gui_io(dlg, aggregator)
    pending_save = [None]
    pending_refresh = [None]
    dlg.setWindowTitle('PicardWulf v1.0 – Multi-Source & natives Picard-Matching')
    dlg.resize(1230, 710)
    layout = QVBoxLayout(dlg)
    layout.addWidget(QLabel(
        'Quellen sind Vorschläge. Ein echtes Release wird nur mit bestätigten MusicBrainz-MBIDs '
        'im Picard-Albumfenster geöffnet. Tags werden nur nach Auswahl, Sicherung und Bestätigung geschrieben.'))
    chooser = QComboBox(dlg)
    for index, f in enumerate(files):
        chooser.addItem(one(getattr(f, 'filename', 'Track')), index)
    layout.addWidget(chooser)
    status = QLabel('', dlg)
    layout.addWidget(status)
    cols = ['Quelle', 'Score', 'Titel', 'Interpret', 'Album', 'Albumartist', 'ISRC', 'MB Release-ID', 'Anbieter-Release-ID']
    table = QTableWidget(0, len(cols), dlg)
    table.setHorizontalHeaderLabels(cols)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.horizontalHeader().setStretchLastSection(True)
    layout.addWidget(table)
    buttons=QHBoxLayout()
    refresh = QPushButton('Erneut suchen', dlg)
    native = QPushButton('In Picard-Album zuordnen', dlg)
    preview = QPushButton('Tag-Änderungen ansehen', dlg)
    save = QPushButton('Tags überschreiben + Backup', dlg)
    close = QPushButton('Schließen', dlg)
    for b in (refresh,native,preview,save,close):buttons.addWidget(b)
    layout.addLayout(buttons)

    available=[]
    last_view_signature=[None]
    def current_file():
        idx=chooser.currentData()
        return files[idx] if isinstance(idx,int) and 0 <= idx < len(files) else None

    def selection():
        f=current_file()
        if f is None:raise UnsafeCandidate('Keine Datei gewählt.')
        md=snapshot_func(f)
        q=clean_track(md) if md is not None else None
        if not q:raise UnsafeCandidate('Für diese Datei fehlen Titel und Interpret.')
        row=table.currentRow()
        if row < 0 or row >= len(available):
            raise UnsafeCandidate('Bitte einen konkreten Treffer in der Tabelle auswählen.')
        return f,q,available[row]

    def update_view():
        nonlocal available
        finish_save()
        f=current_file()
        md=snapshot_func(f) if f else None
        q=clean_track(md) if md is not None else None
        if not q:
            available=[]
            table.setRowCount(0)
            status.setText('Keine auswertbaren Metadaten. Eindeutiger Dateiname »Künstler - Titel« wird unterstützt.')
            return
        key=query_key(q)
        if pending_refresh[0] is not None:
            ref,identity,raw=pending_refresh[0]
            owner=ref()
            owner_md=snapshot_func(owner) if owner is not None else None
            owner_q=clean_track(owner_md) if owner_md is not None else None
            if owner is None or (str(owner.filename),id(owner))!=identity or owner_q!=raw:
                pending_refresh[0]=None
            elif aggregator.schedule_async(raw,force=True):
                pending_refresh[0]=None
        io.read([key])
        waiting=(pending_refresh[0] is not None and query_key(pending_refresh[0][2])==key)
        data=io.results.get(key) if not waiting else None
        if not data:aggregator.schedule_async(md)
        signature=(chooser.currentIndex(),data['updated'] if data else None)
        if last_view_signature[0]==signature:return
        last_view_signature[0]=signature
        available=[]
        table.setRowCount(0)
        if not data:
            aggregator.schedule_async(md)
            status.setText('Suche läuft im Hintergrund. Ergebnisse werden automatisch aktualisiert.')
            return
        payload=data['payload']
        available=[v for v in payload.get('candidates',[]) if v.get('release_score',v.get('score',0))>0]
        table.setRowCount(len(available))
        for j,c in enumerate(available):
            vals=(c.get('source',''),f'{100*c.get("release_score",c.get("score",0)):.1f}%',c.get('title',''),
                  c.get('artist',''),c.get('album',''),c.get('albumartist',''),
                  c.get('isrc',''),c.get('release_mbid',''),c.get('provider_album_id',''))
            for k,v in enumerate(vals):
                table.setItem(j,k,QTableWidgetItem(str(v)))
        table.resizeColumnsToContents()
        by_source=', '.join(f'{name}:{state}' for name,state in payload.get('status',{}).items())
        auto=payload.get('auto') or {}
        best=auto.get('candidate') or (available[0] if available else {})
        best_summary=(f'Gewinner: {best.get("source","-")} / {best.get("album","-")} '
                      f'({100*best.get("release_score",best.get("score",0)):.1f} %) · '
                      f'Auto: {auto.get("state","offen")}')
        status.setText(f'{best_summary} · {len(available)} Treffer · {by_source}')

    def warn(err):
        QMessageBox.warning(dlg,'PicardWulf – keine Änderung',str(err))

    def start_refresh():
        if pending_refresh[0] is not None:
            warn('Die letzte erneute Suche wartet noch auf Platz in der Warteschlange.');return
        f=current_file()
        md=snapshot_func(f) if f else None
        if md is None:warn('Keine Dateimetadaten gefunden.');return
        q=clean_track(md)
        if q is None:warn('Titel oder Interpret fehlen.');return
        key=query_key(q)
        io.invalidate(key)
        if not aggregator.schedule_async(q,force=True):
            pending_refresh[0]=(weakref.ref(f),(str(f.filename),id(f)),q)
        else:
            pending_refresh[0]=None
        last_view_signature[0]=None
        table.setRowCount(0)
        status.setText('Neue Abfragen werden ausgeführt. Ergebnisse folgen über die Warteschlange.')

    def native_match():
        try:
            f,q,c=selection()
            release,recording=native_release_target(q,c)
            answer=QMessageBox.question(dlg,'PicardWulf – in Albumfenster zuordnen',
                f'Künstler: {c.get("artist", "")}\nTitel: {c.get("title", "")}\n'
                f'Album: {c.get("album", "")}\nMusicBrainz Release: {release}\n'
                f'Recording: {recording}\n\nDie Datei wird in Picards Albumfenster '
                'zu diesem nachgewiesenen MusicBrainz-Release zugeordnet.\n'
                'Noch KEINE Audiodatei speichern?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:return
            api.tagger.move_file_to_track(f, release, recording)
            QMessageBox.information(dlg,'PicardWulf – Albumzuordnung',
                'MusicBrainz-Release wird im nativen Picard-Albumfenster geladen. '
                'Das Matching erfolgt durch Picard; Tags wurden nicht gespeichert.')
        except Exception as e:
            api.logger.warning('Native release matching: %s',type(e).__name__)
            warn(e)

    def proposed():
        f,q,c=selection()
        proposal=tag_proposal(q,c)
        diffs=changes_for(f.metadata,proposal)
        if not diffs:
            raise UnsafeCandidate('Alle vorgeschlagenen Tags stimmen bereits überein.')
        txt='\n'.join(f'{k}: {old or "[leer]"}  →  {new}' for k,(old,new) in diffs.items())
        return f,q,c,proposal,diffs,txt

    def inspect():
        try:
            f,q,c,proposed_changes,diffs,txt=proposed()
            QMessageBox.information(dlg,'PicardWulf – Vorschau (keine Änderung)',
                f'Quelle: {c.get("source")} · Score: {100*c.get("score",0):.1f}%\n\n'
                f'{txt}\n\nVorschau: weder Picard-Tags noch Musikdateien geändert.')
        except Exception as e:warn(e)

    def write_with_backup():
        try:
            f,q,c,proposal,diffs,txt=proposed()
            if not getattr(f,'can_save',True) or not getattr(f,'can_edit_tags',True):
                raise UnsafeCandidate('Diese Datei unterstützt kein Tag-Speichern.')
            answer=QMessageBox.question(dlg,'PicardWulf – Tag-Speicherung bestätigen',
                f'{txt}\n\nDiese Tags werden überschrieben. Vorher wird die vollständige '
                'Audiodatei außerhalb des Musikordners gesichert.\n'
                'Picards aktivierte Optionen können die Datei beim Speichern '
                'auch umbenennen oder verschieben.\n\nJetzt sicherungsbasiert speichern?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if answer!=QMessageBox.StandardButton.Yes:return
            if pending_save[0] is not None:
                raise UnsafeCandidate('Eine Hintergrundsicherung läuft bereits.')
            identity=(str(f.filename),id(f),json.dumps(dict(f.metadata),sort_keys=True))
            if not io.backup('backup:manual',f.filename):
                raise UnsafeCandidate('Hintergrundsicherung ist ausgelastet.')
            pending_save[0]=('backup',weakref.ref(f),identity,dict(proposal),None)
            save.setEnabled(False)
            status.setText('Original wird im Hintergrund gesichert. Noch keine Tags geändert.')
        except Exception as e:
            api.logger.warning('Tag save: %s',type(e).__name__)
            warn(e)

    def finish_save():
        if pending_save[0] is None:return
        stage,ref,identity,proposal,backup=pending_save[0]
        token='backup:manual' if stage=='backup' else 'preflight:manual'
        receipt=io.backups.pop(token,None)
        if receipt is None:return
        pending_save[0]=None
        f=ref()
        try:
            if 'error' in receipt:raise UnsafeCandidate('Sicherung/Identitätsprüfung fehlgeschlagen.')
            if (f is None or str(f.filename)!=identity[0] or id(f)!=identity[1] or
                    json.dumps(dict(f.metadata),sort_keys=True)!=identity[2]):
                raise UnsafeCandidate('Datei oder Vorschau inzwischen geändert; nichts gespeichert.')
            from .save_tracking import check_backup_receipt
            if stage=='backup':
                backup=receipt['value']
                check_backup_receipt(backup,f.filename)
                if not io.pre_save_check('preflight:manual',backup,f.filename):
                    raise UnsafeCandidate('Vor-Speicher-Prüfung ist ausgelastet.')
                pending_save[0]=('preflight',ref,identity,proposal,backup)
                status.setText('Backup angelegt; Original und Prüfsummen werden erneut überprüft.')
                return
            if receipt.get('value') is not True:
                raise UnsafeCandidate('Original-Identität nicht bestätigt; nicht speichern.')
            if save_tracker is None:
                raise UnsafeCandidate('Nachprüfung via Picard-Post-Save-Hook nicht verfügbar.')
            old=Metadata()
            old.copy(f.metadata)
            save_token=None
            try:
                save_token=save_tracker.register(f,backup,proposal)
                for field,value in proposal.items():f.metadata[field]=value
                f.update()
                f.save()
            except Exception:
                if save_token is not None:save_tracker.abort(f,save_token)
                f.metadata.copy(old)
                f.update()
                raise
            QMessageBox.information(dlg,'PicardWulf – Speicherung gestartet',
                f'Backup: {backup["backup"]}\n\n'
                'Picard speichert asynchron. Erst der Post-Save-Hook und eine '
                'separate Hintergrundprüfung dürfen einen Erfolg bestätigen. '
                'Die Prüfung ist unter NEOWULF → Tag-Speicherstatus einsehbar.')
        except Exception as exc:warn(exc)
        finally:
            if pending_save[0] is None:save.setEnabled(True)

    chooser.currentIndexChanged.connect(update_view)
    refresh.clicked.connect(start_refresh)
    native.clicked.connect(native_match)
    preview.clicked.connect(inspect)
    save.clicked.connect(write_with_backup)
    close.clicked.connect(dlg.reject)
    timer=QTimer(dlg)
    timer.timeout.connect(update_view)
    timer.start(3500)
    update_view()
    dlg.exec()
    timer.stop()
    io.stop()
