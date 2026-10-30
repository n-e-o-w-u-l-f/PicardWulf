# PicardWulf — isolierte Qt- und Tagger-Abnahme (2026-10-23)

**Status:** Linux Qt/Tagger verified; Windows Qt/BMAX deployment **OPEN**; PR #1 **DRAFT**, native FLAC collision policy **OFF** by default.

## Anlass und Ursachen

Am 2026-10-18 wurden auf BMAX-B6 als authentifizierter Benutzer `megal` ein eigener Git-Checkout von PicardWulf und der offizielle Picard 3.0.2 Tag angelegt unter:

`%LOCALAPPDATA%\NEOWULF\Picard3\release-candidates\20261018-native302`

Der gepatchte Core ließ sich auf Windows kompilieren, und die isolierten Python-Tests ergaben **366 Tests, OK (skipped=3)**. Ein anschließender Versuch, die aus `C:\Program Files\MusicBrainz Picard\_internal` geladene **PyInstaller-PyQt6** in einer separaten Python-3.14-Interpreterinstanz zu verwenden, scheiterte beim Import der Qt-DLLs beziehungsweise fatal mit `Unable to embed qt.conf`. Das bedeutet **nicht**, dass Picard selbst kaputt ist; solche eingebetteten Laufzeitbibliotheken dürfen nicht als generelles Python-SDK wiederverwendet werden.

Am **2026-10-23** ist BMAX-B6 im Tailscale-Netz über `100.87.234.27` erreichbar. Seine live präsentierte SSH-ED25519-Fingerprint `SHA256:4qD7x0e3XYGvnrCEItR2TqiCKHv4X7nc0ZOjRCnp3W0` stimmt mit dem bereits unter Legions `andreas`-Identität für die IP gespeicherten Hostkey überein. Die zuvor erfolgreiche Anmeldung `megal@100.87.234.27` wird aktuell mit `Permission denied (publickey,password,keyboard-interactive)` abgewiesen. Ein breiterer Authentifizierungsversuch war außerdem durch OpenAI-Sicherheitsprüfungen blockiert; **keine weiteren Anmeldeversuche zur Umgehung**. SentinelX hat derzeit nur Legion als Agent, Remote Desktop Commander noch 0 % Remote-Kontingent. Der Zustand kann sich geändert haben, seit Windows zuletzt inspiziert wurde; daher keine Aussage über die dort aktuell laufenden Prozesse treffen.

## Neu implementiert, auf Legion getestet

- `compat/qt_isolated_probe.py`: Prüft die exakten originalen Upstream-**Git-Blobs**, den vorhandenen Core-3.0.2-Patch und dessen native Hook-Funktionen. Erfordert eine virtuelle Python-Umgebung, lehnt Picards produktives PyInstaller-`_internal` als Importpfad ab, verwendet **temporäre AppData/XDG-Verzeichnisse**, deaktiviert automatische Updates und startet einen **echten** Qt-Ereignisloop im Offscreen-Modus. Prüft `picard.file.File`, `PluginApi.register_file_move_collision_processor`, die Event-Hook-Registrierung und den gepatchten `picard`-Import.
- `compat/qt_full_tagger_probe.py`: Separater Python-Prozess, der mit den gleichen Quell- und Profileinschränkungen die **tatsächliche Picard-3.0.2-Klasse `Tagger`**, `Tagger.window` und `Tagger.run()` startet, per `QTimer` regulär beendet und Exit-Code 0 verlangt. Kein Album, keine produktiven Plugins, keine echten Medien werden geladen.
- `compat/Verify-Picard302-Qt-Isolated.ps1`: Zielrechner-spezifischer Windows-Prüfablauf. Er verweigert andere Host-/Benutzerkombinationen, Reparse-Point-Testpfade, einen unerkannten Picard-Upstream-HEAD oder fehlenden Patch. `-InstallDependencies` installiert Picards Python-Abhängigkeiten einschließlich separat packaged PyQt6 **nur in das Kandidatenvenv**. Startet beide getrennten Qt-Probes und anschließend optional die Python-Tests; lässt die installierte Picard.exe, `Picard.ini`, Preset 3, Plugins und Medien unberührt.
- `tests/test_qt_isolated_probe.py`: Vier negative/positive Upstream-Patch-Gates, ausführbar ohne Qt.

### Live-Evidenz vom 2026-10-23

Der Test erfolgte in kurzlebigen, nach Beendigung entfernten `/tmp`-Verzeichnissen auf Legion:
1. Frischer PicardWulf-Branch und offizieller `metabrainz/picard`-Tag `release-3.0.2`.
2. Pinned 3.0.2 Unified Diff bytegleich zum veröffentlichten `compat/patches/picard-3.0.2-native-flac-move.diff`; `git apply --check`, `git apply` und `diff --check` bestanden.
3. Separates `python3 -m venv` und `pip install --only-binary=:all: -e <nur temporärer Picard-Checkout>` erfolgreich.
4. Tatsächlich laufender Qt-App-Ereignisloop: `qt_python=6.11.0`, `picard=3.0.2`, `platform=offscreen`, `native_extension=PRESENT`, Status `PASS_QT_SMOKE_NOT_FULL_GUI`.
5. Tatsächlich gestartete `Tagger`-Hauptanwendung: `Tagger.window` angelegt, `Tagger.run()` und normales Beenden, `exit_code=0`, Status `PASS_FULL_TAGGER_OFFSCREEN_NOT_WINDOWS_SAVE`.
6. `python3 -B -m unittest discover -s tests -q` mit `PICARD302_SOURCE`: **370 Tests, OK**. `compileall`, `git diff --check` bestanden.

Linux-Hinweise zu fehlendem PipeWire, D-Bus, CDROM/discid und einem Offscreen-Qt-Plugin verhinderten den erfolgreichen Start nicht. Das ist **keine Windows-GUI-Verifikation** und **kein echter Ctrl+S-Test mit geladener FLAC**.

## Nächste Freigabekriterien

1. **Einen bestehenden genehmigten BMAX-Zugriff wiederherstellen** (z. B. legitime Benutzer-Sitzung / Work Computer Use), ohne den Sicherheitsblock oder fehlende SSH-Benutzerschlüssel zu umgehen. Nicht auf die alte 2026-10-18-Anmeldung vertrauen.
2. Im bereits vorhandenen Windows-**Kandidatenordner**, nicht im bestehenden `C:\Program Files`-Picard: `git pull --ff-only` nur bei sauberem Checkout, Versions-/Hashcheck, eigenständiges `venv`, `-InstallDependencies` und beide Qt-Probes ausführen. Netzwerk- und Paketdownloads werden nur für dieses venv benötigt.
3. Danach **vollständige echte Windows-Tagger-Sitzung mit temporären FLAC-Medien**, über `File.save()`/`Ctrl+S`, parallele Saves, geladene File-Eigentümer, Rollback bei Postcommit-Fehler, gesperrte Dateien, Windows-Speicherpfade und Absturzwiederherstellung.
4. Erst nach diesen realen Prüfungen und geprüftem Rollback den vorhandenen **produktiven Picard 3.0** und das bereits aktivierte ältere PicardWulf-Plugin durch ein kompatibles **3.0.2-Paket** beziehungsweise dokumentierte Migration ersetzen. Dabei Preset 3 und originale Musik zunächst unangetastet lassen. Nie den 3.0.2-Source-Patch direkt auf die installierte 3.0-PyInstaller-EXE kopieren.
5. Governance und Git-PRE/POST synchronisieren; Pull Request bis zum Abnahmebeleg **DRAFT**, die native Option standardmäßig **OFF**.

**Keine produktive BMAX-Installation, kein authentifizierter BMAX-Zugriff und keine Windows-Qt-Prüfung am 2026-10-23 behauptet.**
