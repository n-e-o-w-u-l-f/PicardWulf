"""Opt-in multi-source similar-album discovery for Picard 3 context menus.

Does not replace the native MusicBrainz-only Lookup command. Never performs
network/media/SQLite I/O on the GUI thread; only schedules bounded work and
reads already delivered immutable result envelopes.
"""
import time

from .background_io import create_gui_io
from .cluster_matching import find_similar_albums, MAX_GROUP_TRACKS
from .native_workflow import UnsafeCandidate
from .universal_engine import clean_track, query_key


def selected_group_files(objs, limit=MAX_GROUP_TRACKS):
    """Bound iteration over selected Picard cluster/album iterfiles objects."""
    result=[]
    seen=set()
    for obj in objs:
        iterator=getattr(obj,'iterfiles',None)
        if callable(iterator):
            stream=iterator()
        else:
            stream=getattr(obj,'files',())
            if isinstance(stream,dict):
                stream=stream.values()
        for file in stream:
            if getattr(file,'metadata',None) is None:
                continue
            identity=id(file)
            if identity in seen:
                continue
            if len(result)>=limit:
                raise UnsafeCandidate('Albumgruppe ist für eine einzelne Suche zu groß (maximal 200 Tracks).')
            seen.add(identity)
            result.append(file)
    if not result:
        raise UnsafeCandidate('Die gewählte Albumgruppe enthält keine geladenen Audiodateien.')
    return result


def show_similar_albums(api, aggregator, files, snapshot_func):
    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import (
        QAbstractItemView, QDialog, QHBoxLayout, QLabel, QMessageBox,
        QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout
    )
    from .native_ui import show_native_window
    queries=[]
    for file in files:
        raw=snapshot_func(file)
        q=clean_track(raw) if raw is not None else None
        if q is None:
            raise UnsafeCandidate('Mindestens einem Album-Track fehlen Interpret oder Titel.')
        queries.append(q)
    if len(files)>MAX_GROUP_TRACKS:
        raise UnsafeCandidate('Die Gruppe überschreitet 200 Tracks.')
    requests={}
    for q in queries:
        requests.setdefault(query_key(q),q)
    # Capture before submissions: old album-cache hits are not a current
    # multi-provider comparison; the user explicitly requested a new search.
    requested_after=time.time()-0.1
    admission={key:False for key in requests}
    dlg=QDialog(None)
    dlg.setWindowTitle('PicardWulf v1.0 – Ähnliche Alben aus allen Quellen (ab 75 %)')
    dlg.resize(1120,620)
    layout=QVBoxLayout(dlg)
    layout.addWidget(QLabel(
        'Alle aktivierten und berechtigten Anbieter werden verglichen. '
        'Mindestens 75 % Übereinstimmung und 75 % Trackabdeckung. '
        'Keine automatische Speicherung; externe Anbieter-IDs sind keine MusicBrainz-IDs.'
    ))
    status=QLabel('Die Multi-Source-Suche wird gestartet…',dlg)
    layout.addWidget(status)
    columns=['Übereinstimmung','Abdeckung','Quelle','Album','Albumartist','Release-Jahr','Anbieter-ID']
    table=QTableWidget(0,len(columns),dlg)
    table.setHorizontalHeaderLabels(columns)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.horizontalHeader().setStretchLastSection(True)
    layout.addWidget(table)
    footer=QHBoxLayout()
    details=QPushButton('Ausgewählten Treffer prüfen',dlg)
    close=QPushButton('Schließen',dlg)
    footer.addWidget(details)
    footer.addWidget(close)
    layout.addLayout(footer)
    io=create_gui_io(dlg,aggregator)
    ranked=[]
    last_signature=[None]

    def poll():
        # Bounded admission and async DB read; never network-fetch in this callback.
        for key,q in list(requests.items()):
            if not admission[key]:
                admission[key]=aggregator.schedule_async(q,force=True)
        io.read(list(requests))
        payloads=[]
        complete=0
        provider_states={}
        for q in queries:
            data=io.results.get(query_key(q))
            if data and float(data.get('updated') or 0)>=requested_after:
                payload=data.get('payload') or {}
                payloads.append(payload)
                if payload.get('completion')=='COMPLETE':
                    complete+=1
                for source,state in payload.get('status',{}).items():
                    provider_states[source]=str(state)
            else:
                payloads.append({})
        candidates=find_similar_albums(queries,payloads)
        signature=(
            tuple((c['source'],c['release_id'],c['confidence'],c['matched_tracks']) for c in candidates),
            complete,tuple(sorted(provider_states.items())),sum(admission.values())
        )
        if signature==last_signature[0]:
            return
        last_signature[0]=signature
        ranked[:]=candidates
        row_selected=table.currentRow()
        table.setRowCount(len(ranked))
        for index,row in enumerate(ranked):
            values=(f'{100*row["confidence"]:.1f} %',
                    f'{row["matched_tracks"]}/{row["total_tracks"]}',
                    row['source'],row['album'],row['albumartist'],
                    str(row['release_date'])[:4],row['release_id'])
            for j,v in enumerate(values):
                table.setItem(index,j,QTableWidgetItem(v))
        if 0<=row_selected<len(ranked):
            table.selectRow(row_selected)
        table.resizeColumnsToContents()
        states=', '.join(f'{source}:{state}' for source,state in sorted(provider_states.items()))
        busy=sum(admission.values())
        status.setText(
            f'{len(ranked)} Alben ab 75 % · vollständige Anfragen: {complete}/{len(queries)} '
            f'· angenommen: {busy}/{len(requests)} · {states or "Quellen werden abgefragt"}'
        )

    def inspect():
        index=table.currentRow()
        if index<0 or index>=len(ranked):
            QMessageBox.warning(dlg,'PicardWulf','Bitte einen Albumtreffer auswählen.')
            return
        row=ranked[index]
        if not row['matched_rows']:
            return
        i,candidate=row['matched_rows'][0]
        reply=QMessageBox.question(
            dlg,'PicardWulf – Auswahl verifizieren',
            f'{row["source"]}: {row["album"]}\n'
            f'Übereinstimmung {100*row["confidence"]:.1f}% · '
            f'{row["matched_tracks"]}/{row["total_tracks"]} Tracks\n\n'
            'Die Einzeldatei-Vorschau öffnen? Dort können die gefundenen '
            'Metadaten geprüft werden. Es wird dabei NICHT gespeichert.',
            QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply==QMessageBox.StandardButton.Yes:
            show_native_window(api,aggregator,[files[i]],snapshot_func,preferred_candidate=candidate)

    details.clicked.connect(inspect)
    close.clicked.connect(dlg.reject)
    timer=QTimer(dlg)
    timer.setInterval(700)
    timer.timeout.connect(poll)
    timer.start()
    try:
        poll()
        dlg.exec()
    finally:
        timer.stop()
        io.stop()
