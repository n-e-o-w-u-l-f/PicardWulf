"""PicardWulf 1.0: multi-source lookup, native release matching and backed-up writes."""
from copy import deepcopy
from datetime import datetime
from pathlib import Path, PureWindowsPath
import os
import re
import shutil
import uuid

from PyQt6.QtWidgets import QMessageBox
from picard.plugin3.api import BaseAction
from picard.script import ScriptParser

from .universal_engine import UniversalAggregator
from .native_ui import show_native_window
from .credentials import load as load_credentials, save as save_credentials, FIELDS
from .repair_logic import (
    RepairNotPossible,
    find_candidates,
    prepare_update,
    correct_curtain_call_metadata,
)


def _source_ini():
    appdata = os.environ.get('APPDATA')
    if not appdata:
        raise RepairNotPossible('APPDATA fehlt: Konfigurationsort kann nicht belegt werden.')
    path = Path(appdata) / 'MusicBrainz' / 'Picard.ini'
    if not path.is_file():
        raise RepairNotPossible(f'Picard.ini nicht gefunden: {path}')
    return path


def _backup(cfg):
    # Picard process owns its active profile: back up the *correct user* file.
    ini = _source_ini()
    cfg.sync()
    folder = ini.parent / 'NEOWULF-Backups'
    folder.mkdir(parents=True, exist_ok=True)
    # Never overwrite; include a random suffix for close-together actions.
    dst = folder / ('Picard.ini.before-NEOWULF-' +
                    datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8] + '.bak')
    with ini.open('rb') as src, dst.open('xb') as out:
        shutil.copyfileobj(src, out)
        out.flush()
        os.fsync(out.fileno())
    if dst.stat().st_size != ini.stat().st_size:
        dst.unlink(missing_ok=True)
        raise RepairNotPossible('Backup-Größe stimmt nicht.')
    return dst


def _show(title, msg, level='information'):
    method = getattr(QMessageBox, level)
    method(None, title, msg)


def _diag(cfg):
    setting = cfg.setting
    scripts = setting['file_renaming_scripts']
    active = setting['active_file_naming_script_id']
    raw_active = setting.raw_value('active_file_naming_script_id')
    candidates = find_candidates(scripts)
    enabled_profiles = []
    try:
        enabled_profiles = [str(p.get('title', '[ohne Namen]')) for p in
                            cfg.profiles['user_profiles'] if p.get('enabled')]
    except (TypeError, KeyError):
        enabled_profiles = ['[nicht lesbar]']
    return scripts, candidates, active, raw_active, enabled_profiles


class Inspect(BaseAction):
    TITLE = 'Konfiguration prüfen (nur lesen)'
    MENU = ('NEOWULF',)

    def callback(self, objs):
        try:
            scripts, candidates, active, raw, profiles = _diag(self.api.global_config)
            _show('NEOWULF – Picard 3',
                  f'Aktives effektives Skript: {active}\n'
                  f'Basiswert: {raw}\n'
                  f'Gespeicherte Skripte: {len(scripts)}\n'
                  f'NEOWULF-Kandidaten mit VA-Regel: {len(candidates)}\n'
                  f'Aktive Profile: {len(profiles)}\n'
                  '\nNoch nichts geändert.')
        except Exception as exc:
            self.api.logger.error('Naming inspection failed: %s', type(exc).__name__)
            _show('NEOWULF – Prüfung nicht möglich', str(exc), 'warning')


class Repair(BaseAction):
    TITLE = 'VA-Sortierung reparieren (mit Backup)'
    MENU = ('NEOWULF',)

    def callback(self, objs):
        cfg = self.api.global_config
        try:
            scripts, candidates, effective, _, profiles = _diag(cfg)
            updated, target_id = prepare_update(scripts)
            candidate = candidates[0][1]
            name = str(candidate.get('title', target_id))
            # Parse the *whole* updated script with the actual running Picard runtime.
            parser = ScriptParser()
            parser.parse(updated[target_id]['script'])
            notice = (
                f'Das bestehende NEOWULF-Skript wird verlustfrei korrigiert:\n{name}\n\n'
                '1. Compilation allein zählt nicht mehr als Various Artists.\n'
                '2. Alle übrigen Regeln und Skripte bleiben erhalten.\n'
                '3. Das NEOWULF-Skript wird aktiv gesetzt.\n'
                f'4. Bisher aktiv: {effective}; aktive Profile: {len(profiles)}.\n'
                '5. Vorher wird die vollständige Picard.ini gesichert.\n\n'
                'Jetzt anwenden? Es werden KEINE Musikdateien gespeichert oder verschoben.'
            )
            if QMessageBox.question(None, 'NEOWULF – Reparatur bestätigen', notice,
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                    QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
                return
            before_scripts = deepcopy(scripts)
            before_active = effective
            bak = _backup(cfg)
            try:
                cfg.setting['file_renaming_scripts'] = updated
                cfg.setting['active_file_naming_script_id'] = target_id
                cfg.sync()
                live_scripts = cfg.setting['file_renaming_scripts']
                live_active = cfg.setting['active_file_naming_script_id']
                if live_scripts[target_id]['script'] != updated[target_id]['script'] or live_active != target_id:
                    raise RepairNotPossible('Picard hat die aktive Skriptänderung nicht bestätigt.')
            except Exception:
                # Restore in-memory state; on-disk full backup remains untouched.
                cfg.setting['file_renaming_scripts'] = before_scripts
                cfg.setting['active_file_naming_script_id'] = before_active
                cfg.sync()
                raise
            _show('NEOWULF – Reparatur durchgeführt',
                  f'Skript korrigiert und aktiviert: {name}\n'
                  f'Backup: {bak}\n\n'
                  'Bitte vor dem ersten Speichern in Picard die Dateibenennungsvorschau prüfen.')
        except Exception as exc:
            self.api.logger.error('Naming repair not performed: %s', type(exc).__name__)
            _show('NEOWULF – keine Änderung bestätigt', str(exc), 'warning')


def _album_guard(api, album, metadata, release_node):
    if correct_curtain_call_metadata(metadata):
        api.logger.info('Curtain Call 2: album artist normalized to Eminem (MusicBrainz RGID)')


_aggregator = None


def _get_engine():
    if _aggregator is None:
        raise RuntimeError('Universal-Aggregator nicht initialisiert; Fehler in Picard-Protokollen prüfen.')
    return _aggregator


def _file_snapshot(file):
    """Read tags; infer only a clear 'artist - title' filename when tags are absent."""
    md=getattr(file, 'metadata', None)
    if md is None:md=getattr(file, 'orig_metadata', None)
    if md is None:return None
    get=getattr(md,'get',None)
    if get is None:return None
    keys=('title','artist','album','albumartist','isrc','musicbrainz_recordingid','length','~length')
    data={k:get(k,'') for k in keys}
    if not data['title'] and not data['artist']:
        filename=str(getattr(file,'filename','') or '')
        stem=(PureWindowsPath(filename).stem if "\\" in filename else Path(filename).stem)
        match=re.fullmatch(r'(.{2,130}?)\s+-\s+(.{2,160})',stem)
        if match:
            data['artist']=match.group(1).strip()
            data['title']=match.group(2).strip()
            data['inferred_filename']='1'
    return data


def _file_loaded(api, file):
    """Picard hook: snapshot then queue; never block GUI on network."""
    if _aggregator is None:return
    md=_file_snapshot(file)
    if md is not None:
        try:_aggregator.schedule(md)
        except Exception as exc:
            api.logger.warning('Universal file load scheduling failed: %s', type(exc).__name__)


def _track_loaded(api, track, metadata, track_node, release_node=None):
    """Rescan when MusicBrainz track information has been refreshed."""
    if _aggregator is not None:
        try: _aggregator.schedule(metadata)
        except Exception as exc:
            api.logger.warning('Universal track scheduling failed: %s', type(exc).__name__)


class SourceStatus(BaseAction):
    TITLE = 'Quellenstatus und Warteschlange'
    MENU = ('NEOWULF',)

    def callback(self, objs):
        eng = _get_engine()
        st = eng.status()
        try: saved = load_credentials()
        except (OSError, RuntimeError, ValueError): saved = {}
        creds = dict(eng.credentials)
        creds.update(saved)
        spotify = bool(creds.get('spotify_access_token') or
                       (creds.get('spotify_client_id') and creds.get('spotify_client_secret')))
        _show('NEOWULF Universal Metadata',
            'MusicBrainz: aktiv (frei)\nDeezer: aktiv (öffentliche Katalogsuche)\n'
            'Apple iTunes-Katalog: aktiv (öffentliche Suche)\n'
            f'Spotify: {"konfiguriert" if spotify else "Zugangsdaten fehlen"}\n'
            f'SoundCloud: {"konfiguriert" if creds.get("soundcloud_token") else "OAuth-Token fehlt"}\n'
            f'Last.fm: {"konfiguriert" if creds.get("lastfm_api_key") else "API-Schlüssel fehlt"}\n\n'
            f'Geplant: {st["queued"]} · Ausstehend: {st["backlog"]} · In Arbeit: {st["pending"]} · Fehlgeschlagen: {st["failed"]}\n\n'
            'Konfiguriert bedeutet nicht, dass der Anbieter die Anfrage freigibt.\n'
            'Detaillierte Antworten und HTTP-Status unter Ergebnisse ansehen.')


class CredentialsAction(BaseAction):
    TITLE = 'Quellen-Zugangsdaten (Windows DPAPI)'
    MENU = ('NEOWULF',)

    def callback(self, objs):
        from PyQt6.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout,
                                     QLabel, QLineEdit, QVBoxLayout)
        if os.name != 'nt':
            _show('NEOWULF', 'Credential Manager benötigt Windows DPAPI.', 'warning')
            return
        try: existing=load_credentials()
        except Exception as exc:
            _show('NEOWULF', f'Sicherer Schlüsselspeicher nicht lesbar: {type(exc).__name__}', 'warning')
            return
        dlg=QDialog(None)
        dlg.setWindowTitle('NEOWULF – API-Zugangsdaten')
        layout=QVBoxLayout(dlg)
        layout.addWidget(QLabel('Zugangsdaten bleiben lokal mit Windows DPAPI verschlüsselt.\n'
                                'Leere Felder behalten bereits hinterlegte Werte.\n'
                                'Es entstehen durch NEOWULF keine zusätzlichen Abonnements.'))
        form=QFormLayout()
        labels={'spotify_client_id':'Spotify Client-ID',
                'spotify_client_secret':'Spotify Client-Secret',
                'soundcloud_token':'SoundCloud OAuth Access Token',
                'lastfm_api_key':'Last.fm API-Key'}
        inputs={}
        for key in FIELDS:
            w=QLineEdit()
            if key != 'spotify_client_id':w.setEchoMode(QLineEdit.EchoMode.Password)
            w.setPlaceholderText('Bereits gespeichert – leer lassen' if existing.get(key) else 'Noch nicht konfiguriert')
            form.addRow(labels[key],w)
            inputs[key]=w
        layout.addLayout(form)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save |
                                 QDialogButtonBox.StandardButton.Cancel)
        layout.addWidget(buttons)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        if dlg.exec() != QDialog.DialogCode.Accepted:return
        updated=dict(existing)
        updated.update({key:w.text().strip() for key,w in inputs.items() if w.text().strip()})
        if not updated:
            _show('NEOWULF', 'Keine Zugangsdaten vorhanden; nichts geändert.')
            return
        try:
            save_credentials(updated)
            eng=_get_engine()
            eng.credentials.update(updated)
            # Token obtained through old client credentials must not be reused after update.
            eng.credentials.pop('spotify_access_token',None)
            eng.credentials.pop('spotify_token_until',None)
            _show('NEOWULF', 'API-Zugangsdaten verschlüsselt gespeichert. Keine geheimen Daten in Picard.ini.')
        except Exception as exc:
            _show('NEOWULF', f'Zugangsdaten NICHT gespeichert: {type(exc).__name__}', 'warning')


class ResultsAction(BaseAction):
    TITLE = 'Gesammelte Treffer ansehen (alle Quellen)'
    MENU = ('NEOWULF',)

    def callback(self, objs):
        from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QTableWidget,
                                     QTableWidgetItem, QDialogButtonBox)
        eng=_get_engine()
        rows=eng.store.recent(80)
        dlg=QDialog(None)
        dlg.setWindowTitle('NEOWULF – Universal Metadata Aggregator')
        dlg.resize(1150,630)
        layout=QVBoxLayout(dlg)
        status=eng.status()
        layout.addWidget(QLabel(
            f'{len(rows)} zuletzt untersuchte Titel · {status["pending"]} in Arbeit · {status["backlog"]} ausstehend. '
            'Nur Vorschau; keine Tags oder Dateinamen verändert.'))
        fields=('Datei/Tag','Quelle','Treffer','Interpret','Album','Confidence',
                'Bewertung','ISRC','Provider-Status','URL')
        table=QTableWidget(0,len(fields),dlg)
        table.setHorizontalHeaderLabels(list(fields))
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSortingEnabled(False)
        for record in rows:
            q=record['query'];result=record['payload']
            candidates=[c for c in result.get('candidates',[]) if c.get('score')]
            status=', '.join(f'{k}:{v}' for k,v in result.get('status',{}).items())
            if not candidates:candidates=[{}]
            for candidate in candidates[:8]:
                idx=table.rowCount();table.insertRow(idx)
                values=(q['artist']+' – '+q['title'],candidate.get('source','(keine Treffer)'),
                        candidate.get('title',''),candidate.get('artist',''),candidate.get('album',''),
                        str(round(100*candidate.get('score',0),1))+'%' if candidate else '',
                        result.get('verdict',''),candidate.get('isrc',''),status,
                        candidate.get('url',''))
                for i,v in enumerate(values):table.setItem(idx,i,QTableWidgetItem(str(v)))
        table.setSortingEnabled(True)
        table.resizeColumnsToContents()
        layout.addWidget(table)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dlg.reject);buttons.accepted.connect(dlg.accept)
        layout.addWidget(buttons)
        dlg.exec()


class RefreshAction(BaseAction):
    TITLE = 'Geladene Titel aus allen Quellen erneut prüfen'
    MENU = ('NEOWULF',)

    def callback(self, objs):
        eng=_get_engine()
        response=QMessageBox.question(
            None,'NEOWULF – Suche aktualisieren',
            'Metadaten der geladenen Audiodateien werden an zugängliche öffentliche '
            'Katalog-APIs gesendet. Bestehende Tags und Dateien bleiben unberührt.\n\n'
            'Jetzt Hintergrundsuche durchführen?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if response != QMessageBox.StandardButton.Yes:return
        n=0
        for file in self.api.tagger.iter_all_files():
            md=_file_snapshot(file)
            if md is not None and eng.schedule(md,force=True):n+=1
        _show('NEOWULF',f'{n} Titel zur erneuten Prüfung angemeldet.\n'
                           'Später Werkzeuge → NEOWULF → Gesammelte Treffer ansehen öffnen.')


class NativeReview(BaseAction):
    TITLE = 'Album-Matching & Tags überschreiben (mit Backup)'
    MENU = ('PicardWulf',)

    def callback(self, objs):
        eng = _get_engine()
        files=list(self.api.tagger.iter_all_files())
        show_native_window(self.api, eng, files, _file_snapshot)


class SelectedFileReview(BaseAction):
    TITLE = 'PicardWulf: Multi-Source-Release/Tags auswählen'

    def callback(self, objs):
        eng=_get_engine()
        files=[obj for obj in objs if getattr(obj,'metadata',None) is not None]
        show_native_window(self.api, eng, files, _file_snapshot)


def enable(api):
    global _aggregator
    api.register_tools_menu_action(Inspect)
    api.register_tools_menu_action(Repair)
    api.register_album_metadata_processor(_album_guard, priority=-1000)
    try:
        _aggregator = UniversalAggregator()
    except Exception as exc:
        _aggregator = None
        api.logger.error('Universal aggregator initialization failed: %s', type(exc).__name__)
        return
    api.register_file_post_load_processor(_file_loaded)
    api.register_track_metadata_processor(_track_loaded, priority=-1000)
    api.register_tools_menu_action(SourceStatus)
    api.register_tools_menu_action(CredentialsAction)
    api.register_tools_menu_action(ResultsAction)
    api.register_tools_menu_action(RefreshAction)
    api.register_tools_menu_action(NativeReview)
    api.register_file_action(SelectedFileReview)


def disable():
    global _aggregator
    if _aggregator is not None:_aggregator.stop()
    _aggregator=None
