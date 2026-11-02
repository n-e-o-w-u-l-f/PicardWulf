# PicardWulf — Künstler-Compilations, Aggro Ansage, Frank Zander, WWE

**Datum:** 2026-11-02 · Branch `feature/picard3-retention-policy-20261017` · PR #1 bleibt DRAFT.

## Nutzerauftrag und tatsächlich gewünschte lokale Ordner

Musikstamm der BMAX-B6-Installation laut Benutzer:

```text
G:\[--1--MUSiKz------------]\
├── Die Sekte\2001 - Ihr Nutten\
├── Die Sekte\2003 - Aggro Ansage Nr. 3\
├── Frank Zander\2022 - Meine coolsten Hits\
│   ├── CD 01\
│   └── CD 02\
└── ![-1.2-VARiOUS-ARTiSTz-]!\
    ├── WWE The Music\2009 - WWE The Music Volume 9\
    ├── WWE Anthology\2002 - WWE Anthology\
    │   ├── CD 01\
    │   ├── CD 02\
    │   └── CD 03\
    └── WWE Entrance Themes\YYYY - WWE Entrance Themes\
```

**„Die Sekte“ als Aggro-Ansage-Ablage ist ausdrücklich eine Benutzerpräferenz, keine Korrektur des offiziellen `albumartist`-Tags.** MusicBrainz führt `Aggro Ansage Nr. 1` in der Aggro-Berlin-Diskografie offiziell als `Various Artists` (https://musicbrainz.org/label/3634fa9a-8e09-4544-8980-272033d924f3); auch weitere Ansagen sind Multi-Artist-Labelsampler. Der Quellcode verändert dafür niemals offizielle Tags, sondern nur **bei dieser individuell bestätigten Albumfamilie** die relative Zielablage.

**Frank Zander – Meine coolsten Hits** ist eine belegte Künstler-Compilation mit **2 CDs, 40 Tracks**, Veröffentlichung **2022-02-04**. Quellen: https://frank-zander.de/wp/?album=jay-moon, https://www.jpc.de/jpcng/poprock/detail/-/art/frank-zander-meine-coolsten-hits/hnum/10810526. Falsche Zuordnungen durch Gastinterpreten wie Curry Sauce, Frank Schöbel, Fred Sonnenschein und Freunde werden nicht als eigene Alben abgetrennt. Ein behauptetes `CD 03`/`totaldiscs=3`, widersprüchliche Jahreszahl oder eine andere Edition führt zu **REVIEW** statt erzwungener automatischer Zusammenführung. Wenn Discnummer und Gesamtzahl verifiziert `1/2` oder `2/2` sind, erhalten beide CDs bei gleichem Albumordner eindeutige `CD 01`/`CD 02`-Unterordner.

**WWE Anthology** ist ein **eigenständiges** Set von drei CDs, veröffentlicht **2002-11-12**, mit 86 Entrance-Themes (https://corporate.wwe.com/about/news/2002/10-30-2002). Es darf weder mit `WWE The Music Volume 1–9` verwechselt noch in drei getrennte Albumgruppen zerrissen werden. Die lokalen `WWE Entrance Themes CD 1/2/…` bleiben unter einer eigenen Sammlerreihe und werden nur bei konsistenter Discidentität mit CD-Unterordnern behandelt.

## Implementierte Sicherheits- und Korrekturlogik

`neowulf_picard_repair/release_scope.py` ist der releaseweite, I/O-freie Katalog für genau diese Benutzeralben. Die **beiden** BMAX-Pfadgeneratoren `bmax_naming.classify_bmax` und `preset3_corrections.route_preset3` lesen denselben Scope vor einer gewöhnlichen VA-/Compilation-Klassifizierung. Dies verhindert, dass nur einer von Picards Import- oder Benennungswegen korrekt einsortiert.

- Frank Zander: Titelvarianten `Meine coolsten Hits`, `Frank Zander - Meine coolsten Hits`, `Meine coolsten Hits CD 1` und `CD 2` ergeben denselben Albumordner. Eine dritte CD wird abgewiesen. Gast-Songinterpreten ändern die releaseweite Albumzuordnung nicht.
- Die Sekte: Aus `Ihr Nutten`, `Die Sekte` oder releaseweit `Die Sekte/A.i.d.S.` entsteht ein Künstleralbum; `compilation` allein löst keine VA-Kategorie aus.
- Aggro Ansage Nr. 1–5 inklusive konkreter `Nr. 3x`-Neuauflage: auf Benutzerwunsch lokale Kategorie `Die Sekte`, aber `albumartist`-Tags bleiben original und Konflikte hinsichtlich Jahr/Edition werden zur Prüfung angehalten.
- WWE: `Anthology` ist ein belegtes 2002er Drei-CD-Album; `Entrance Themes` eine separate Sammlung, `The Music Volume N` die dokumentierte dritte Serie. Explizite `discnumber`/`totaldiscs`-Widersprüche werden abgewiesen, statt eine vierte Anthology-CD zu erzeugen.
- `bmax_naming.picard_bmax_fullpath` erhält **den aus dem aktiven Preset erzeugten Trackdateinamen**, den Musikstamm und vorhandene CD-Ordner. Ein `CD nn` wird nur mit nachvollziehbaren Disc-Tags hinzugefügt. Fehlende/konfliktbehaftete Release-Identität ändert **keine Tags** und löst **keine automatische Dateiverschiebung** aus.
- `tools/audit_artist_compilations.py` durchsucht nur ausdrücklich angegebene Dateiwurzeln und gibt getrennte reale Fundpfade, zusammengehörige Ziel-Alben, beobachtete Discnummern, unterschiedliche MusicBrainz-Release-IDs und sicherheitsrelevante Konflikte aus. `automatic_move_allowed=false` in jedem Ergebnis; das Audit verschiebt, löscht und retaggt niemals.
- Der Patch `compat/patches/picard-3.0.2-native-flac-move.diff` bleibt auf die offiziell verifizierte **3.0.2**-Quellversion gebunden. Der Live-Rechner hatte früher **Picard 3.0** gemeldet; ein ungezieltes Überschreiben des Programms wäre unsicher.

## Automatisierte Verifikation

- `tests/test_artist_compilation_20261102.py`: 15 neue gezielte Fälle, inkl. beschädigte VA-Credits, Originaltags erhalten, Frank 2-CD/kein CD3, Songfeat vs Release, Aggro X-Neuauflage, WWE-Disc- und Serienabgrenzung, Pfadwrapper ohne Namensverlust.
- Bestehende `tests/test_artist_compilation_audit.py` und `tests/test_artist_compilation_scope.py` sind an die **neu bestätigte lokale Aggro-Ablagepräferenz** angepasst und prüfen weiterhin, dass der offizielle `Various Artists`-Tag nicht verändert wird.
- Frischer Legion-Checkout: **498 Python-Unittests PASS**; `compileall`; offizieller, blob-geprüfter Picard-3.0.2-Core-Patch bytegenau erzeugt, `git apply --check` und Anwendung PASS, `git diff --check` PASS.
- Echter offizieller Picard-3.0.2-`ScriptParser` in isoliertem PyQt-Venv: **13 BMAX-Ordnerbeispiele PASS**, einschließlich Frank 2-CD und eigener Anthology-/Entrance-Discs; kein Medien- oder produktiver Profilzugriff.

## Produktionsstand und Rückfallplan

**BMAX-B6:** Desktop Commander hat nach einer vorherigen Quotenblockade wieder **99 % Remote-Kontingent** gemeldet und das korrekte BMAX-Gerät online angezeigt. Eine autorisierte `read_file`-Abfrage von `C:\Users\megal\AppData\Roaming\MusicBrainz\Picard.ini` ist jedoch bisher nur mit einem noch offenen `call_id` und wiederholtem `lookup_timeout` belegt. Kein gelesener Inhalt, keine SHA-Bestätigung und keine produktive Änderung darf unterstellt werden.

**Keine installierte Picard-Version, aktive Preset-3-Dateibenennung, Benutzer-Picard.ini, Musikdatei oder Tags wurden in dieser Arbeit verändert.**

Bevor real etwas geändert wird: BMAX aktives Programm/Profil/Plugin-Version vollständig lesen; exakten Original-SHA der aktiven Skript-ID und Picard.ini sichern; alle relevanten Tracks vor- und nach dem Eingriff als reine Pfadvorhersage prüfen. Bei abweichender Versions-/Datei-/Discidentität verweigern und Rückfall erhalten. Ein Script-/Code-Commit ist **keine** Windows-Produktionsfreigabe.
