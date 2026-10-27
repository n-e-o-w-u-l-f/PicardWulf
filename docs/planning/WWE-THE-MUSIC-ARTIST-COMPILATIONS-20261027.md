# WWE The Music 1–10 und Künstler-Compilations: Zielablage, Sicherungs- und Suchnachweis

Stand: 2026-10-27 · Projekt PicardWulf · PR #1 **DRAFT** · Medienmigration auf BMAX **NICHT AUSGEFÜHRT**

## Nutzerziel

Viele Compilations mit einem **echten Hauptkünstler** sollen bei diesem Künstler bleiben, statt aufgrund des Picard-Metadatenwerts `compilation` als `Various Artists` einsortiert zu werden. Anders die ausdrückliche Samplerreihe WWE/WWF The Music: Band 1–9, später auch Band 10, soll so benannt werden:

```text
<konfigurierter Musik-Bibliotheksstamm>\Various Artists\WWE The Music\YYYY - WWE The Music Volume N\<von Preset 3 erzeugter ursprünglicher Trackdateiname>.flac
```

Kein globaler Schluss `compilation == Various Artists`: NEOWULFs bestehende `repair_logic.OLD -> NEW`-Korrektur nimmt nur echte `albumartist=Various Artists`-Release-Credits als VA; korrekt ausgewiesene Künstler-Compilations wie `Eminem / Curtain Call 2` bleiben beim Künstler. **Besteht der vorhandene Wert `albumartist` bereits irrtümlich aus `Various Artists`, lässt sich der wahre Albumkünstler nicht allein aus dem Interpret eines Tracks rekonstruieren.** Die neue Prüfung markiert dies zur manuellen Freigabe statt alle echten Multi-Artist-Sampler zu zerstören.

## Kanonische WWE-Alben

| Band | Originales Album / Albumalias | Ordnerjahr |
|---:|---|---:|
| 1 | `WWF Full Metal: The Album` bzw. ausdrücklich `WWF/WWE The Music Volume 1` | **Originaljahr aus Tags (1995 oder 1996) erforderlich**, sonst keine automatische Entscheidung |
| 2 | `WWF The Music, Volume 2` | 1997 |
| 3 | `WWF The Music, Volume 3` | 1998 |
| 4 | `WWF The Music, Volume 4` | 1999 |
| 5 | `WWF The Music, Vol. 5` | 2001 |
| 6 | `ThemeAddict: WWE The Music, Vol. 6` | 2004 |
| 7 | `WWE The Music, Vol. 7` | 2007 |
| 8 | `WWE The Music, Vol. 8` | 2008 |
| 9 | `Voices: WWE The Music, Vol. 9` | 2009 |
| 10 | `WWE The Music: A New Day, Vol. 10` | 2010 |

Quellen: WWE Music Group Discography und offizielle WWE-Ankündigungen zu Voices Volume 9, https://corporate.wwe.com/about/news/2009/01-27-2009 und https://en.wikipedia.org/wiki/WWE_Music_Group. Band 1 wird absichtlich nicht mit einem unbelegten Jahr überschrieben. Reissue-Jahre werden beim bekannten Band 2–10 nicht irrtümlich zur neuen Seriennummerierung verwendet; Konflikte werden als Prüfhinweis ausgegeben.

## Implementierte Änderungen

1. `neowulf_picard_repair/wwe_series.py`: Reine, unveränderliche Erkennung der exakt erlaubten WWE-/WWF-/ThemeAddict-/Voices-Titel; keine Ähnlichkeitssuche, kein Seiteneffekt. Ordnerbeispiel `Various Artists/WWE The Music/2009 - WWE The Music Volume 9`. Der Künstler und Albumkünstler anderer Alben werden **nicht** umgeschrieben. Fremde WWE-Alben wie `WWE Originals`, `WWE Uncaged` und `WWE Wreckless Intent` gehören nicht automatisch zur Serie.
2. Picard-3-Plugin: native `$pw_wwe_folder(%album%,%date%,%originaldate%)` registriert und über offiziellen `ScriptParser` in einem isolierten Picard **3.0.2** wirklich geprüft (Bände 2, 6, 9 PASS). Kein stilles Auswechseln von aktivem Preset 3: Erst nach read-only Export/Prüfung des Originalskripts und separat bestätigter Konfigurationssicherung kann dieses die neue Funktion als Zielordner verwenden.
3. Über die **bereits vorhandene** bestätigungspflichtige `SafeStagedFlacImport`-Picard-Dateiaktion wird der vom unveränderten aktiven Preset erzeugte **Track-Dateiname** beibehalten, der WWE-Albumordner aber zur kanonischen Reihe umgelenkt. Die Originaldatei bleibt erhalten; Prüfung, Ziel-Pfadsperre, FLAC-Dekodierung und separate Rückfallsicherung sind unverändert verpflichtend. Ein `Strg+S` in der produktiven Picard-3.0-Installation führt diese neue Route **noch nicht** aus.
4. Neues Kontextmenü `PicardWulf > Ablage prüfen: WWE / Künstler-Compilations (nur lesen)`: zeigt die konkrete relative WWE-Zielstruktur bzw. warnt bei unbewiesenen VA-Credits; keine Tag-/Profil-/Dateiänderung.
5. `tools/audit_wwe_music.py`: Vollständiger **read-only** Scan explizit benannter Bibliotheksstämme, optional vollständig ohne PyQt6/Picard in vorhandenem Python + Mutagen. Liest FLAC/MP3/anderen Audio-Albumtag, erkennt bekannte WWE-Aliasse auch in fremden Ordnern, meldet Bestand und tatsächliche Fundpfade je Band sowie Diskrepanz zur Sollablage. Zusätzlich werden physisch gruppierte Veröffentlichungen mit `albumartist=Various Artists`, aber mindestens drei gleich kreditierten Tracks als **Prüfkandidaten** ausgewiesen – keine automatische Änderung. Sym-/NTFS-Junction-Verknüpfungen werden nicht verfolgt; die Anzahl der Dateien ist begrenzt, und der Lauf hat keine Schreiboperationen.

Beispielsyntax **erst nach wiederhergestelltem autorisierten BMAX-Zugang und mit dem aus Picard abgelesenen tatsächlichen Bibliotheksstamm**:

```powershell
python -I "C:\Users\megal\AppData\Local\NEOWULF\Picard3\release-candidates\20261018-native302\PicardWulf\tools\audit_wwe_music.py" "D:\<BESTÄTIGTER-BIBLIOTHEKSSTAMM>"
```

Der Pfad `D:\<BESTÄTIGTER-BIBLIOTHEKSSTAMM>` ist lediglich ein Platzhalter und keine Behauptung über den echten Benutzerpfad. Python und Mutagen müssen vorhanden sein; fehlendes Mutagen darf keine falsch leere Fundliste vortäuschen. Das Skript liefert JSON auf stdout, einschließlich `by_volume`, `misplaced_candidates`, `examples` und `potentially_misfiled_artist_compilations`. Bei mehreren Bibliotheksstämmen jeden Root explizit übergeben.

## Abnahme / Grenzen

Auf Legion im isolierten Branch-/Picard-3.0.2-Checkout: **390/390 Python-Tests PASS**, Python-Quellkompilierung, regenerierter offizieller 3.0.2-Patch bytegleich zur eingecheckten Version, `git apply --check`, `git diff --check`. Die Tests umfassen **alle WWE-Bände 2–9**, Full Metal Vol. 1 mit zweifelhafter Jahreszahl, Vol. 10, falsche WWE-Nachbartitel, Eminem-/Artist-Compilations vs echte verschiedene Interpreten, GUI-Vorschau, tatsächliche sichere WWE-Importzielbildung, read-only Inventar und **wirklich kodierte FLAC-Tags**. Der offizielle Picard-3.0.2-`ScriptParser` hat `$pw_wwe_folder` mit den echten Titeln 2/6/9 ausgewertet: PASS.

**Offen:** Derzeit ist kein authentifizierter BMAX-Zugang verfügbar (zuletzt abgewiesen am 2026-10-23). Es liegt **kein Scan der realen WWE-Dateien** vor; die gesuchten Bände 2–9 können nicht als gefunden, vorhanden, gelöscht oder verschoben bestätigt werden. Nichts wurde auf BMAX neu getaggt, umsortiert, überschrieben oder gelöscht. Stock Picard 3.0 und die installierte ältere PicardWulf-Version bleiben unverändert. Aktives Preset 3 und Picard.ini werden weder automatisch durch die Quelle noch durch den Suchlauf geändert; der PR bleibt DRAFT und native Ctrl+S-Produktionsabnahme OPEN.

**Nächster konkreter Schritt bei wiederhergestellter autorisierter Windows-Sitzung:** tatsächliches `move_files_to`, verwendetes Preset 3 und Bibliotheksstämme nur lesen, Inventar für Bände 1–10 und VA-Künstler-Compilations exportieren, Fundlisten mit dem Besitzer abstimmen. Danach separate atomar gesicherte Profiländerung und ausschließlich bestätigte reversible Umzüge – nicht vor der Windows-Qt-/Ctrl+S-Freigabe.
