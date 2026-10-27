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
from .auto_apply import AutoApplyController
from .save_tracking import SaveTracker
from .cluster_ui import selected_group_files, show_similar_albums
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


class WweSeriesPlacementPreview(BaseAction):
    TITLE = 'WWE The Music: Zielordner prüfen (nur lesen)'
    MENU = ('PicardWulf',)

    def callback(self, objs):
        """Never changes tags, Picard profiles, or filesystem paths."""
        from .wwe_series import route_metadata
        files=list(objs or [])
        lines=[]
        for file in files[:20]:
            md=getattr(file,'metadata',None) or getattr(file,'orig_metadata',None)
            if md is None:continue
            get=getattr(md,'get',None)
            if not callable(get):continue
            info=route_metadata({
                key:get(key,'')
                for key in ('album','artist','albumartist','date','originaldate',
                            '_secondaryreleasetype')
            })
            if info.get('state')=='WWE_SERIES':
                lines.append(str(info['folder']).replace('/','\\'))
                if info.get('needs_review'):
                    lines.append('  Hinweis: Datum/Originaljahr prüfen (abweichende Ausgabe).')
        if not lines:
            _show('WWE The Music – Vorschau',
                  'Keine bekannte WWE-The-Music-Reihe in den ausgewählten '
                  'Dateien erkannt. Keine Dateien oder Einstellungen geändert.')
        else:
            unique=list(dict.fromkeys(lines))
            _show('WWE The Music – Soll-Zielordner (nur Vorschau)',
                  '\\n'.join(unique[:24])+
                  '\\n\\nKeine Dateien verschoben oder umgetaggt. '
                  'Für die reale Ablage muss das geprüfte Preset-3-Benennungsskript '
                  'die Funktion $pw_wwe_folder() aufrufen.')


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
_controller = None
_save_tracker = None
_gold_controller = None
_retiring_engine = None


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
    keys=('title','artist','album','albumartist','isrc','musicbrainz_recordingid',
          'musicbrainz_albumid','length','~length','date','releasecountry','barcode',
          'releasecomment','tracknumber','totaltracks','discnumber','totaldiscs','genre','label','composer','originaldate',
          '~picardwulf_source','~picardwulf_decision','~picardwulf_review')
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



def _original_file_snapshot(file):
    """Match from original disk tags, not transient MusicBrainz UI replacements."""
    orig=getattr(file,'orig_metadata',None)
    if orig is not None:
        get=getattr(orig,'get',None)
        if get is not None and get('title','') and get('artist',''):
            # Reuse the same bounded snapshot logic, only substitute the
            # metadata owner; never change the Picard file itself.
            class _Original:
                metadata=orig
                filename=getattr(file,'filename','')
            return _file_snapshot(_Original())
    return _file_snapshot(file)


def _retire_mp3_after_verified_flac(path):
    """Worker-only: remove matching MP3 only after a verified FLAC save.

    Keep an independently SHA-256-verified recovery copy outside the music
    folder. Missing flac CLI or uncertain metadata means no deletion.
    """
    if not path:
        return None
    flac=Path(path)
    if flac.suffix.casefold()!='.flac':
        return None
    mp3=flac.with_suffix('.mp3')
    if not mp3.is_file():
        return None
    from .retention_policy import decide_mp3_removal, remove_verified_mp3
    decision=decide_mp3_removal(mp3,flac)
    if decision['action']!='REMOVE':
        return decision
    from .native_workflow import backup_envelope
    from .save_tracking import verify_pre_save_identity
    receipt=backup_envelope(str(mp3))
    verify_pre_save_identity(receipt,str(mp3))
    outcome=remove_verified_mp3(mp3,flac,backup_receipt=receipt)
    if outcome['action']=='REMOVED':
        outcome['backup']=receipt['manifest']
    return outcome


def _file_saved(api, file):
    # Picard 3 invokes this ONLY after a file's save operation has completed.
    # Disk tag verification runs on PicardWulf's dedicated worker, not here.
    if _save_tracker is not None:
        _save_tracker.post_save(file)


def _file_loaded(api, file):
    """Picard hook: snapshot then queue; never block GUI on network."""
    if _aggregator is None:return
    md=_original_file_snapshot(file)
    if md is not None:
        try:
            if _controller is not None:
                _controller.watch(file,md)
            else:
                api.logger.warning('PicardWulf admission unavailable: GUI controller missing')
        except Exception as exc:
            api.logger.warning('Universal file load scheduling failed: %s', type(exc).__name__)


def _track_loaded(api, track, metadata, track_node, release_node=None):
    """Rescan when MusicBrainz track information has been refreshed."""
    if _aggregator is not None and _controller is not None:
        try:
            for file in getattr(track,'iterfiles',lambda: ())():
                md=_original_file_snapshot(file)
                if md is not None:_controller.watch(file,md)
        except Exception as exc:
            api.logger.warning('Universal track scheduling failed: %s', type(exc).__name__)


_SOURCE_NAMES={'musicbrainz':'MusicBrainz','deezer':'Deezer','itunes':'Apple/iTunes',
               'spotify':'Spotify','soundcloud':'SoundCloud','lastfm':'Last.fm'}


def _source_line(source,cap):
    states={'AVAILABLE':'Für Abfragen zugelassen','CREDENTIALS_REQUIRED':'Zugangsdaten benötigt',
            'QUOTA_WAIT':'Wartet auf das Anfragebudget','TEMPORARY_ERROR':'Vorübergehend nicht verfügbar',
            'RESTRICTED':'Zugang eingeschränkt','DISABLED':'Ausgeschaltet'}
    reasons={'existing_access_not_confirmed_no_purchase':'Bereits bestehenden Zugang in den Anbieteroptionen bestätigen.',
             'one_time_refresh_uncertain':'Ein neuer gültiger Refresh-Token wird benötigt.',
             'credentials_missing':'Zugangsdaten fehlen.', 'HTTP_401':'Der Anbieter hat die Zugangsdaten abgelehnt.',
             'HTTP_403':'Der Anbieter hat den App-Zugang abgelehnt.', 'request_budget':'Die gespeicherte Wartezeit gilt weiter.',
             'response_invalid':'Die Antwort konnte nicht sicher ausgewertet werden.',
             'vault_unavailable':'Der sichere Schlüsselspeicher ist nicht verfügbar.'}
    observed='Eine Antwort wurde bereits geprüft.' if cap.get('observed') else 'Noch keine Antwort geprüft.'
    return (f'{_SOURCE_NAMES.get(source,source)}: {states.get(cap.get("state"),"Wird geprüft")} · '
            f'{reasons.get(cap.get("reason"),"")} {observed}').strip()


class SourceStatus(BaseAction):
    TITLE = 'Quellenstatus und Warteschlange'
    MENU = ('NEOWULF',)

    def callback(self, objs):
        eng = _get_engine()
        st = eng.status()
        lines='\n'.join(_source_line(source,cap) for source,cap in st.get('capabilities',{}).items())
        _show('NEOWULF Universal Metadata',
            (lines or 'Anbietersteuerung wird im Hintergrund initialisiert.')+'\n\n'
            f'Geplant: {st["queued"]} · Eingangs-Puffer: {st["staging"]} · Ausstehend: {st["backlog"]} · In Arbeit: {st["pending"]} · Fehlgeschlagen: {st["failed"]} · Pause: {st["paused"]}\n'
            f'Großer Rückstand erkannt: {st["large_backlog_detected"]} (Warnung, keine automatische Pause)\n\n'
            f'Bestätigt verarbeitet: {st["committed"]} · Wiederholen: {st["retry"]}\n'
            f'Rückstau: {st["backpressure"]} · Datenbankfehler: {st["db_error"] or "keiner"}\n'
            'Eingangs-Puffer ist noch NICHT dauerhaft; Überlauf wartet in Picard.\n'
            'Konfiguriert bedeutet nicht, dass der Anbieter die Anfrage freigibt.\n'
            'Detaillierte Antworten und HTTP-Status unter Ergebnisse ansehen.')


def _provider_options(config):
    return {'disabled':config.get('disabled_providers',[]),
            'exhaustive':config.get('search_exhaustive',False),
            'spotify_existing_access_confirmed':config.get('spotify_existing_access_confirmed',False),
            'requests_per_hour':config.get('provider_requests_per_hour',3000)}


class ProviderPolicyAction(BaseAction):
    TITLE = 'Anbieter, Suchumfang und Anfragebudget'
    MENU = ('PicardWulf',)

    def callback(self,objs):
        from PyQt6.QtWidgets import (QDialog,QVBoxLayout,QLabel,QCheckBox,QSpinBox,QDialogButtonBox)
        from .universal_adapters import SOURCES
        from .provider_policy import normalize_options
        cfg=self.api.plugin_config
        options=normalize_options(_provider_options(cfg))
        dlg=QDialog(None);dlg.setWindowTitle('PicardWulf – Anbieter und Suche')
        layout=QVBoxLayout(dlg)
        layout.addWidget(QLabel('Nur zugelassene Quellen erhalten Metadaten.\n'
                               'Es werden keine Konten erstellt und keine Abonnements abgeschlossen.'))
        inputs={}
        for source in SOURCES:
            check=QCheckBox(_SOURCE_NAMES[source],dlg)
            check.setChecked(source not in options['disabled'])
            layout.addWidget(check);inputs[source]=check
        exhaustive=QCheckBox('Alle zugänglichen Quellen auch bei starkem lokalem Treffer prüfen',dlg)
        exhaustive.setChecked(options['exhaustive']);layout.addWidget(exhaustive)
        spotify=QCheckBox('Für diese Spotify-App besteht bereits ein zulässiger API-Zugang',dlg)
        spotify.setChecked(options['spotify_existing_access_confirmed']);layout.addWidget(spotify)
        layout.addWidget(QLabel('Maximale Anfragen je Anbieter und Stunde; Anbieterlimits gelten zusätzlich.'))
        budget=QSpinBox(dlg);budget.setRange(1,3000)
        budget.setValue(options['requests_per_hour']);layout.addWidget(budget)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        layout.addWidget(buttons);buttons.accepted.connect(dlg.accept);buttons.rejected.connect(dlg.reject)
        if dlg.exec()!=QDialog.DialogCode.Accepted:return
        cfg['disabled_providers']=[s for s,w in inputs.items() if not w.isChecked()]
        cfg['search_exhaustive']=exhaustive.isChecked()
        cfg['spotify_existing_access_confirmed']=spotify.isChecked()
        cfg['provider_requests_per_hour']=budget.value()
        _get_engine().configure_providers(_provider_options(cfg))
        _show('PicardWulf','Anbietersteuerung übernommen. Bereits laufende Anfragen dürfen auslaufen; '
                         'bestehende Quoten-Wartezeiten bleiben erhalten.')


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
                'soundcloud_client_id':'SoundCloud Client-ID (bereits registriert)',
                'soundcloud_client_secret':'SoundCloud Client-Secret',
                'soundcloud_refresh_token':'SoundCloud Refresh-Token',
                'lastfm_api_key':'Last.fm API-Key'}
        inputs={}
        for key in labels:
            w=QLineEdit()
            if key not in ('spotify_client_id','soundcloud_client_id'):w.setEchoMode(QLineEdit.EchoMode.Password)
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
        updated={key:w.text().strip() for key,w in inputs.items() if w.text().strip()}
        if not updated:
            _show('NEOWULF', 'Keine Zugangsdaten vorhanden; nichts geändert.')
            return
        try:
            eng=_get_engine()
            receipt=eng.update_credentials(updated,persist=True)
            if receipt is None:raise RuntimeError('Hintergrundwarteschlange ausgelastet; nichts gespeichert.')
            from PyQt6.QtCore import QTimer
            timer=QTimer(self.api.tagger)
            def acknowledged():
                if not receipt.done():return
                timer.stop();timer.deleteLater()
                if eng.stopped:return
                try:receipt.result()
                except Exception as exc:
                    _show('NEOWULF',f'Zugangsdaten NICHT bestätigt: {type(exc).__name__}','warning')
                else:
                    _show('NEOWULF','API-Zugangsdaten verschlüsselt gespeichert. Keine geheimen Daten in Picard.ini.')
            timer.timeout.connect(acknowledged);timer.start(100)
            _show('NEOWULF','Speicherung im Hintergrund beauftragt. Bestätigung folgt erst nach erfolgreicher Speicherung.')
        except Exception as exc:
            _show('NEOWULF', f'Zugangsdaten NICHT gespeichert: {type(exc).__name__}', 'warning')


class ResultsAction(BaseAction):
    TITLE = 'Gesammelte Treffer ansehen (alle Quellen)'
    MENU = ('NEOWULF',)

    def callback(self, objs):
        from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QTableWidget,
                                     QTableWidgetItem, QDialogButtonBox)
        eng=_get_engine()
        dlg=QDialog(None)
        from .background_io import create_gui_io
        from PyQt6.QtCore import QTimer
        io=create_gui_io(dlg,eng)
        dlg.setWindowTitle('NEOWULF – Universal Metadata Aggregator')
        dlg.resize(1150,630)
        layout=QVBoxLayout(dlg)
        status=eng.status()
        layout.addWidget(QLabel(
            f'Zuletzt untersuchte Titel · {status["pending"]} in Arbeit · {status["backlog"]} ausstehend. '
            'Nur Vorschau; keine Tags oder Dateinamen verändert.'))
        fields=('Datei/Tag','Quelle','Treffer','Interpret','Album','Matching-Punkte',
                'Bewertung','ISRC','Provider-Status','URL')
        table=QTableWidget(0,len(fields),dlg)
        table.setHorizontalHeaderLabels(list(fields))
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSortingEnabled(False)
        signature=[None]
        def populate():
            io.read_recent()
            rows=io.recent
            current=repr([(r['updated'],r['query']) for r in rows])
            if signature[0]==current:return
            signature[0]=current
            table.setSortingEnabled(False)
            table.setRowCount(0)
            for record in rows:
                q=record['query'];result=record['payload']
                candidates=[c for c in result.get('candidates',[]) if c.get('score')]
                status=', '.join(f'{k}:{v}' for k,v in result.get('status',{}).items())
                if not candidates:candidates=[{}]
                for candidate in candidates[:8]:
                    idx=table.rowCount();table.insertRow(idx)
                    values=(q['artist']+' – '+q['title'],candidate.get('source','(keine Treffer)'),
                            candidate.get('title',''),candidate.get('artist',''),candidate.get('album',''),
                            str(round(100*candidate.get('release_score',candidate.get('score',0)),1))+'/100' if candidate else '',
                            result.get('verdict',''),candidate.get('isrc',''),status,
                            candidate.get('url',''))
                    for i,v in enumerate(values):table.setItem(idx,i,QTableWidgetItem(str(v)))
            table.setSortingEnabled(True)
            table.resizeColumnsToContents()
        layout.addWidget(table)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dlg.reject);buttons.accepted.connect(dlg.accept)
        layout.addWidget(buttons)
        timer=QTimer(dlg)
        timer.timeout.connect(populate)
        timer.start(500)
        populate()
        dlg.exec()
        timer.stop()
        io.stop()



class SearchPauseAction(BaseAction):
    TITLE = 'Hintergrundsuche pausieren / fortsetzen (ohne Picard-Neustart)'
    MENU = ('PicardWulf',)

    def callback(self, objs):
        eng=_get_engine()
        if eng.paused:
            eng.resume()
        else:
            eng.pause()
        self.api.plugin_config['search_paused']=eng.paused
        state=eng.status()
        _show('PicardWulf – Warteschlange',
              ('PAUSIERT. Bereits laufende Anfragen dürfen noch auslaufen.' if eng.paused
               else 'FORTGESETZT. Die gespeicherten Aufträge werden weiter bearbeitet.')
              + f'\nSQLite-Warteschlange: {state["backlog"]}'
              + f'\nNoch in Übertragung: {state["staging"]}'
              + '\nAlle geladenen Dateien bleiben in Picard erhalten.')


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
        if _controller is None:
            _show('NEOWULF','Hintergrundaufnahme nicht verfügbar; nichts angemeldet.','warning')
            return
        _controller.refresh(self.api.tagger.iter_all_files(),force=True)
        _show('NEOWULF','Geladene Titel werden schrittweise zur erneuten Prüfung angemeldet.\n'
                           'Später Werkzeuge → NEOWULF → Gesammelte Treffer ansehen öffnen.')


class RestoreAudioCopy(BaseAction):
    TITLE = 'Audio-Backup in NEUE Datei wiederherstellen'
    MENU = ('NEOWULF',)

    def callback(self, objs):
        from PyQt6.QtWidgets import QFileDialog
        if _save_tracker is None:
            _show('PicardWulf','Wiederherstellungsdienst nicht verfügbar.','warning')
            return
        receipt,_=QFileDialog.getOpenFileName(
            None,'PicardWulf – Sicherungsbeleg auswählen','',
            'PicardWulf-Belege (*.receipt.json)')
        if not receipt:return
        destination,_=QFileDialog.getSaveFileName(
            None,'PicardWulf – NEUEN Zieldateinamen auswählen','',
            'Audiodateien (*.*)')
        if not destination:return
        if QMessageBox.question(None,'PicardWulf – Kopie wiederherstellen',
            'Die Sicherung wird per SHA-256 geprüft und NUR als NEUE Datei '
            'wiederhergestellt. Bestehende Audiodateien werden nicht überschrieben. '
            'Ein Kopieren in den Musikordner kann Dubletten erzeugen.\n\n'
            'Wiederherstellung im Hintergrund starten?',
            QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:return
        try:
            _save_tracker.request_restore(receipt,destination)
        except Exception as exc:
            _show('PicardWulf – Wiederherstellung nicht gestartet',str(exc),'warning')
            return
        _show('PicardWulf – Wiederherstellung beauftragt',
              'Die neue Kopie wird im Hintergrund erstellt. Erst RESTORED_COPY '
              'unter NEOWULF → Tag-Speicherstatus bestätigt den Erfolg.')


class TagSaveStatus(BaseAction):
    TITLE = 'Tag-Speicherstatus (Post-Save & Readback)'
    MENU = ('NEOWULF',)

    def callback(self, objs):
        if _save_tracker is None:
            _show('PicardWulf', 'Speichernachverfolgung ist nicht aktiv.', 'warning')
            return
        status=_save_tracker.status()
        totals=', '.join(f'{entry["state"]}' for entry in status['recent'][-8:])
        from .gold_retirement import native_gold_retirement_allowed
        if not self.api.plugin_config.get('gold_auto_retire', True):
            gold_state='AUS (PicardWulf-Einstellung)'
        elif not native_gold_retirement_allowed(self.api):
            gold_state=('GESPERRT: Picards eigene Option "Vollständige Alben nach dem '
                        'Speichern entfernen" ist aktiv oder nicht verifizierbar. '
                        'Picard kann ohne unabhängige PicardWulf-Prüfung entfernen; '
                        'diese native Option zuerst in Picard deaktivieren.')
        elif _gold_controller is None:
            gold_state='NICHT GESTARTET (Plugin oder Qt-Controller prüfen)'
        else:
            gold_state='AKTIV (nur nach unabhängiger FLAC-Prüfung)'
        _show('PicardWulf – Tag-Speicherstatus',
              f'Ausstehende Picard-Speicherungen: {status["pending"]}\n'
              f'Laufende Dateiprüfungen: {status["verifying"]}\n'
              f'Laufende Wiederherstellungen: {status["restoring"]}\n'
              f'Letzte Prüfergebnisse: {totals or "keine"}\n'
              f'Goldene CD automatisch aus der Ansicht: {gold_state}\n\n'
              'VERIFIED bedeutet Post-Save-Ereignis plus übereinstimmend '
              'zurückgelesene Tags und intakte Sicherung. '
              'UNVERIFIED oder MISMATCH bedeutet NICHT bestätigt. '
              'Backups werden niemals automatisch überschrieben oder gelöscht.')


class SimilarAlbumsAllSources(BaseAction):
    TITLE = 'PicardWulf: Ähnliche Alben aus ALLEN Quellen (ab 75 %)'
    MENU = ('PicardWulf',)

    def callback(self, objs):
        try:
            files=selected_group_files(objs)
            show_similar_albums(self.api,_get_engine(),files,_file_snapshot)
        except Exception as exc:
            self.api.logger.warning('PicardWulf multi-provider album comparison: %s',
                                    type(exc).__name__)
            _show('PicardWulf – Albumsuche',str(exc),'warning')


class NativeReview(BaseAction):
    TITLE = 'Album-Matching & Tags überschreiben (mit Backup)'
    MENU = ('PicardWulf',)

    def callback(self, objs):
        eng = _get_engine()
        files=list(self.api.tagger.iter_all_files())
        show_native_window(self.api, eng, files, _file_snapshot, _save_tracker)


class SelectedFileReview(BaseAction):
    TITLE = 'PicardWulf: Multi-Source-Release/Tags auswählen'

    def callback(self, objs):
        eng=_get_engine()
        files=[obj for obj in objs if getattr(obj,'metadata',None) is not None]
        show_native_window(self.api, eng, files, _file_snapshot, _save_tracker)



class NativeCollisionPreview(BaseAction):
    TITLE = 'PicardWulf: Dateikollisionen / FLAC-Größenregel prüfen (nur lesen)'

    def callback(self, objs):
        try:
            from .collision_preview import show_collision_preview
            show_collision_preview(self.api, objs)
        except Exception as exc:
            self.api.logger.warning('PicardWulf native collision preview failed: %s',
                                    type(exc).__name__)
            _show('PicardWulf – Dateikollisionen',
                  'Kollisionsprüfung nicht verfügbar; keine Dateien verändert.', 'warning')


class SafeStagedFlacImport(BaseAction):
    TITLE = 'PicardWulf: FLAC sicher in Musikbibliothek übernehmen (mit Backup)'

    def callback(self, objs):
        try:
            from .picard_safe_import import show_safe_import
            show_safe_import(self.api, objs, _save_tracker)
        except Exception as exc:
            self.api.logger.warning('PicardWulf safe FLAC import: %s', type(exc).__name__)
            _show('PicardWulf – Sicherer FLAC-Import',
                  'Import konnte nicht gestartet werden; keine Erfolgsmeldung.', 'warning')


def _native_move_prepare(api):
    """GUI-thread snapshot: background workers must never read ProfileConfig."""
    config = api.plugin_config
    return (bool(config.get('native_move_auto', False)),
            str(config.get('native_recovery_root', '')))


def _native_move_collision(api, old_filename, new_filename, settings,
                           destination_loaded, frozen_policy):
    """Patched Picard 3.0.2 move-worker hook; only immutable values are read.

    Do not dereference api, Picard File, Tagger, Qt or ProfileConfig here.
    The public core extension captures frozen_policy on the GUI thread.
    """
    if (not isinstance(frozen_policy, tuple)
            or len(frozen_policy) != 2):
        return {'action': 'KEEP', 'reason': 'missing_native_policy_snapshot'}
    enabled, recovery_root = frozen_policy
    if not enabled:
        return {'action': 'UNHANDLED'}
    from .native_move_bridge import arbitrate_native_flac_move
    return arbitrate_native_flac_move(
        old_filename, new_filename, settings, recovery_root,
        destination_loaded=destination_loaded,
    )


class NativeMoveSafetyToggle(BaseAction):
    TITLE = 'Native FLAC-Kollision (nur geprüfter Picard-Core-Build)'
    MENU = ('PicardWulf',)

    def callback(self, objs):
        cfg = self.api.plugin_config
        if cfg.get('native_move_auto', False):
            cfg['native_move_auto'] = False
            _show('PicardWulf – Native FLAC-Kollision',
                  'Native Kollisionsintegration AUS. Standard-Picard-Verhalten aktiv.')
            return
        if not hasattr(self.api, 'register_file_move_collision_processor'):
            _show('PicardWulf – Native FLAC-Kollision',
                  'Der installierte Picard-Core bietet keine native '
                  'Kollisionsschnittstelle. Keine Aktivierung, keine '
                  'Datei- oder Profileinstellungen verändert.', 'warning')
            return
        from PyQt6.QtWidgets import QFileDialog
        recovery = QFileDialog.getExistingDirectory(
            getattr(self.api.tagger, 'window', None),
            'Separaten Ordner für unveränderliche FLAC-Sicherungen wählen')
        if not recovery:
            return
        folder = Path(recovery)
        if not folder.is_dir() or folder.is_symlink():
            _show('PicardWulf', 'Ungeprüfter Sicherungsordner.', 'warning')
            return
        settings = self.api.global_config.setting
        try:
            library = Path(settings['move_files_to'])
            if (settings['move_files'] is not True
                    or settings['move_overwrite_existing_files'] is not False
                    or not library.is_absolute() or not library.is_dir()
                    or folder.resolve().is_relative_to(library.resolve())
                    or library.resolve().is_relative_to(folder.resolve())):
                raise ValueError('unsafe_root')
        except (ValueError, KeyError, TypeError, OSError):
            _show('PicardWulf', 'Musikbibliothek und Sicherungen müssen '
                  'getrennte absolute Verzeichnisse sein; natives Überschreiben '
                  'muss AUS sein.', 'warning')
            return
        msg = ('Native Picard-Core-Kollisionsentscheidung NUR in einem '
               'isolierten, mit realen FLAC-Testdateien geprüften '
               'Picard-3.0.2-Testprofil aktivieren?\n\n'
               'Bei identischem FLAC gewinnt die nach Tags/Decoder und '
               'SHA-256 bestätigte größere Datei. Unklare Fälle behalten '
               'die geladene Quelle. Original und Backup bleiben erhalten. '
               'Diese Funktion darf NICHT ungeprüft auf Ihre aktive '
               'Musikbibliothek angewandt werden.')
        if QMessageBox.question(
            None, 'PicardWulf – Native Kollisionsintegration', msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            cfg['native_recovery_root'] = str(folder)
            cfg['native_move_auto'] = True
            _show('PicardWulf', 'Native Kollisionsintegration im '
                  'PicardWulf-Testprofil aktiviert. Kein globales '
                  'Picard-Speicherprofil verändert.')


class AutoApplyToggle(BaseAction):
    TITLE = 'Automatische Release-Auswahl ein-/ausschalten'
    MENU = ('PicardWulf',)

    def callback(self, objs):
        enabled=bool(self.api.plugin_config.get('auto_apply_best',True))
        new=not enabled
        message=('Auto-Auswahl aus allen Metadatenquellen für neu geladene Dateien '
                 + ('einschalten' if new else 'ausschalten') + '?\n\n'
                 'Picard-Metadaten werden nur bei eindeutigem Gewinner aktualisiert. '
                 'Audiodateien werden ohne separat aktiviertes Auto-Speichern nicht geschrieben.')
        if QMessageBox.question(None,'PicardWulf – Auto-Auswahl',message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self.api.plugin_config['auto_apply_best']=new
            _show('PicardWulf', 'Automatische Metadatenübernahme: '+
                  ('EIN (Speichern separat)' if new else 'AUS'))


class AutoSaveToggle(BaseAction):
    TITLE = 'Automatisches Tag-Speichern mit Backup ein-/ausschalten'
    MENU = ('PicardWulf',)

    def callback(self, objs):
        enabled=bool(self.api.plugin_config.get('auto_save_with_backup',False))
        if enabled:
            self.api.plugin_config['auto_save_with_backup']=False
            _show('PicardWulf', 'Automatisches Speichern: AUS. Auto-Auswahl bleibt aktiv.')
            return
        from .retention_policy import require_native_tag_only, RetentionRejected
        try:
            require_native_tag_only(self.api.global_config.setting)
        except RetentionRejected:
            _show('PicardWulf – Automatisches Speichern gesperrt',
                  'Picards natives Umbenennen oder Verschieben ist aktiv oder '
                  'die Einstellungen sind nicht verifizierbar. '
                  'Damit könnte File.save() die geprüfte FLAC-Kollisionsregel '
                  'umgehen. Für reine Tag-Speicherung die Picard-Optionen '
                  '"Dateien umbenennen" und "Dateien verschieben" deaktivieren; '
                  'zur sicheren Bibliotheksübernahme die separate '
                  'PicardWulf-FLAC-Importaktion verwenden.', 'warning')
            return
        notice=('Automatisches SPEICHERN von Musikdateien aktivieren?\n\n'
                'Nur der eindeutige höchstbewertete Release-Treffer wird ausgewählt. '
                'Vor jedem Speichern wird die vollständige Original-Audiodatei '
                'separat gesichert und per SHA-256 geprüft. Picard kann dabei '
                'entsprechend den Einstellungen Dateien umbenennen/verschieben.\n\n'
                'Fehlerhafte API-Zuordnung kann trotzdem falsche Tags erzeugen. '
                'Zuerst mit einer KOPIE testen. Die Änderung gilt ab der nächsten '
                'automatischen Übernahme.')
        if QMessageBox.question(None,'PicardWulf – automatisches Schreiben',notice,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self.api.plugin_config['auto_save_with_backup']=True
            _show('PicardWulf', 'Auto-Speichern mit Backup aktiviert. '
                  'Asynchrone Speichervorgänge und mögliche Umbenennungen in Picard prüfen.')

def enable(api):
    global _aggregator, _controller, _save_tracker, _gold_controller
    api.register_tools_menu_action(Inspect)
    api.register_tools_menu_action(Repair)
    # Independent Picard scripting API: registered but NEVER alters Preset 3
    # until its exact existing script is inspected and safely migrated.
    from .wwe_series import picard_wwe_folder
    api.register_script_function(
        picard_wwe_folder, name='pw_wwe_folder',
        documentation='WWE/WWF The Music sampler series album folder, read-only.',
        signature='$pw_wwe_folder(album,date,originaldate)')
    api.register_file_action(WweSeriesPlacementPreview)
    api.register_album_metadata_processor(_album_guard, priority=-1000)
    api.plugin_config.register_option('auto_apply_best', True)
    api.plugin_config.register_option('auto_save_with_backup', False)
    api.plugin_config.register_option('native_move_auto', False)
    api.plugin_config.register_option('native_recovery_root', '')
    api.plugin_config.register_option('flac_only_cleanup', True)
    api.plugin_config.register_option('gold_auto_retire', True)
    api.plugin_config.register_option('search_paused', False)
    api.plugin_config.register_option('sqlite_batch_size', 256)
    api.plugin_config.register_option('disabled_providers', [])
    api.plugin_config.register_option('search_exhaustive', False)
    api.plugin_config.register_option('spotify_existing_access_confirmed', False)
    api.plugin_config.register_option('provider_requests_per_hour', 3000)
    try:
        _aggregator = UniversalAggregator(paused=bool(api.plugin_config.get('search_paused', False)),
                                         predecessor=_retiring_engine,
                                         batch_size=api.plugin_config.get('sqlite_batch_size',256),
                                         provider_options=_provider_options(api.plugin_config))
    except Exception as exc:
        _aggregator = None
        api.logger.error('Universal aggregator initialization failed: %s', type(exc).__name__)
        return
    _save_tracker=SaveTracker(on_verified=(_retire_mp3_after_verified_flac if
        api.plugin_config.get('flac_only_cleanup',True) else None))
    api.register_file_post_save_processor(_file_saved)
    # This extension exists ONLY in the separately reviewed, locally built
    # Picard 3.0.2 core patch; stock Picard lacks it. Default is OFF.
    if hasattr(api, 'register_file_move_collision_processor'):
        api.register_file_move_collision_processor(
            _native_move_collision, _native_move_prepare)
    try:
        _controller = AutoApplyController(api, _aggregator, _file_snapshot,
                                          ingest_snapshot_func=_original_file_snapshot,
                                          save_tracker=_save_tracker)
        if hasattr(api.tagger,'iter_all_files'):
            # Reload recovery covers overflow identities still owned by Picard.
            # SQLite skips unchanged cached work; this never forces a rescan.
            _controller.refresh(api.tagger.iter_all_files())
    except Exception as exc:
        _controller = None
        api.logger.error('Automatic matching initialization failed: %s',type(exc).__name__)
    api.register_file_post_load_processor(_file_loaded)
    api.register_track_metadata_processor(_track_loaded, priority=-1000)
    # Gold retirement is stricter than Picard's native complete-album option:
    # actual FLAC tags are checked off-GUI before invoking UI-only removal.
    # No auto-removal in headless/mock contexts without an actual Qt window.
    if getattr(api.tagger, 'window', None) is not None and api.plugin_config.get('gold_auto_retire', True):
        try:
            from .gold_retirement import start_gold_retirement
            _gold_controller = start_gold_retirement(api, _save_tracker)
        except Exception as exc:
            _gold_controller = None
            api.logger.error('PicardWulf gold retirement not started: %s', type(exc).__name__)
    api.register_tools_menu_action(SourceStatus)
    api.register_tools_menu_action(ProviderPolicyAction)
    api.register_tools_menu_action(CredentialsAction)
    api.register_tools_menu_action(ResultsAction)
    api.register_tools_menu_action(RefreshAction)
    api.register_tools_menu_action(SearchPauseAction)
    api.register_tools_menu_action(TagSaveStatus)
    api.register_tools_menu_action(RestoreAudioCopy)
    api.register_cluster_action(SimilarAlbumsAllSources)
    api.register_album_action(SimilarAlbumsAllSources)
    api.register_tools_menu_action(NativeReview)
    api.register_file_action(SelectedFileReview)
    api.register_file_action(NativeCollisionPreview)
    api.register_file_action(SafeStagedFlacImport)
    api.register_tools_menu_action(AutoApplyToggle)
    api.register_tools_menu_action(AutoSaveToggle)
    api.register_tools_menu_action(NativeMoveSafetyToggle)


def disable():
    global _aggregator, _controller, _retiring_engine, _save_tracker, _gold_controller
    from .collision_preview import stop_collision_previews
    stop_collision_previews()
    from .picard_safe_import import stop_safe_imports
    stop_safe_imports()
    if _gold_controller is not None:
        _gold_controller.stop()
        _gold_controller = None
    if _controller is not None:
        _controller.stop()
    _controller=None
    if _save_tracker is not None:
        _save_tracker.close()
        _save_tracker=None
    if _aggregator is not None:
        _aggregator.stop()
        _retiring_engine=_aggregator
    _aggregator=None
