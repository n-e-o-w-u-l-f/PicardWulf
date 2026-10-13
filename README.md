# PicardWulf v1.0

**Universal Metadata & native MusicBrainz release association for Picard 3.0**
Target repository: <https://github.com/n-e-o-w-u-l-f/PicardWulf>

PicardWulf extends the existing NEOWULF naming repair with shared catalogue searches,
file-load hooks, a persistent search queue, confidence-based candidate comparison,
**native Picard album-window linking** for verified MusicBrainz release/recording pairs,
and **explicitly approved tag saving with a full verified audio-file backup**.

> **Status:** Source/tests completed; Windows BMAX runtime installation and live API calls
> not yet verified. Tests with simulated provider responses are not live provider proof.
> GitHub repository is published at the target URL. This does not prove successful
> activation, provider responses or an end-to-end Windows save.

## Requirements

- MusicBrainz Picard **3.0**, with plugin API `3.0` and PyQt6.
- Windows 11 BMAX-B6, desktop account **`megal`** for the supplied installer.
- Sufficient storage for **one full copy of each audio file before writing tags**.
- No additional paid services, CI runners or subscriptions are installed by PicardWulf.

## Install or upgrade v2/v3 (BMAX)

1. Close Picard normally and keep unsaved Picard edits safe.
2. Unpack `PicardWulf-v1.0.zip` in an ordinary directory.
3. Double-click **`Install-NEOWULF.cmd` while signed in as `megal`**. Do *not* run
   the unsigned `.ps1` directly: the CMD entry point uses a per-process PowerShell
   policy. Any higher-level policy remains effective.
4. The installer copies the plugin to `%APPDATA%\MusicBrainz\Picard\plugins3\neowulf_picard_repair`
   without invoking the broken bundled `picard-cli.exe`, without editing `Picard.ini`
   and without writing to audio files.
5. It recognizes **unmodified previous v2 and v3 source** via pinned SHA-256 values,
   preserves the complete previous plugin directory in a non-discovered backup folder,
   then places v1.0. Unknown modifications are not overwritten.
6. After Picard opens, select **Options → Plugins → PicardWulf v1.0** and enable
   the plugin if not already enabled. The UUID is kept across v2/v3 to preserve
   compatible settings and plugin identity.

If plugin activation fails, inspect Picard's plugin log; the installer only verifies
that files were placed correctly, not that Picard enabled them.

## Workflow

### 1. Add a folder

Picard's **Folder hinzufügen / Add Folder** loads audio files. The plugin's official
`register_file_post_load_processor` schedules their metadata lookup, and a track
metadata hook schedules updates after Picard's native MusicBrainz refresh.

- **MusicBrainz:** official recording search and release relationships, 1+ second throttle.
- **Deezer:** public catalogue search while the official service permits it.
- **Apple iTunes Store Search:** public catalogue search, distinct from Apple Music Library API.
- **Spotify:** official authenticated Web API, if your existing client credentials are valid.
- **SoundCloud:** official authenticated track search, if an OAuth token is supplied.
- **Last.fm:** authenticated `track.search`, if an API key is supplied.

Unavailable/rejected sources report status; there is no HTML scraping, API-limit bypass,
free account creation or subscription purchase. Enabling the lookup hook means search
fields such as artist and title are sent to the enabled providers. Creds are Windows
DPAPI-encrypted in `%LOCALAPPDATA%\NEOWULF\Picard3\credentials.dpapi`.

The shared results are **proposals**, not autonomous replacements for Picard metadata.
SQLite persists cache (72 h) and outstanding jobs, including large folder queues.
ISRC and MusicBrainz IDs are treated as exact identifiers; artist/title/duration/album
conflicts reduce confidence or veto a match. Tags inferred from `Artist - Title.ext`
are marked as lower-confidence. No provider's name is ever written into `albumartist`.

### 2. Show candidate results

**Tools → NEOWULF → Gesammelte Treffer ansehen (alle Quellen)** shows provenance,
confidence and source status. **Tools → PicardWulf → Album-Matching & Tags überschreiben
(mit Backup)** opens the per-file release/tag review. You can also right-click a file
and choose **PicardWulf: Multi-Source-Release/Tags auswählen**.

### 3. Associate a real release in Picard's native album window

Choose a verified **MusicBrainz** candidate with a valid *release MBID and recording MBID*
and press **In Picard-Album zuordnen**. After confirmation, PicardWulf invokes
`api.tagger.move_file_to_track(file, release_mbid, recording_mbid)`; Picard loads
that release in its **normal album pane**. External provider IDs are never
misrepresented as MusicBrainz releases. Spotify, SoundCloud, Deezer, Last.fm and Apple
results can influence discovery and the ISRC bridge, but they are not fictitious native
Picard releases.

### 4. Preview and overwrite tags (opt-in)

Select a candidate, click **Tag-Änderungen ansehen**, and review the exact field changes.
Then click **Tags überschreiben + Backup** and explicitly approve the change. Before
editing Picard metadata, PicardWulf makes a separate full backup of that audio file at
`%LOCALAPPDATA%\NEOWULF\PicardWulf-v1.0\Audio-Backups`, checks its SHA-256 and size,
and refuses the operation if backup integrity or disk space fails. After that, the
normal `file.update()` and `file.save()` API performs **asynchronous native Picard saving**.
The status in Picard must confirm its eventual success. Picard preferences for file
renaming or moving **may also apply** when saving; check your active naming script first.
No silent batch overwrite is enabled.

**Tag mapping:** artist/title/album and a valid ISRC may be suggested. Only MusicBrainz
candidates may write `musicbrainz_albumid` and `musicbrainz_recordingid`; albumartist
is protected against `Various Artists`/provider confusion.

### 5. Existing NEOWULF file naming and Eminem

**Tools → NEOWULF → Konfiguration prüfen** checks the *effective* naming script and
active profiles. **VA-Sortierung reparieren (mit Backup)** patches only one uniquely
identified old NEOWULF naming script after a confirmation and `Picard.ini` backup.
Compilation alone does not imply Various Artists. MusicBrainz Release Group
`77c24600-5610-473b-876e-09d8a42296b7` is recognized as **Eminem – Curtain Call 2**.
Apple Music remains provider provenance, never albumartist.

## Important boundaries and limitations

- The combined provider candidates are displayed in **PicardWulf's own review UI**.
  Only **authentic MusicBrainz release entities** are loaded in Picard's native album pane.
  External catalogues cannot be injected as counterfeit MusicBrainz releases.
- Unrecognized plugins/active-profile overrides and extra API sources require separate
  validation; v1.0 explicitly implements six providers, not arbitrary websites.
- An installer file copy is not proof of Picard plugin activation. Unit tests do not
  validate Windows GUI runtime, licensing/access of providers, or live tagging outcome.
- This tool does not modify `Picard.ini` during installation, and only explicit naming
  repair changes its own settings. Background workers never write audio tags.
- A verified media backup is kept even after successful asynchronous saving; restoration
  is manual, in case a later Picard save or move behaves unexpectedly.

## Development and verification

Source lives in `neowulf_picard_repair/`. Local tests:

```bash
python -m unittest discover -s tests -v
```

No paid GitHub Actions are required; use your existing local runner. Platform/GUI
smoke tests on the actual BMAX Picard 3 installation remain an explicit release gate.

## GitHub publication

Repository target is **only** `n-e-o-w-u-l-f/PicardWulf`. For a repository the connected
assistant GitHub integration cannot currently access, **`Publish-PicardWulf.cmd`**
provides a manual, consent-based route using an existing authenticated GitHub CLI.
It never embeds credentials or force-pushes, does not delete remote files, and requires
operator approval before creating a missing private repository.

The GitHub source is published. A verified native Windows runtime and live API results
are still required before announcing a production-ready release.

## Previous installer failure

The earlier v1 installer called a broken frozen `picard-cli.exe` and failed with
`No module named 'picard.cli.completions'`. This is **not** retried in v1.0.
The old staged directory from that fehlgeschlagenen Registrierungsversuch remains untouched.

Sources: [Picard plugin v3 API](https://github.com/metabrainz/picard/blob/master/docs/PLUGINSV3/API.md),
[local plugin loading](https://github.com/metabrainz/picard/blob/master/docs/PLUGINSV3/LOCAL_NON_GIT.md),
[MusicBrainz API](https://musicbrainz.org/doc/MusicBrainz_API),
[Spotify Web API](https://developer.spotify.com/documentation/web-api/),
[SoundCloud developers](https://developers.soundcloud.com/docs/),
[Last.fm API](https://www.last.fm/api/),
[iTunes Search API](https://performance-partners.apple.com/resources/documentation/itunes-store-web-service-search-api/).
