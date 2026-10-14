<div align="center">

[English](README.md) · [Deutsch](README.de.md) · [Русский](README.ru.md) · [Français](README.fr.md) · [Español](README.es.md) · [Italiano](README.it.md) · [Português (Brasil)](README.pt-BR.md) · [Polski](README.pl.md) · [Українська](README.uk.md) · [日本語](README.ja.md) · [简体中文](README.zh-CN.md)

</div>

# PicardWulf v1.0

**Ricerca delle release su più servizi, scelta automatica e scrittura sicura dei tag per MusicBrainz Picard 3.0.**

> **Stato:** versione candidata. Test locali superati; l'attivazione su BMAX-B6, le API reali e il salvataggio dei file devono ancora essere verificati.

## Funzioni

- Ricerca su MusicBrainz, Deezer e Apple/iTunes, con Spotify, SoundCloud e Last.fm disponibili tramite credenziali API autorizzate.
- Dopo **Aggiungi cartella**, confronta brano, artista, album, durata e identificativi delle release di tutte le fonti.
- **Vince la release con il punteggio più alto**, senza priorità automatica per MusicBrainz; può vincere anche Deezer o Spotify.
- Edizioni ambigue, ISRC incompatibili e artisti discordanti richiedono conferma manuale.
- Nel pannello album nativo di Picard sono ammessi soltanto veri MBID MusicBrainz di release e registrazione, mai ID esterni falsificati.
- I metadati vengono aggiornati in Picard; **il salvataggio automatico dei file è disattivato** per impostazione iniziale. Dopo l'attivazione esplicita, ogni file viene copiato integralmente e verificato con SHA-256 prima della scrittura.
- Rimangono le regole NEOWULF e la correzione delle compilation attribuite erroneamente a Various Artists. *Curtain Call 2* rimane di Eminem.

## Installazione

Chiudi Picard **3.0**, estrai il pacchetto, esegui **`Install-NEOWULF.cmd`** con l'account desktop (`megal` su BMAX-B6) e abilita il plugin in **Options → Plugins**. La destinazione è `%APPDATA%\MusicBrainz\Picard\plugins3\neowulf_picard_repair`. Non viene usato il `picard-cli.exe` difettoso.

## Utilizzo e sicurezza

**File → Add Folder** avvia la ricerca; **Tools → PicardWulf** gestisce scelta, revisione e salvataggio opzionale; **Tools → NEOWULF** mostra fonti e riparazione dei nomi. È necessario un punteggio non ambiguo di almeno **93,5 %**. Le richieste inviano dati di ricerca ai provider abilitati, rispettandone condizioni e limiti. La verifica operativa su BMAX-B6 resta aperta.

## Sviluppo

```bash
python -m unittest discover -s tests -v
```

[Documentazione inglese completa](README.md) · [Modifiche](CHANGELOG.md) · [Stato](LAST_TASKS.md) · [Licenza](LICENSE)


## v1.0 S2 – stato del codice

Sono implementati consenso per fornitore, stati di disponibilità, limiti e attese persistenti e gestione sicura dei token. Le risposte incomplete non attivano modifiche automatiche. Le verifiche anonime MusicBrainz/Deezer/iTunes e 145 test passano; fornitori autenticati e BMAX restano da verificare. Nessun nuovo abbonamento.

[S2 evidence / Nachweise](docs/planning/S2-EXECUTION-2026-10-14.md).
