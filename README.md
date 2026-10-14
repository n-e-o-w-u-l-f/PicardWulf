<div align="center">

[English](README.md) · [Deutsch](README.de.md) · [Русский](README.ru.md) · [Français](README.fr.md) · [Español](README.es.md) · [Italiano](README.it.md) · [Português (Brasil)](README.pt-BR.md) · [Polski](README.pl.md) · [Українська](README.uk.md) · [日本語](README.ja.md) · [简体中文](README.zh-CN.md)

</div>

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

The shared results are ranked without source priority. **The highest-confidence, unambiguous release wins automatically**, including a Deezer, Spotify, SoundCloud or other non-MusicBrainz source. PicardWulf writes the winner and its score into private Picard metadata. If conflicting releases or identifiers prevent a safe decision, PicardWulf leaves the file for manual review. This selection changes Picard metadata, not the on-disk audio file by default.
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
Automatic media overwrite is OFF by default; an explicitly enabled auto-save mode can write a verified high-confidence winner after backup.

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

## Automatic multi-source release selection

After **Add Folder**, PicardWulf searches the enabled providers asynchronously and compares release candidates using a **source-neutral score**: track title, artist, album, album artist, duration, ISRC and compatible MusicBrainz recording ID. Independent provider agreement counts only for the **same named release**, not unrelated compilations or editions. Different known provider album IDs and MusicBrainz release IDs remain distinct.

A winner normally requires a matching score of at least **93.5/100** and a meaningful margin over a different release; questionable filename-derived guesses, artist conflicts and ambiguous editions are left for review. The candidate's actual provider appears as `~picardwulf_source` and the score as `~picardwulf_score` in Picard's private metadata.

- **Tools → PicardWulf → Automatische Release-Auswahl ein-/ausschalten**: on by default for metadata inside Picard.
- **Tools → PicardWulf → Automatisches Tag-Speichern mit Backup ein-/ausschalten**: **OFF by default**. Explicitly enabling it allows unattended writes for unambiguous matches, with a full verified backup of each audio file before Picard's asynchronous save. Always test on copies first.
- **Tools → NEOWULF → Gesammelte Treffer ansehen (alle Quellen)** shows the ranked candidate list and source. The release review dialog likewise displays provider-specific album IDs.

If Picard's native MusicBrainz lookup updates metadata while multi-provider searches are running, PicardWulf compares against the original file tags and may replace the temporary MusicBrainz choice with a better-scoring permitted provider. It never invents a MusicBrainz release ID for that provider. The external release appears in the PicardWulf review and file tags, **not as a counterfeit album in Picard's native release pane**.

## Important boundaries and limitations

- The combined provider candidates are displayed in **PicardWulf's own review UI**, and a reliable best release can automatically update Picard file metadata.
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

## Recover a large import without closing Picard

For an already-open Picard session that becomes sluggish while importing thousands of tracks, **do not terminate picard.exe, reboot Windows, delete the SQLite cache or force-save all files**.

If Picard's GUI still responds, first select **Options → Plugins** and disable PicardWulf. The active worker pool is stopped without closing Picard, while already-durable pending searches remain in the SQLite job database. This does not automatically save or discard Picard's loaded audio files.

To update **without quitting Picard**, while the PicardWulf plugin is disabled, run **`Install-PicardWulf-Live.cmd`** from a current checkout or unpacked package under the *same Windows desktop account*. Confirm `JA-PLUGIN-DEAKTIVIERT` only after verifying the plugin is disabled. The installer keeps the original plugin directory in a backup and deploys updated Python sources; **it never terminates or restarts Picard**. Re-enable the plugin in Options → Plugins to load the new code. If Picard is completely unresponsive, do not force changes to its live files: Windows Task Manager's non-destructive process statistics and **Analyze wait chain** can help distinguish a blocked UI from sustained CPU work.

The v1.0 S1 scheduler admits at most **2,048 uncommitted envelopes**, including the batch being written. Overflow stays represented by weak references to loaded Picard files and is retried in small GUI slices; staged work is explicitly **not yet durable**. One dedicated SQLite writer commits configurable batches (default 256) and handles result/status reads off the GUI thread. Qt queued signals deliver detached result and backup receipts; media copying/hashing also runs off-GUI. Database failure pauses dispatch and retains staging. Plugin disable returns immediately, with flush acknowledgement available in status; a subsequent enable waits in the background before taking database ownership. **Tools → PicardWulf → Hintergrundsuche pausieren / fortsetzen (ohne Picard-Neustart)** pauses/resumes provider dispatch while ingestion continues; up to two running jobs may complete. A backlog above 2,000 jobs at startup is automatically paused. [S1 tests and remaining BMAX acceptance](docs/planning/S1-EXECUTION-2026-10-14.md) distinguish source evidence from actual runtime deployment.

**Status:** Tested on Legion with 10,000 synthetic jobs; real BMAX process health and in-Picard hot-reload remain unverified, and the fix cannot modify code already imported by a running plugin until Picard's plugin manager reloads it.

## v1.0 architecture review and next implementation step

The sole target version remains **PicardWulf v1.0**. A source-backed stability assessment has identified remaining risks in GUI/SQLite operations, staging durability, provider quotas, uncalibrated release confidence and asynchronous media writes. The next step is **S1: bounded durable scheduling and completely non-blocking GUI integration**. No claim of Windows runtime remediation is made from this research alone.

- [Deep architecture / API research](docs/research/PICARDWULF-V1.0-DEEP-RESEARCH-2026-10-14.md)
- [Sequenced execution and acceptance gates](docs/planning/V1.0-NEXT-EXECUTION.md)

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
