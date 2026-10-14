<div align="center">

[English](README.md) · [Deutsch](README.de.md) · [Русский](README.ru.md) · [Français](README.fr.md) · [Español](README.es.md) · [Italiano](README.it.md) · [Português (Brasil)](README.pt-BR.md) · [Polski](README.pl.md) · [Українська](README.uk.md) · [日本語](README.ja.md) · [简体中文](README.zh-CN.md)

</div>

# PicardWulf v1.0

**Quellenübergreifende Release-Erkennung, automatische Metadatenübernahme und sicheres Tagging für MusicBrainz Picard 3.0.**

> **Status:** Entwicklungsversion. Lokale Tests erfolgreich; Installation, Plugin-Aktivierung, Live-APIs und das Speichern auf BMAX-B6 sind noch nicht vollständig praktisch verifiziert.

## Funktionen

- **Alle Quellen gemeinsam bewerten:** MusicBrainz, Deezer, Apple/iTunes sowie Spotify, SoundCloud und Last.fm mit vorhandenen API-Berechtigungen.
- **Automatisch nach „Ordner hinzufügen“:** Dateien laden, Suchanfragen im Hintergrund ausführen und alle gefundenen Albumversionen **quellenneutral** nach Titel, Interpret, Album, Albumkünstler, Laufzeit und echten Kennungen bewerten.
- **Bestes Release gewinnt:** Der höchste eindeutige Treffer liefert die Metadaten – auch wenn die Quelle **Deezer, Spotify, SoundCloud oder eine andere Nicht-MusicBrainz-Quelle** ist. Die Quelle und Bewertung werden intern in Picard festgehalten.
- **Keine Blindzuordnung:** Bei widersprüchlichen Kennungen, verschiedenen Editionen oder knappen Bewertungen erfolgt nur eine manuelle Vorschau.
- **Natives Picard-Albumfenster:** Nur ein überprüftes MusicBrainz-Release-/Recording-MBID-Paar darf als nativer Picard-Release geladen werden. Deezer-/Spotify-/Apple-Album-IDs bleiben eigene Anbieterkennungen.
- **Tags und Backups:** Eindeutige Treffer aktualisieren standardmäßig nur Picards Vorschau. Automatisches Schreiben in Audiodateien ist **ausgeschaltet**, bis es ausdrücklich aktiviert wurde; davor wird jede vollständige Datei separat kopiert und per SHA-256 geprüft.
- **NEOWULF:** Bestehende Dateibenennungsskripte, Profilprüfung und die Reparatur von „Compilation → Various Artists“ bleiben erhalten. *Eminem – Curtain Call 2* bleibt Eminem.

## Installation auf Windows

1. MusicBrainz **Picard 3.0** schließen; ungespeicherte Änderungen vorher sichern.
2. Das Projekt beziehungsweise Release-Paket entpacken.
3. **`Install-NEOWULF.cmd`** unter dem Desktop-Benutzer ausführen (auf BMAX-B6: `megal`). Die `.ps1` nicht direkt starten.
4. Das Plugin wird unter `%APPDATA%\MusicBrainz\Picard\plugins3\neowulf_picard_repair` abgelegt; die defekte `picard-cli.exe` wird nicht verwendet.
5. Picard starten und unter **Optionen → Plugins** aktivieren. Die Installation allein beweist noch keine erfolgreiche Plugin-Aktivierung.

## Bedienung

**Datei → Ordner hinzufügen** startet die Metadatensuche. Im Menü **Werkzeuge → PicardWulf** stehen die automatische Release-Auswahl, das optional aktivierbare automatische Speichern mit Backup sowie die manuelle **Album-Matching & Tags überschreiben**-Ansicht zur Verfügung. **Werkzeuge → NEOWULF** enthält Quellenstatus, Zugangsdaten, Trefferübersicht und Dateibenennungsreparatur.

Die automatische Übernahme benötigt einen eindeutig bewerteten Treffer (standardmäßig mindestens **93,5 %** bei hinreichendem Abstand zu alternativen Releases). Dateien mit nur geratenen Angaben aus dem Dateinamen werden nicht ungeprüft verändert.

## Reparatur bei 10.000+ Dateien ohne Picard-Neustart

**Picard nicht beenden, nicht zwangsweise speichern und die SQLite-Datenbank nicht löschen.** Wenn die Oberfläche reagiert, unter **Optionen → Plugins** zuerst **PicardWulf deaktivieren**. Die laufende Hintergrundsuche wird gestoppt, bereits dauerhaft gespeicherte Aufträge bleiben erhalten. Anschließend im entpackten aktuellen Projekt **`Install-PicardWulf-Live.cmd`** starten und die ausdrücklich verlangte Bestätigung erst nach dem Deaktivieren des Plugins eingeben. Der Installer ersetzt gesichert nur das Plugin, **nicht den laufenden Picard-Prozess**. Danach in Picard das Plugin erneut aktivieren.

S1 begrenzt den noch nicht dauerhaften Eingang auf **2.048 Aufträge einschließlich laufender Schreibcharge**. Weitere geladene Dateien bleiben über schwache Dateireferenzen vorgemerkt und werden schrittweise erneut aufgenommen. Ein einzelner SQLite-Schreiber übernimmt Datenbankzugriffe und konfigurierbare Chargen (standardmäßig 256); Ergebnisse und Backup-Bestätigungen kommen über Qt-Signale zurück. Vollständige Audiosicherung und Hashing laufen ebenfalls außerhalb des GUI-Threads. Bei Datenbankfehlern pausiert die Suche, der Eingang bleibt erhalten. Deaktivieren startet eine Hintergrundleerung; erneutes Aktivieren wartet im Hintergrund auf deren Bestätigung. **Werkzeuge → PicardWulf → Hintergrundsuche pausieren / fortsetzen** steuert Anbieterabfragen, während die Aufnahme weiterläuft. Ein Rückstand über 2.000 Aufträgen wird beim Start vorsorglich pausiert. **Der synthetische Qt-Test mit 29.000 alten + 10.000 neuen Identitäten auf Legion ist bestanden; BMAX-Laufzeit und Installation bleiben offen.** [Nachweise und Grenzen](docs/planning/S1-EXECUTION-2026-10-14.md).

## Vollständiger Quellenvergleich beim Dateiimport

Ein starker Cache-Treffer einer anderen Datei desselben Albums konnte weitere Provider-Abfragen vorzeitig überspringen. Die Korrektur prüft **jede aktivierte, berechtigte Quelle** für den aktuellen Track oder verwendet einen bereits erfolgreich abgeschlossenen Cache-/Checkpoint-Treffer **für dieselbe Anfrage**. Auch ein überzeugender MusicBrainz-Treffer sperrt Deezer, SoundCloud oder Last.fm nicht mehr aus. Anbieterquoten, fehlende API-Berechtigungen und eine bewusst gesetzte Pause gelten weiterhin. [Ursachenanalyse und Tests](docs/planning/V1.0-PROVIDER-COMPLETENESS-2026-10-14.md). BMAX wurde dabei nicht verändert.

## Metadaten vollständig sammeln und API-Schlüssel (v1.0)

MusicBrainz, Deezer und Apple/iTunes lieferten ohne eigene API-Schlüssel im öffentlichen Test Treffer. Deezer kann nach erfolgreicher Track- und Albumzuordnung ISRC, Disc-/Tracknummer, Datum, Label, Barcode und Albuminterpret aus offiziellen Detaildaten übernehmen. Der Treffervergleich ist **bidirektional und anbieterneutral**.

SoundCloud stellt neue Anwendungsschlüssel nur mit Artist Pro aus. Spotify-Development-Anwendungen erfordern Premium; Last.fm vergibt API-Schlüssel über das eigene Entwicklerkonto. Keine zusätzlichen Kosten und keine erfundenen Zugangsdaten. Bereits berechtigte Schlüssel werden lokal über **Tools > NEOWULF > Quellen-Zugangsdaten (Windows DPAPI)** eingegeben. Ein großer Rückstand zeigt nun eine Warnung, aber startet keine ungewollte Pause; Ihre manuelle Pause bleibt erhalten.

Siehe [Anbieterzugänge, Freigabegrenzen und sicherer BMAX-Rollout](docs/planning/V1.0-PROVIDER-ACCESS.md). Diese Änderungen sind noch nicht im laufenden Windows-Picard aktiviert.

## Architekturprüfung und nächster Schritt für v1.0

Die Zielversion bleibt **v1.0**. Die geprüften Risiken und die vor der Freigabe notwendigen Arbeiten sind im [technischen Forschungsbericht](docs/research/PICARDWULF-V1.0-DEEP-RESEARCH-2026-10-14.md) und im [verbindlichen Ausführungsplan](docs/planning/V1.0-NEXT-EXECUTION.md) festgehalten. Zuerst wird die SQLite-Warteschlange vollständig entkoppelt und dauerhaft abgesichert. Diese Recherche hat den laufenden BMAX-Picard nicht verändert.

## Sicherheit und Grenzen

MusicBrainz, Deezer und iTunes können ohne zusätzliche Zugangsdaten abgefragt werden, sofern ihre öffentlichen Dienste erreichbar sind. Spotify, SoundCloud und Last.fm benötigen legitime Zugangsdaten. Es findet **keine Umgehung von API-Limits** statt. Suchbegriffe werden an aktivierte Metadatenanbieter übertragen.

**Wichtig:** Drittanbieter-Releases können in der PicardWulf-Trefferansicht ausgewählt und in Datei-Metadaten übernommen werden; sie werden **nicht als gefälschte MusicBrainz-Releases** in Picards natives Albumfenster eingespeist. Auch ein gestarteter asynchroner Speichervorgang ist noch kein bestätigter Schreib-Erfolg.

## Entwicklung und Tests

```bash
python -m unittest discover -s tests -v
```

Weitere technische Einzelheiten stehen in der [englischen Referenz-README](README.md). Lokale Tests ersetzen keine Live-Abnahme auf BMAX. Zusätzliche kostenpflichtige Runner oder Abonnements sind nicht vorgesehen.

[Quellcode](https://github.com/n-e-o-w-u-l-f/PicardWulf) · [Änderungen](CHANGELOG.md) · [Offene Prüfungen](LAST_TASKS.md) · [Lizenz](LICENSE)


## v1.0 S2 – Quellstand

Anbieterfreigaben, klare Verfügbarkeitszustände, dauerhafte Anfragebudgets/Wartezeiten und sichere Tokenverwaltung sind umgesetzt. Vollständige Cache-Entscheidungen können wiederverwendet werden; ausstehende Antworten lösen keine automatische Übernahme aus. Unter Werkzeuge → PicardWulf → **Anbieter, Suchumfang und Anfragebudget** lassen sich Quellen, vollständige Suche, bereits vorhandener Spotify-Zugang und Stundenbudget einstellen. Anonyme MusicBrainz-/Deezer-/iTunes-Prüfungen und 145 Tests bestehen; Anbieter mit Zugangsdaten und BMAX-Laufzeit bleiben offen.

[S2 evidence / Nachweise](docs/planning/S2-EXECUTION-2026-10-14.md).

## v1.0 S3 Quellcode-Zwischenstand

Release-v2 prüft Editions-, Datums- und Disc-Konflikte, zeigt Matching-Punkte mit Beiträgen und hält angewendete Vorschauen fest. Verifizierte weitere Aufnahmen desselben Albums können kompatible Editionskonflikte auflösen; fehlende Belege erfordern Prüfung. Der kuratierte synthetische Korpus umfasst 41 Fälle: zehn korrekte automatische Vorschläge, 31 Enthaltungen und keine falsche Zuordnung. BMAX-Laufzeit und sichere Dateispeicherung bleiben offen. Ungeprüfte Transliteration und fehlende vollständige Tracklisten führen zur Enthaltung. [S3-Nachweise und Grenzen](docs/planning/S3-EXECUTION-2026-10-14.md).
