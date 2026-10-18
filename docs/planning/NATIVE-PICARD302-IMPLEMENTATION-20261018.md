# PicardWulf — Native FLAC-Kollisionsintegration für Picard 3.0.2 (Quellstand)

Stand: 2026-10-18, **SOURCE TESTED / INSTALLATION AUF BMAX NICHT ERFOLGT**, PR #1 DRAFT.

## Verifizierter Soll- und Ist-Zustand

Der Elternauftrag bleibt die automatische native `Strg+S`-FLAC-Kollisionsentscheidung mit genau identifizierter Aufnahme, bevorzugter größerer FLAC, separatem unveränderlichem Backup, SHA-256, vollständiger Dekodierung, Wiederherstellung, unveränderten aktiven Benennungsregeln und tatsächlicher BMAX-/Windows-Picard-Abnahme.

**Umgesetzt und getestet:**
1. `compat/patches/picard-3.0.2-native-flac-move.diff` ist ein veröffentlichter vollständiger Unified-Diff gegen **genau** `metabrainz/picard` `release-3.0.2`. `compat/picard302_core_contract.py` prüft vor der Erzeugung drei exakte upstream **Git-Blob-SHAs**, lehnt andere Fassungen ab und erzeugt byteidentisch den veröffentlichten Patch.
2. Der Patch erweitert `picard/file.py`, `picard/extension_points/event_hooks.py` und `picard/plugin3/api_impl.py` um einen **öffentlichen** `PluginApi.register_file_move_collision_processor`. Er befindet sich im nativen `File._rename` **vor** `os.makedirs()`, `get_available_filename()` und `_move_with_retry()`. Der File-Save-Worker wird über `File.save()` aufgerufen. Callback-Argumente sind unveränderliche Pfade und eine kopierte native Einstellungsmenge sowie die auf dem Qt-Thread vor Save ermittelte Information, ob das Ziel bereits von einem geladenen `File` belegt ist.
3. Der Policy-Callback `neowulf_picard_repair._native_move_collision` ruft `native_move_bridge.arbitrate_native_flac_move` auf. Dessen FLAC-Entscheidungen `KEEP`, `COMMITTED`, `UNHANDLED` entsprechen einer klaren Core-API. `COMMITTED` wird nur nach `import_staged_flac` mit Identitäts-/Codec-Prüfung, gesperrter Zieldatei, ggf. separat erhaltener Original-Ziel-FLAC und unabhängig überprüften Ziel-Bytes zurückgegeben. `KEEP` lässt die bestehende Bibliotheksdatei unberührt; bei mehreren konkurrierenden Resolvern oder ungültigen Receipts bricht der native Worker mit Fehler ab statt unsicher zu verschieben.
4. Wird die Datei sicher **kopiert** und die Staging-Quelle absichtlich erhalten, überspringt der gepatchte Save-Worker das anschließende Verschieben zusätzlicher Dateien (z. B. `cover.jpg`) aus dem Stagingordner. Picards bisheriges Sidecar-Verhalten für wirkliche Verschiebungen ohne Quelle bleibt erhalten.
5. Der Core-Hook ist **standardmäßig AUS** (`native_move_auto=False`). Stock-Picard bietet ihn nicht, weshalb die Tools-Menüaktion die Aktivierung dort ablehnt. Nur bei installiertem explizit gepatchtem Core und getrennt gewähltem Recovery-Verzeichnis kann der Anwender das Plugin im isolierten Testprofil opt-in aktivieren. Kein stilles globales Überschreiben, keine Änderung der aktiven Picard.ini oder von Preset 3. PicardWulf-auto/manuell gestartete Tag-Saves bleiben weiterhin konservativ tag-only bis ihre eigene asynchrone Nachprüfung auf dem Zielhost erweitert und abgenommen ist.

## Reproduzierbare Source-Validierung, vorhandene kostenlose Legion-Ressourcen

Nur **im kurzlebigen isolierten Checkout**:

```bash
git clone --depth 1 --branch feature/picard3-retention-policy-20261017 \
  https://github.com/n-e-o-w-u-l-f/PicardWulf.git /tmp/picardwulf-test
git clone --depth 1 --branch release-3.0.2 --filter=blob:none \
  https://github.com/metabrainz/picard.git /tmp/picard302-test

cd /tmp/picardwulf-test
python3 -c "from pathlib import Path; from compat.picard302_core_contract import write_checkout_patch; write_checkout_patch(Path('/tmp/picard302-test'), Path('/tmp/picard302-test.patch'))"
cmp /tmp/picard302-test.patch compat/patches/picard-3.0.2-native-flac-move.diff
git -C /tmp/picard302-test apply --check /tmp/picard302-test.patch
git -C /tmp/picard302-test apply /tmp/picard302-test.patch
python3 -m py_compile /tmp/picard302-test/picard/file.py /tmp/picard302-test/picard/plugin3/api_impl.py /tmp/picard302-test/picard/extension_points/event_hooks.py
PICARD302_SOURCE=/tmp/picard302-test python3 -B -m unittest discover -s tests -q
```

**Tatsächlich ausgeführt und bestanden auf Legion:** Patch-Generator-Blob-Prüfung und `cmp` bytegenau (7.685 Bytes), `git apply --check`, `git apply`, Python-Quellkompilierung, `git diff --check`, insgesamt **354 Python-Tests** auf einem frischen PicardWulf-Checkout. Davon sind Quell-API-/Worker-Tests direkt auf dem gepatchten offiziellen `File._rename` und `File._save_and_rename` mit AST-Harness ausgeführt. Ein Test erzeugt eine **echte FLAC** inklusive Tags, lässt sie über den Core-Worker nach einer größer kodierten Version entscheiden, prüft das Backup und die unveränderte Staging- und Coverdatei. Dies ist ein Source-/Worker-Test, **kein vollständiger gestarteter Qt-Picard-Prozess**.

## Weiterhin offene produktionskritische Abnahmen (NICHT DONE)

- **BMAX-B6 / Windows:** Kein authentifizierter Remote-Befehl unter dem angemeldeten Nutzer `megal`, keine überprüfte tatsächlich installierte Picard-Version, kein Windows-Dateisystem-/Hardlink-/Locking-Test, kein echter installierter GUI-Build. SentinelX bietet aktuell nur Legion als eigenen Agent-Host; BMAX liegt über Tailscale erreichbar, aber RDC-Befehlsquote war zuletzt **0 %**. Kein anderes Konto oder Werkzeug dient als Umgehung fehlender Rechte.
- **Vollständiger Save/UI-Lifecycle:** Die Prüfung der `destination_loaded`-Information auf dem Hauptthread ist implementiert, aber ein *nach* der Save-Einplanung und *vor* dem Worker hinzugeladener zweiter `File` kann zusätzlich zu prüfen sein. Auch `tagger.files`-Rebinding, gleichzeitige Saves, Save-/Album-Status, native `File.save()`-Fehlermeldungen, Recoverability nach Prozessabsturz und Gold-UI-Retirement müssen in einem vollständigen echten Picard-3.0.2-Qt-Prozess getestet werden. Bis dahin **nicht produktiv aktivieren**.
- **Andere Dateiformate und Profiloptionen:** Automatisches FLAC-Arbitrating gilt nur für die geprüfte FLAC-Staging-/Bibliothekskonstellation. Fehlende Recovery-Pfade, native Overwrite-Einstellungen oder belegte Picard-Ziele geben sicher `KEEP`. Nicht-FLAC bleibt `UNHANDLED` und nutzt die normalen Picard-Regeln. Die reine Kontextmenü-Importaktion bleibt als unabhängiger unterstützter Weg verfügbar.
- **Veröffentlichung:** Branch und Pull Request bleiben **DRAFT**, kein Merge, kein aktiver BMAX-Picard oder Benutzerprofil verändert. Vor produktivem Einsatz ist ein kontrollierter Windows-Testbuild mit eigenem Profil und ausschließlich generierten temporären FLAC-Dateien zwingend.

## Exakte nächste Ausführung

Den vorhandenen autorisierten BMAX-Remote-Ausführungsweg verifizieren; aktive Version/Profillade-/Skripteinstellungen auslesen; den gepatchten 3.0.2-Core ausschließlich in isolierter Kopie installieren; echte Qt-/File.save-/SaveTracker-/Tagger-Batch-/Kollisionsläufe und Windows-Rückfalltests mit temporären Streams ausführen und Source- und Installationszustand separat abnehmen. Bei gefundenen Abweichungen Implementierung und Governance zusammen aktualisieren; Elternziel bleibt offen.

## Weiterentwicklung am 18. Oktober: richtige Picard-Dateizuordnung und Thread-Snapshot

Ein wichtiger ursprünglicher Core-Patch-Fehler wurde behoben: Die FLAC-Richtlinie führt eine **verifizierte Kopie** in der Bibliothek aus, lässt die Quell-FLAC im Staging aber unverändert bestehen. Der alte Patch gab trotz erhaltenem Quellpfad den Bibliothekspfad an Picards `_saving_finished(result)` zurück. Picard hätte daraufhin sein `File.filename` zur Kopie geändert und in `tagger.files` gegebenenfalls eine zweite, später geladene Datei am Ziel überschrieben. Nach `COMMITTED` liefert `File._rename` jetzt **den ursprünglichen Pfad** zurück, prüft `source_preserved` im Receipt und behält damit die echte File-/Tagger-Identität im Staging. Dazu werden zusätzliche Bilder/Playlist-Dateien bei einer Kopie oder `KEEP` nicht verschoben; bei einer echten nativen Verschiebung bleibt die bisherige Begleitdatei-Logik.

Zudem wird das Policy-/Recovery-Profil **auf dem Qt-Thread vor `thread.run_task` in ein unveränderliches Tupel** überführt. Die neue öffentliche Core-API akzeptiert deshalb zusätzlich einen `prepare(api)`-Callback. Der asynchrone `File._save_and_rename` erhält den unveränderlichen Snapshot als zusätzliches Argument. Der Worker verwendet `frozen_policy` statt `api.plugin_config`: selbst ein unmittelbar nach `File.save()` erfolgter Profilwechsel verändert die im Worker verwendete Richtlinie nicht. Dies vermeidet thread-unsafe Zugriffe auf `ProfileConfigSection` sowie eine stillschweigende nachträgliche Aktivierung des Vorgangs. Bereits eingereihte Jobs bleiben an die beim Start gültigen Optionen gebunden; das nachträgliche Ausschalten ist **keine Rücknahme eines gestarteten Jobs**.

Auch die automatische Gold-Album-Entfernung bleibt bei `native_move_auto=True` gesperrt, weil Picard die Staging-Datei weiterhin besitzt. Die Abnahme umfasst zwei asynchrone Speichervorgänge auf denselben Zielpfad, die Zielsperre, einen nachträglich geladenen File-Eigentümer, die *originale* upstream `_saving_finished()`-Dateiregistry, die originale `File.save()`-Job-Einplanung und ein nach Einplanung geändertes Profil. Unterlagen und Tests verwenden weiterhin ausschließlich temporäre/generated Audio-Dateien.

**Quellvalidierung:** **361 Python-Tests PASS** (einige direkt auf extrahierten, offiziell gepatchten Picard-3.0.2-Funktionen), stabiler Patch aus exakt verifizierten offiziellen Git-Blobs generiert, `git apply --check`, `git apply`, `py_compile`, `git diff --check`, veröffentlichter Unified-Diff byteidentisch. Verifizierter Test-Code-HEAD `8d994cf8c2f7c492a648552a2fc1a8e6b7d6e0e3`.

**Offen bleibt:** Ein vollständiger gestarteter Picard-3.0.2-Qt-Prozess, insbesondere das vollständige Datei-Laden während einer bereits laufenden Kopie (die Registry wird nicht überschrieben, der Ziel-File-Inhalt kann aber veralten), Windows-Dateisperren, Wiederanlauf nach Absturz und echte BMAX-B6-Abnahme. `tailscale ping bmax-b6` zeigte am 18.10.2026 direkte Konnektivität, aber keine `megal`-SSH-Sitzung; Remote Desktop Commander hatte bei der letzten Prüfung 0 % Kontingent. Keine Installation, kein Merge, keine Änderung an aktiver Picard.ini, Preset 3 oder der Musikbibliothek. **Native Policy standardmäßig AUS; PR #1 bleibt DRAFT.**

## Nativer Profil-/Zielpfad-Snapshot: fortgesetzte Abnahme 2026-10-18

**Entdeckter Fehler:** PicardWulf hatte bereits seine eigenen Plugin-Optionen beim `File.save()`-Aufruf auf dem GUI-Thread eingefroren, aber Picards `_save_and_rename()` liest `get_config().setting` im asynchronen Worker erneut. Damit konnte ein geändertes aktives Dateibenennungsskript, Zielverzeichnis, eine Änderung von `rename_files`/`move_files` oder das Setzen von `move_overwrite_existing_files` den tatsächlich verwendeten Pfad bzw. die Überschreibepolitik nach dem initialen Klick verändern.

**Behoben für den opt-in nativen FLAC-Pfad:** Beim ursprünglichen `File.save()` zeichnet der gepatchte Picard-Core zusätzlich zum unveränderlichen Plugin-Policy-Tupel den **vorhergesehenen vollständigen Zielpfad** sowie vier native Profilwerte auf: `rename_files`, `move_files`, `move_files_to`, `move_overwrite_existing_files`. Ein Worker-Vergleich findet **vor jeglichem Tag-Schreibversuch** statt. Sind die Werte, einschließlich des aus dem laufenden Naming-Skript erneut ermittelten Zielpfads, nicht identisch, wird der native Job mit explizitem Fehler abgebrochen; **Quelle und Ziel bleiben in diesem Fall unangetastet**. Ein weiterer Vergleich in `File._rename()` erfolgt direkt vor der Kollisionsentscheidung, falls ein Profil während der eigentlichen Tag-Speicherung verändert wurde. Dann können die Quell-Tags schon geschrieben worden sein, aber eine Änderung der Bibliotheksdatei wird unterbunden und nicht als erfolgreich verschobene Datei gemeldet. Bei nicht aktiviertem Feature bleibt das native Stock-Picard-Verhalten erhalten.

**Regressionen:** Der AST-Test führt exakt die gepatchten offiziellen `File.save()`- und `_save_and_rename()`-Methoden aus, verzögert den Worker, manipuliert danach abwechselnd Zielordner, Naming-Skript und Rename/Move/Overwrite-Schalter und prüft **keine Tag-, Audio- oder Zieländerung vor Worker-Ausführung**. Ein weiterer Test verändert das Skript *während* des Tag-Schreibens und prüft den Abbruch vor dem Move. Zusammen mit der vollständigen FLAC-Kollisions-, Core- und Gold-Suite sind **365 Python-Tests PASS** auf Legion (validierter Quellstand `8348ba48807eef0337e520aa9ea56fad13e7dbd8`); der neue 11.437-Byte-Patch wurde aus den Git-Blob-geprüften offiziellen Picard-3.0.2-Dateien erzeugt, erfolgreich angewandt, kompiliert und veröffentlicht.

**Noch kein RELEASE:** Die Abnahme innerhalb einer wirklich gestarteten Qt-Anwendung auf Windows/BMAX, bei Windows-Dateisperren, Echtzeit-Ladevorgängen anderer Picard-Dateien, Wiederanlauf nach Stromverlust und aktivem Benutzer-Preset bleibt **OPEN**. `native_move_auto=False` bleibt Vorgabe. Der separierte Patch im Entwicklungszweig darf nicht in die produktive Picard-Installation kopiert werden, solange diese Tests nicht erfolgreich durchgeführt wurden.
