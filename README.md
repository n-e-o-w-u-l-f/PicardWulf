# PicardWulf v1.0

**Multi-source metadata discovery, MusicBrainz release matching and safe tag writing for MusicBrainz Picard 3.0.**

PicardWulf combines the original NEOWULF naming repair with a persistent metadata queue, provider-based candidate review and optional native Picard album association.

> **Release status:** v1.0 candidate. Unit tests passed locally; the GUI integration, Windows BMAX-B6 runtime, actual metadata-provider connectivity and asynchronous save behavior have **not** yet been live-verified. Do not bulk-save a music library before testing on a small copy.

## Features

- **Add Folder**: after Picard loads files, queue background metadata discovery without blocking the UI; remain compatible with the regular MusicBrainz lookup and refresh.
- **Unified sources**: MusicBrainz, Deezer public catalogue and iTunes Search, with optional authenticated Spotify, SoundCloud and Last.fm APIs. Providers may be unavailable or impose restrictions; no authentication bypass, HTML scraping or additional paid services.
- **Result comparison**: preserve source provenance; assess artist, track, album, duration, MusicBrainz IDs and ISRC; persist cache and pending jobs locally.
- **Native album matching**: after explicit selection of an authentic MusicBrainz release + recording pair, use Picard's `move_file_to_track` to link the file into its normal album pane. External streaming IDs are never passed off as MusicBrainz release IDs.
- **Tag writing**: show proposed differences first, require an explicit confirmation, and make a full SHA-256-verified backup of the source audio file before invoking Picard's normal asynchronous save.
- **NEOWULF naming**: preserve custom filename rules and fix the incorrect `Compilation ⇒ Various Artists` assumption. *Eminem – Curtain Call 2* should remain attributed to Eminem, not Various Artists or a metadata provider.

## Windows installation

1. Use **MusicBrainz Picard 3.0** and sign in as the Windows desktop owner (`megal` on BMAX-B6).
2. Close Picard and preserve any unsaved work.
3. Download a vetted release archive, extract it, and launch **`Install-NEOWULF.cmd`**. The CMD launcher is required because the PowerShell script is not code-signed; it does **not** change the machine-wide execution policy.
4. PicardWulf installs in `%APPDATA%\MusicBrainz\Picard\plugins3\neowulf_picard_repair`. It does not invoke the known-incomplete frozen `picard-cli.exe` or directly edit `Picard.ini`.
5. Open Picard, enable the plugin under **Options → Plugins**, and use its **Tools → NEOWULF / PicardWulf** actions. Enable external sources only with their legitimate API access.

> **Caution:** Tag saving may also apply Picard's configured file rename/move options. Check the effective naming profile first. Keep the audio backups until the result is verified.

## Testing

Run the Python source tests locally:

```sh
python -m unittest discover -s tests -v
```

The v1.0 source candidate previously passed 90 local unit/contract tests. Mock provider responses are not proof of live API access or Windows GUI behavior. Before treating the version as production-ready, verify plugin activation, queue processing, native album linking and restored audio files after tag writing in a controlled BMAX test.

## Development and licensing

- Sources: `neowulf_picard_repair/`
- Tests: `tests/`
- Changelog: `CHANGELOG.md`
- Installer: `Install-NEOWULF.cmd`, `Install-NEOWULF.ps1`
- Existing GitHub Actions are not required; use the local build runner.
- Preserve personal credentials only in the local encrypted Windows store. Never commit them.
- Code license: see `LICENSE`.

The upstream reference implementation and plugin APIs are maintained by [MusicBrainz Picard](https://github.com/metabrainz/picard). PicardWulf is an independent project and is not affiliated with MetaBrainz.
