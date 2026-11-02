# PicardWulf — Künstler-Compilations / Die Sekte / Frank Zander / WWE

**Stand:** 2026-11-02 · Zielsystem: **BMAX-B6** · Arbeitsbranch: `feature/picard3-retention-policy-20261017` · **keine produktive Aktivierung**

## Fehlerursache

Der Picard-Release-Typ `compilation` beweist **keine** Veröffentlichung mit mehreren Albumkünstlern. Einzelne Gastinterpreten, abweichende Track-Artists und falsch auf `Various Artists` gesetzte Albumartist-Tags führten dazu, dass Künstleralben in mehrere VA-Sampler-/CD-Gruppen zerfielen. Eine Dateibenennungsregel allein ändert nicht automatisch bereits fragmentierte MusicBrainz-Release-/Disc-Zuordnungen.

Die reparierte Regel verwendet **Release-weite Kredits** und **eng benannte, überprüfte Editionen**. Unbekannte Alben behalten ihren bestehenden Pfad oder gehen in den Prüfmodus; es gibt keine pauschale `compilation => Various Artists`-Umleitung.

## Benannte Fälle

- **Die Sekte**: Release-weiter Albumkünstler `Die Sekte`, `Alles ist die Sekte` bzw. `A.I.D.S.` bleibt unter `Die Sekte/JJJJ - Albumtitel/`, auch wenn `_secondaryreleasetype=compilation` lautet oder Gastinterpreter auf Tracks vorkommen. Die belegten Alben `Ihr Nutten` (2001) und `Die Sekte` (2009) sind eng benannte Sonderfälle, wenn das fehlerhafte Albumartist-Feld stattdessen `Various Artists` sagt.
- **Aggro Ansage**: Bei nachweislichem Albumartist `Die Sekte` folgt die benannte Ausgabe dem Künstler; **nicht** alle `Aggro Ansage`-Ausgaben werden umetikettiert. Die veröffentlichte `Aggro Ansage Nr. 1` (2002) ist nach MusicBrainz und Spotify ein echter Multi-Artist-Sampler. Mit Albumartist `Various Artists` wird er **REVIEW** statt automatisch `Die Sekte`. Quellen: https://musicbrainz.org/label/3634fa9a-8e09-4544-8980-272033d924f3 und https://open.spotify.com/album/3i5xg1iUZJRRijklF2kseg
- **Frank Zander – Meine coolsten Hits**: tatsächliche 2022er **Zwei-CD-Compilation**. Alle Tracks einschließlich Gästen/Aliasaufnahmen erhalten den Albumordner `Frank Zander/2022 - Meine coolsten Hits/`. Nur bei verifizierten `discnumber` und `totaldiscs>=2` werden `CD 01/` und `CD 02/` ergänzt; vorhandene CD-Unterordner und native Track-Dateinamen bleiben erhalten. Drei unterschiedliche Picard-Cluster sind kein Beleg für drei verschiedene Alben. Quellen: https://music.apple.com/us/album/meine-coolsten-hits/1603798300 und https://www.musik-sammler.de/release/frank-zander-meine-coolsten-hits-2-cd-1612093/
- **WWE Anthology**: 2002 veröffentlichte Sammlung mit **drei CDs**. Ziel: `![-1.2-VARiOUS-ARTiSTz-]!/WWE Anthology/2002 - WWE Anthology/`, Disc-Unterscheidung `CD 01`, `CD 02`, `CD 03` nur mit bestätigten Disc-Tags. WWE-Bestätigung: https://corporate.wwe.com/about/news/2002/10-30-2002
- **WWE Entrance Themes**: CD-betitelte Teile werden bei gleicher Ausgabe zusammen gehalten unter `![-1.2-VARiOUS-ARTiSTz-]!/WWE Entrance Themes/JJJJ - WWE Entrance Themes/`; Ausgaben ohne belegtes Jahr bleiben REVIEW. **WWE The Music Vol. 1–10** bleibt die bereits separat abgesicherte Serie, z. B. `![-1.2-VARiOUS-ARTiSTz-]!/WWE The Music/2004 - WWE The Music Volume 6/`. Das `WWE Entrance Themes [Bonus CD]` einer bestimmten internationalen Vol.-6-Ausgabe darf **ohne Release-/Katalogzuordnung nicht blind in beliebige andere Veröffentlichungen gemischt werden**.

## Implementierte Dateien

- `neowulf_picard_repair/release_scope.py`: gemeinsame, reine Release-Klassifizierung `release_artist_scope()` und Disc-Unterverzeichnis-Regel `disc_subfolder()`; niemals eine Änderung an Musikdateien oder Tags.
- `neowulf_picard_repair/bmax_naming.py`: **tatsächlich registrierte** `pw_bmax_folder`/ `pw_bmax_fullpath`-Funktionen priorisieren den Release-Guard vor der alten VA-Compilation-Heuristik. Der ursprüngliche Preset-3-Skriptdateiname und ein vorhandener Musik-Masterordner `[--1--MUSiKz------------]` bleiben erhalten.
- `neowulf_picard_repair/preset3_corrections.py`: älterer Kompatibilitätsrouter nutzt denselben Release-Guard, damit nicht zwei unterschiedliche Pfadentscheidungen existieren.
- `neowulf_picard_repair/preset3_migration.py`: der reversible Wrapper übergibt optional `%discnumber%` und `%totaldiscs%`; die gesamte unveränderte alte Skriptquelle bleibt als erstes Argument vorhanden, alle weiteren Presets bleiben unverändert. Die Live-Aktivierung erfordert *vorher* Bestätigung und vollständigen Picard.ini-Backupvergleich.
- `neowulf_picard_repair/picard_safe_import.py`: derselbe Disc-Guard im nur nach zweimaliger Bestätigung anwendbaren FLAC-Import; Originaldatei bleibt erhalten, und es gelten weiterhin Decoder-/Hash-/Backup- und Sperrprüfungen.
- `neowulf_picard_repair/__init__.py`: schreibgeschützte GUI-Ablagevorschau nutzt nun die tatsächliche BMAX-Pfadlogik.
- `tools/audit_artist_compilations.py`: reiner **Read-only-Library-Scanner** für echte BMAX-Medien; gruppiert vorhandene Funddateien, Albumartists, Disc-Nummern, MusicBrainz-Release-IDs und Quellverzeichnisse. Zeigt `split_across_directories`, `multiple_picard_release_ids` und `automatic_move_allowed=false`. „Nicht gefunden“ bedeutet nicht gelöscht. Kein automatisches Kopieren, Retaggen oder Bewegen.
- `Install-NEOWULF.ps1`: alle Python-Module einschließlich `release_scope.py` sind im Hash-/Vollständigkeitskatalog berücksichtigt.

## Nachweise

Auf Legion mit **frischem PicardWulf-Branch** und **offiziellem Picard 3.0.2 `release-3.0.2`**:

- **483 Python-Unit-Tests: OK**, darunter 13 direkte Release-Guard-Tests, eigene GUI-Preview- und sichere FLAC-Importtests, sowie fünf schreibgeschützte Gruppierungs-/Konfliktproben.
- Gepinnter Picard-3.0.2-Core-Patch gegen offizielle Quellen bytegleich zum Repository-Diff, `git apply --check`/Anwendung/Compilation/diff checks PASS.
- Unabhängiger **echter Picard-3.0.2 ScriptParser** in einem isolierten Qt-Virtualenv: **12 Preset-3-Beispiele PASS**, Frank Zander CD 1/2, Die Sekte, Aggro VA Review, WWE Anthology CD 3 und WWE Entrance Themes CD 1 eingeschlossen; keine produktiven Dateien berührt.
- Plugin bleibt bis zur realen BMAX-Überprüfung ein **Draft**, nicht releasefertig.

## Reale BMAX-Prüfung (noch offen)

BMAX-B6 ist der erforderliche Produktionsrechner. Die zuletzt nachgewiesene Situation: Desktop-Commander-Gerät online, aber Remote-Kontingent **0 %**, und der vorhandene Legion→BMAX-Schlüssel wurde für `megal` abgewiesen. **Kein heute authentifizierter Dateisystemzugriff**, keine belegte Änderung an `G:\\[--1--MUSiKz------------]`, Picard.ini, Preset 3 oder realen Medien.

Bei erneutem regulären Zugriff:
1. Gewählten Benutzer und aktive Picard-Installation samt **wirklich aktiver** Skript-ID und tatsächlicher Preset-3-Skriptquelle nur lesen; vollständige unveränderliche Picard.ini- und Skript-Backups mit SHA-256 vor jeder Änderung.
2. Das *tatsächliche* Preset-3-Skript mit isolierten Testdaten im installierten Picard-Parser prüfen; alle Fälle und die bestehenden Album-Pfade vergleichen.
3. Das **nur lesende** Audit auf dem vom Benutzer bestätigten echten Bibliotheksstamm ausführen und auf Vorhandensein, doppelte Release-ID, falsch gesetzte Albumartist-Tags und zwei- bzw. drei-CD-Gruppierung prüfen. Beispiel:
   ```powershell
   python -I tools/audit_artist_compilations.py "G:\\[--1--MUSiKz------------]"
   ```
   Der Pfad ist ein vom Nutzer angegebener Soll-Stamm; vor Ausführung tatsächliche Existenz und Berechtigungen prüfen.
4. Nur das exakt verifizierte aktive Preset-3-Skript atomar und rückrollbar ändern; Picard-Oberflächenvorschau prüfen, danach ausgewählte Testdateien; **keine** bestehenden Originalmedien ohne gesondert bestätigten, SHA-/Backup-geprüften Umzug verschieben.

**Keine Produktionserfolgsmeldung, solange BMAX-Readback und Windows-Ctrl+S-Abnahme nicht tatsächlich PASS sind.**
