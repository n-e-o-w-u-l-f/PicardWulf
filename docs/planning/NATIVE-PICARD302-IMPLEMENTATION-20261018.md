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
