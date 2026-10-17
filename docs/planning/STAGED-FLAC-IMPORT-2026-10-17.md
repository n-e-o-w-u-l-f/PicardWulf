# PicardWulf v1.0 – sicherer separater FLAC-Eingangsimport

Checkpoint: 2026-10-17, Source-Branch `feature/picard3-retention-policy-20261017`. **Nicht in BMAX installiert, nicht live in Picards Speichervorgang eingebunden.**

## Zweck und Umfang

Picards öffentlich dokumentierter `file_pre_save_processor` bietet keinen belegten Rückgabewert zum Abbrechen eines nativen Speichervorgangs. Der eigentliche `_rename()`-Konflikt wird erst nach der Tag-Speicherung entschieden. Daher bleibt eine Änderung dieser Routine oder ein erzwungenes automatisches Überschreiben auf dem laufenden Windows-Picard verboten, solange weder Schnittstelle noch Windows-Laufzeit erwiesen sind.

`neowulf_picard_repair/staged_flac_import.py` stellt jetzt unabhängig davon **ausführbaren Importcode** bereit. Er verarbeitet eine einzeln vollständig getaggte und dekodierbare FLAC-Datei aus einem **separaten Eingangsordner** gegen einen expliziten Zielpfad in der Musikbibliothek. Der Import wird durch `import_staged_flac(source, destination, staging_root=..., library_root=..., recovery_root=...)` aufgerufen; Standard ist `apply=False` (nur Plan). Erst explizites `apply=True` autorisiert Dateiarbeit in einer getrennten Staging-/Zielstruktur.

| Ergebnis | Operation bei ausdrücklichem `apply=True` | Wiederherstellung |
|---|---|---|
| `CREATED` | Eindeutig freien Zielnamen aus verifizierter temporärer FLAC-Datei exklusiv per Hardlink erstellen | Eingangsdatei bleibt unverändert |
| `SKIPPED` | Vorhandene größere/gleich große passende Zieldatei behalten | Eingangsdatei bleibt unverändert |
| `REPLACED` | Kleinere passende Ziel-FLAC nach SHA-256-Backup durch verifizierte größere FLAC atomar ersetzen | Alte Ziel-FLAC bleibt im separaten `recovery_root` |
| `REVIEW` | Uneindeutige Zuordnung oder abweichende ID; **nichts überschreiben** | Kein Import |
| Ablehnung | Fehlende FLAC-Dekodierung, ungültige Verzeichnisse, Link-/Hardlink-Konflikt, konkurrierende Sperre, unlesbare Datei | Keine absichtlich ausgeführte Ersetzung |

**Schutzmechanismen:** Mit Mutagen wird der tatsächliche Dateityp samt Artist/Title/Album/Disc/Track und Dauer kontrolliert; verfügbare Recording-/Release-IDs, ISRC, Barcode, Datum und Albumartist dürfen sich nicht widersprechen. Für beide vorhandenen FLAC-Streams ist ein vollständiger `flac -t`-Dekodiertest erforderlich. Die drei Wurzeln müssen bereits existieren, getrennt sein und dürfen sich nicht überschneiden. Medienpfade mit symbolischen Links, fremden Wurzeln oder identischen Inodes werden abgelehnt. Eine exklusive Dateisperre pro Ziel verhindert parallele Importoperationen; nach einem Absturz wird sie nicht eigenmächtig übernommen. Zielstaging, SHA-256-Kontrolle, Flush und atomarer Austausch/Exklusivanlage werden getestet. **Die Eingangskopie wird niemals gelöscht.**

## Erreichte Verifikation

- Synthetic temporary tests: `WOULD_REPLACE`, `WOULD_CREATE`, `REPLACED`, `SKIPPED`, `CREATED`, geänderte Song-ID, Ablehnung von MP3, zerstörtem Decoder, Wurzelüberschneidung, Directory-Symlink, Inode-Kollision, vorhandener Sperre und zeitgleichem Anlegen eines Ziels.
- Disposable real-FLAC test: FLAC-Stream erzeugt, Music-Tags geschrieben, Daten vergrößert, Import mit Original-SHA-Backup ausgeführt, bestehende und neue Zieldatei byteweise verifiziert. Unter Legion mit verfügbarem `flac`/Mutagen.
- **294 Python-Regressionstests PASS**, `compileall` PASS, `git diff --check` PASS im letzten bestätigten lokalen Legion-Checkout `18387d6486730455db9d0af1b7588f7f903bc33b`. Der GitHub-Code wird nach dieser Dokumentationsänderung erneut gelesen.

## Blocker und klare Grenzen

1. **Noch kein aktiver automatischer Picard-Dateiimport:** Es gibt einen eigenständigen, getesteten Python-Funktionskern, aber keinen zugelassenen nativen Picard-Abbruch-/Weiterleitungs-Hook und keine aktivierte Bedienoberfläche. Die installierte Dateibenennung/Preset 3 wurde nicht geändert.
2. **Standalone-Kommandozeileneinstieg:** Ein zusätzlicher Repository-Schreibversuch für `scripts/picardwulf_staged_flac.py` wurde mit einer generischen externen Sicherheitsablehnung beendet. Nach Readback existiert die Datei nicht. Ein gleichwertiger Zweitversuch über anderen Transport ist ausgeschlossen; Grund über die generische Ablehnung hinaus unbekannt.
3. **Windows/BMAX:** Echte Picard-3-Pfade, Hardlink-Unterstützung, aktive Windows-Dateisperren, mitgelieferter FLAC-Decoder, Profile/Preset 3 und die Wiederherstellung sind weiterhin auf BMAX-B6 als `megal` zu prüfen. Kein Einsatz auf Originalmusik vor einer isolierten Windows-Abnahme.
4. **Kein heimliches Entfernen:** MP3-Bestandsbereinigung und Gold-CD-Entfernung erfolgen über die getrennten bereits vorhandenen Prüfpfade; dieser Importer löscht weder MP3 noch FLAC im Eingang.
5. **Identität ≠ Dateigröße:** Eine größere FLAC kann vor allem größere Metadaten/Artwork enthalten und ist nicht zwingend klanglich besser. Benutzerregel „größere bevorzugen“ wird nur nach Identitäts- und FLAC-Integritätsprüfung angewandt.

## NEXT

Windows-Zugang zulässig verifizieren; auf einem vollständig isolierten temporären Datensatz und mit deaktivierter nativer Picard-Überschreibung CREATE/SKIP/REPLACE/Recovery, Original-Windows-Dateisperren und neue Zielpfade testen. Danach entscheiden, ob der Staging-Importer als separat autorisierte Importaktion eingebunden werden kann, ohne den Picard-3-Dateiobjekt-Lebenszyklus zu verletzen. Bis dahin bleibt Pull Request #1 **DRAFT**, kein Merge und keine Live-Bereinigung.
