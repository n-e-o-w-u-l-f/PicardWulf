<div align="center">

[English](README.md) · [Deutsch](README.de.md) · [Русский](README.ru.md) · [Français](README.fr.md) · [Español](README.es.md) · [Italiano](README.it.md) · [Português (Brasil)](README.pt-BR.md) · [Polski](README.pl.md) · [Українська](README.uk.md) · [日本語](README.ja.md) · [简体中文](README.zh-CN.md)

</div>

# PicardWulf v1.0

**Wyszukiwanie wydań w wielu źródłach, automatyczny wybór i bezpieczny zapis tagów w MusicBrainz Picard 3.0.**

> **Status:** wersja kandydacka. Testy lokalne zaliczone; rzeczywiste działanie na BMAX-B6, dostęp do API i zapis plików wymagają jeszcze sprawdzenia.

## Funkcje

- Jednoczesne wyszukiwanie w MusicBrainz, Deezer i Apple/iTunes oraz w Spotify, SoundCloud i Last.fm z autoryzowanym dostępem API.
- Po **Dodaj folder** ocena wydań według tytułu, wykonawcy, albumu, czasu trwania i rzeczywistych identyfikatorów.
- **Wygrywa wydanie z najwyższą wiarygodną oceną**, również z Deezer lub Spotify; MusicBrainz nie ma automatycznego pierwszeństwa.
- Sprzeczne identyfikatory, różne edycje i podobnie ocenione wyniki wymagają ręcznego wyboru.
- Natywne okno albumów Picard przyjmuje wyłącznie zweryfikowane pary MBID MusicBrainz. Identyfikatory innych dostawców pozostają osobne.
- Automatyczny wybór zmienia najpierw metadane w Picard. **Automatyczny zapis plików jest domyślnie wyłączony**; po świadomym włączeniu każda kopia zapasowa pliku audio jest weryfikowana SHA-256.
- Zachowane są funkcje NEOWULF, a kompilacje jednego artysty nie trafiają automatycznie do Various Artists. *Curtain Call 2* należy do Eminema.

## Instalacja

Zamknij Picard **3.0**, rozpakuj pakiet i uruchom **`Install-NEOWULF.cmd`** na koncie użytkownika pulpitu (`megal` na BMAX-B6). Docelowa ścieżka: `%APPDATA%\MusicBrainz\Picard\plugins3\neowulf_picard_repair`. Wadliwy `picard-cli.exe` nie jest używany. Aktywuj wtyczkę w **Options → Plugins**.

## Obsługa i bezpieczeństwo

**File → Add Folder** uruchamia wyszukiwanie. **Tools → PicardWulf** udostępnia wybór źródła i opcjonalny zapis z kopią zapasową; **Tools → NEOWULF** pokazuje status i naprawę nazewnictwa. Automatyczne zastosowanie wymaga jednoznacznej oceny co najmniej **93,5 %**. Wyszukiwane dane trafiają do włączonych dostawców zgodnie z zasadami API. Testy produkcyjne na BMAX-B6 pozostają otwarte.

## Testy

```bash
python -m unittest discover -s tests -v
```

[Pełna dokumentacja po angielsku](README.md) · [Zmiany](CHANGELOG.md) · [Stan](LAST_TASKS.md) · [Licencja](LICENSE)
