"""Opt-in GUI-safe Mixcloud LiveSet *metadata only* lookup.

Network request runs in a worker. Picard File/Metadata/Qt are accessed only
on the GUI thread. Source URLs are displayed as suggestions; no automatic
file move, tag update, audio download or profile change.
"""
from concurrent.futures import ThreadPoolExecutor

_ACTIVE = {}


def stop_live_set_lookups():
    for key, session in tuple(_ACTIVE.items()):
        session['timer'].stop()
        session['pool'].shutdown(wait=False, cancel_futures=True)
        _ACTIVE.pop(key, None)


def show_liveset_lookup(api, selected, *, search=None):
    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QMessageBox

    files=tuple(selected or ())
    if len(files)!=1:
        QMessageBox.warning(None,'PicardWulf – LiveSet-Suche',
                            'Bitte genau eine geladene LiveSet-Datei wählen.')
        return False
    metadata=getattr(files[0],'metadata',None)
    getter=getattr(metadata,'get',None)
    if not callable(getter):
        QMessageBox.warning(None,'PicardWulf – LiveSet-Suche',
                            'Kein gültiger Picard-Metadatensatz vorhanden.')
        return False
    artist=str(getter('albumartist','') or '').strip()
    title=str(getter('album','') or '').strip()
    if not artist or not title or len(artist)>120 or len(title)>180:
        QMessageBox.warning(None,'PicardWulf – LiveSet-Suche',
                            'Albumkünstler und LiveSet-Titel müssen geprüft sein.')
        return False
    prompt=(f'Nur LiveSet-Metadaten suchen?\n\n'
            f'DJ: {artist}\nTitel: {title}\n\n'
            'Hierfür werden DJ und Titel an die öffentliche Mixcloud-API '
            'gesendet. Keine Tags, Musikdateien oder Einstellungen werden '
            'verändert. Upload-Datum ist kein belegtes Auftrittsdatum.')
    if QMessageBox.question(
            None,'PicardWulf – Mixcloud lesen?',prompt,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
        return False
    if search is None:
        from .liveset_sources import lookup_mixcloud
        search=lookup_mixcloud
    pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='PicardWulf-LiveSet-API')
    timer=QTimer(getattr(api.tagger,'window',None))
    timer.setInterval(175)
    key=object()
    future=pool.submit(search,artist,title)
    _ACTIVE[key]={'pool':pool,'timer':timer,'future':future}

    def deliver():
        if not future.done():
            return
        timer.stop() # Avoid modal QMessageBox reentrancy.
        _ACTIVE.pop(key,None)
        pool.shutdown(wait=False,cancel_futures=True)
        try:
            result=future.result()
        except Exception as exc:
            QMessageBox.warning(None,'PicardWulf – Mixcloud-Anfrage',
                'LiveSet-Metadaten nicht verifiziert ('+type(exc).__name__+
                '). Keine Dateien oder Tags geändert.')
            return
        rows=result.get('matches',[]) if isinstance(result,dict) else []
        if result.get('status') != 'SUGGESTION_ONLY' or not rows:
            QMessageBox.information(None,'PicardWulf – LiveSet prüfen',
                'Kein eindeutiger, zur selben DJ-Person passender Show-Treffer. '
                'Keine automatischen Tagänderungen.')
            return
        one=rows[0]
        QMessageBox.information(None,'PicardWulf – LiveSet-Metadaten (Vorschlag)',
            f"DJ: {one['artist']}\nShow: {one['title']}\n"
            f"Quelle: {one['source_url']}\n"
            f"Upload am: {one.get('uploaded_on') or 'unbekannt'}\n"
            'Auftrittsdatum: NICHT BELEGT\n\n'
            'Nur verifizierter Vorschlag. Keine Dateien, Tags oder Profilwerte verändert.')

    timer.timeout.connect(deliver)
    timer.start()
    return True
