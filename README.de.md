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

Das Update nutzt eine im Hintergrund geschriebene SQLite-Sammelwarteschlange (je 256 Aufträge), eine faire, gebündelte Ergebnisprüfung und **Werkzeuge → PicardWulf → Hintergrundsuche pausieren / fortsetzen**. Ein beim Pluginstart vorhandener Rückstand von mehr als 2.000 Aufträgen wird vorsorglich pausiert und kann gezielt wieder gestartet werden. **Die 10.000-Dateien-Belastungsprüfung auf Legion ist bestanden; der Zustand des laufenden Picard auf BMAX-B6 ist noch nicht direkt überprüft.**

## Sicherheit und Grenzen

MusicBrainz, Deezer und iTunes können ohne zusätzliche Zugangsdaten abgefragt werden, sofern ihre öffentlichen Dienste erreichbar sind. Spotify, SoundCloud und Last.fm benötigen legitime Zugangsdaten. Es findet **keine Umgehung von API-Limits** statt. Suchbegriffe werden an aktivierte Metadatenanbieter übertragen.

**Wichtig:** Drittanbieter-Releases können in der PicardWulf-Trefferansicht ausgewählt und in Datei-Metadaten übernommen werden; sie werden **nicht als gefälschte MusicBrainz-Releases** in Picards natives Albumfenster eingespeist. Auch ein gestarteter asynchroner Speichervorgang ist noch kein bestätigter Schreib-Erfolg.

## Entwicklung und Tests

```bash
python -m unittest discover -s tests -v
```

Weitere technische Einzelheiten stehen in der [englischen Referenz-README](README.md). Lokale Tests ersetzen keine Live-Abnahme auf BMAX. Zusätzliche kostenpflichtige Runner oder Abonnements sind nicht vorgesehen.

[Quellcode](https://github.com/n-e-o-w-u-l-f/PicardWulf) · [Änderungen](CHANGELOG.md) · [Offene Prüfungen](LAST_TASKS.md) · [Lizenz](LICENSE)
