# PicardWulf — Vier-Kategorien-Albumablage und LiveSet-Metadaten

Stand: 2026-10-27 · Branch `feature/picard3-retention-policy-20261017` · PR #1 bleibt **DRAFT**.

## Kanonisches Ablageschema

```text
Various Artists/<Samplerreihe>/YYYY - <Albumtitel> Vol. X/<Preset-3-Dateiname>
Collaborations/<Artist 1>, <Artist 2> & <Artist Last>/YYYY - <Albumtitel>/<Preset-3-Dateiname>
<Albumartist>/YYYY - <Albumtitel>/<Preset-3-Dateiname>
LiveSets/<DJ oder LiveSet-Artist>/YYYY-MM-DD - <Settitel>/<Preset-3-Dateiname>
```

Bei LiveSets ohne belegtes vollständiges Datum gilt `YYYY - <Settitel>`, nur wenn ein verlässliches Jahr existiert. WWE Volume 2–10 verwendet weiterhin ausdrücklich `Various Artists/WWE The Music/YYYY - WWE The Music Volume X`, selbst wenn der Tag `date` eine spätere Neuauflage nennt. Ein unvollständig belegtes oder fehlerhaftes Album führt zu `REVIEW` statt zu einer erfundenen neuen Ordnerhierarchie.

## Zuweisung nach Release-Credits, niemals Track-Künstlern

Das Modul `neowulf_picard_repair/album_routing.py` berechnet ohne Dateizugriff ein `AlbumRoute(kind, folder, reason, review)`:

1. **Sampler**: WWE-/WWF-Reihe anhand der streng definierten Titel; andere Sampler nur bei `albumartist=Various Artists` zusammen mit explizitem `sampler_collection` oder eindeutiger Titelendung `Vol. X`/`Volume X`/`Band X`. Die belegte Serie heißt z. B. `Bravo Hits`; die tatsächlich bekannte Bandnummer wird normalisiert. Ohne gesicherte Bandnummer wird niemals eine `Vol. 1` erfunden.
2. **Kollaborationen**: ausschließlich `albumartists` als mehrwertiger Albumkünstler-Tag von Picard 3.0 (oder kompatibles `_albumartists`), maximal zwölf überprüfbare, eindeutige Albumkünstler. Ein einzelner Bandname wie `Simon & Garfunkel` und Gäste eines Tracks erzeugen **keine** separate Kollaboration. Auch wenn der kombinierte `albumartist`-Text `Alpha & Beta` enthält, wird der Künstlername nicht anhand von `&` ohne individuelle releaseweite Credits zerrissen.
3. **Künstleralben**: verifizierter echter `albumartist`; `compilation` allein bedeutet **nicht** `Various Artists`. Ein künstlerbezogenes `Eminem / Curtain Call 2` bleibt bei Eminem. Falsche Albumkünstlerwerte, Quellenmarken als Albumartist oder fehlende Jahre werden geprüft statt automatisch korrigiert.
4. **LiveSets**: ausdrücklich belegte `is_liveset`, `set_type` oder kombinierte `live` + `dj-mix`-/Radio-/Festival-Set-Evidenz. Konventionelle Livekonzerte als normale Livealben bleiben beim Hauptkünstler. Ein tatsächliches `event_date` oder `set_date` geht dem allgemeinen Veröffentlichungsdatum vor. Nie ein Upload-Datum als Auftrittsdatum angeben.

Ein Windows-Pfadkomponentenschutz verhindert Laufwerksonderzeichen, reservierte DOS-Namen und `..`-Traversals; lange oder uneindeutige Artist-Credits führen zu `REVIEW`. Ein späteres Zusammenführen identischer Zielpfade bleibt Aufgabe des unabhängig überprüften FLAC-Kollisions- und Sicherungsprozesses.

## Picard-Kontextmenü und Skript

Die Plugin-Aktivierung **registriert** eine zusätzliche offizielle Picard-3-Funktion:

```text
$pw_album_folder(album,albumartist,originaldate,date,secondary,albumartists,collection,volume)
```

Picard 3.0 stellt `albumartists` explizit als mehrwertigen Tag zur Verfügung: https://picard-docs.musicbrainz.org/en/v3.0/variables/tags_basic.html

Ein möglicher isoliert zu prüfender Ausschnitt des File-Naming-Skripts lautet:

```picard
$pw_album_folder(%album%,%albumartist%,%originaldate%,%date%,$join(%_secondaryreleasetype%,;),$join(%albumartists%,;),%sampler_collection%,%sampler_volume%)
```

Dies ist nur der **Albumordner**. Die reale Dateinamenskomponente des bestehenden Preset 3 wird nicht ersetzt, auch das aktive Skript, die Picard.ini und die vorhandenen Presets werden **nicht** stillschweigend geändert. Vor einer zukünftigen echten Preset-Migration müssen die tatsächlich installierte Skriptfassung, die Original-Hashes, getestete ScriptParser-Auswertung und ein separates Backup vorliegen.

Die ausgewählten Dateien können im Menü `PicardWulf > Ablage prüfen: Sampler, Kollaborationen, Künstler, LiveSets (nur lesen)` klassifiziert werden. Im **explizit bestätigten** `SafeStagedFlacImport` wird bei einem vollständig geprüften Release nur der Albumordner auf das Schema gesetzt; der ursprüngliche aktive native Trackdateiname bleibt erhalten. Vorschau und Importprüfung bleiben gesondert, einschließlich FLAC-Decoder, quellgebundener SHA und Recovery-Sicherungen. Wenn die Evidenz unzureichend ist, gibt die neue Route keinen eigenmächtigen Ersatzpfad vor.

## LiveSet-Suche („Scraping“)

**Bevorzugte offizielle, legitim nutzbare Datenquelle:** [Mixcloud REST API](https://www.mixcloud.com/developers/), öffentlicher Endpoint `https://api.mixcloud.com/search/?q=...&type=cloudcast`, JSON-Antwort. MusicBrainz unterscheidet ausdrücklich die Typen **Live**, **DJ-mix** und **Broadcast**; sie sind **nicht synonym** und führen nicht pauschal in `LiveSets`: https://musicbrainz.org/doc/Release%20Group/Type

`neowulf_picard_repair/liveset_sources.py` bietet einen streng auf DJ- und Showtitel vergleichenden, längenbegrenzten, mit Zeitlimit versehenen JSON-Lookup. Die URL muss dem echten Mixcloud-HTTPS-Endpunkt entsprechen. Eine identische Show bei mehreren nahezu gleich guten Treffern wird als `REVIEW` zurückgegeben. Die Ergebnisdaten erhalten Quellen-URL, DJ, Titel, Upload-Datum, Dauer, Score und `requires_confirmation=True`, **keine automatische Dateiumbenennung oder Tagübernahme**. Mixclouds `created_time` dokumentiert die **Uploadzeit**, nicht sicher den Live-Auftritt; `performance_date_verified=False` und `suggested_folder=""` bis ein echtes Auftrittsdatum geprüft wird.

Zwei ausdrücklich opt-in Varianten:

- Direkt im Picard-Dateikontextmenü `LiveSets: Mixcloud-Metadaten suchen (nur lesen)`: Vor der Anfrage wird die Übermittlung von DJ-/Albumtitel an Mixcloud bestätigt, dann erledigt ein separater Worker den Netzaufruf; der Qt-Thread zeigt nur einen Treffer mit Link und Unsicherheitshinweisen an. Abschalten des Plugins stoppt Polling und nicht gestartete Hintergrundjobs.
- Extern `python tools/lookup_liveset.py --artist "DJ Example" --title "Boiler Room Berlin DJ Set"`. Benötigt **nur Standard-Python** und Netzfreigabe; importiert nicht die Picard-/PyQt6-GUI. JSON-Status `SUGGESTION_ONLY`, `ABSTAIN` oder `REVIEW`, Exitstatus 0 nur für eindeutigen Vorschlag. Es werden keine Musikdateien gelesen oder geschrieben.

## Teststand und Release-Schranke

Die zuvor veröffentlichte PicardWulf-Suite hatte **400 Tests PASS** auf dem versionsgebundenen offiziellen Picard-3.0.2-Checkout. Nach Implementierung des Kern-Routers und vor den abschließenden GUI-LiveSet-Tests wurden **403 Tests OK (2 skipped)** auf einem separaten Python-Testlauf nachgewiesen. Danach blockierten Sicherheitsprüfungen die weitere externe Remote-Testausführung, einschließlich des erneuten echten Picard-ScriptParser-Probes. **Die allerneuesten Änderungen sind daher noch nicht vollständig auf Legion und BMAX getestet.** Das wird weder als reale Windows-Abnahme noch als fehlerfrei im produktiven Picard behauptet.

**BMAX-Pfad und Medienstatus:** kein autorisierter aktueller Windows-Zugriff, kein Scan der echten WWE-Alben, keine Installation in die dortige Picard-3.0-EXE, keine Änderung an Preset 3, Picard.ini oder Audio. PR #1 bleibt DRAFT; die native automatische Kollisionsfunktion bleibt AUS. Der bestehende native Source-Patch gegen exakt Picard 3.0.2 und die neuen Kategorien sind erst nach vollständigen Regressionstests, Windows-Qt-/Ctrl+S-Abnahme und separatem Rollback produktiv nutzbar.
