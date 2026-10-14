# PicardWulf v1.0 — S2 provider-policy source checkpoint

**Target: v1.0 only.** Baseline HEAD `c492fa8a7b6efb24f76b51e5f5dcb83a8dbb317a` was verified in clean Windows/Legion checkouts before editing. The existing completed research was reused, not restarted. Work is isolated in `/home/andreas/Projekte/.worktrees/PicardWulf-S2-20261014`.

## Implemented behavior

- Every source has `AVAILABLE`, `CREDENTIALS_REQUIRED`, `QUOTA_WAIT`, `TEMPORARY_ERROR`, `RESTRICTED` or `DISABLED`, an explicit reason and an observed/unprobed distinction. Empty **valid** lists mean no matches; malformed/missing schemas and missing tokens are errors. Optional unavailable sources do not require new purchases and do not masquerade as successful searches.
- One SQLite writer persists capacity-one token buckets, provider hourly counters, shared MusicBrainz search/lookup limits, cooldowns and circuit-breaker state. Configuration is validated; the operator may choose 1–3,000 requests/hour per provider. Provider minimum delays and SoundCloud's separate conservative auth budget remain in force. Reload and credential updates do not reset quotas.
- Retry-After seconds and HTTP dates are honored without truncating a longer server wait. 401/403 stop repeated requests until an operator changes credentials or re-enables the source. 429/503/network/schema errors retain per-provider attempts and retry deadlines; retries have jitter and a three-attempt bound for actual failures. Budget-only deferral consumes no failure attempt. Three temporary failures open the persisted circuit for at least 180 seconds.
- Short pacing (at most eight seconds per request) waits only in the worker and is cancellation-aware. Multi-request MusicBrainz/Last.fm adapters are serialized per source, preventing search→lookup/enrichment from restarting indefinitely. Long waits return to durable queued retries.
- Partial results are visible for review but have `pending_providers`/`incomplete_providers`; they cannot trigger auto-apply or enter the complete album pool. A retry result and its durable job state are written atomically. Successful providers resume from checkpoints rather than being queried again.
- Unchanged cached jobs are reused. A bounded normalized artist/album pool reuses compatible exact-track decisions from complete source work. It never bypasses this job's already unfinished/error checkpoints. Newly found strong MusicBrainz search results still allow better Deezer/iTunes/other eligible candidates to compete. Last.fm enrichment is limited to promising candidates lacking album information; exhaustive mode considers every accessible source. Recording MBIDs use official direct lookup; cross-source ISRC resolution remains budgeted and checkpointed.
- Spotify remains optional: the operator must confirm that the configured app **already** has legitimate access; the actual token/search response then determines availability. No app, account, subscription or entitlement is created. This addresses the documented development-mode eligibility restrictions without assuming a new free entitlement. [Official Spotify migration contract](https://developer.spotify.com/documentation/web-api/tutorials/february-2026-migration-guide).
- SoundCloud supports existing registered clients via HTTP Basic client credentials and single-use refresh-token rotation. Auth quota is reserved **before** persisting the consumed/uncertain marker. Only that in-memory reservation may cross its own pending fence; a reloaded uncertain token is never retried. Rotated tokens are encrypted and acknowledged before catalogue use. A failure before any HTTP clears the pending marker safely; uncertain network outcomes require fresh legitimate credentials. Public-resource grants do not initiate a user-account login/PKCE workflow. No plaintext fallback or registration is added. [Official SoundCloud OAuth/API contract](https://developers.soundcloud.com/docs/api/guide).
- Credential changes run off-GUI, under the OAuth locks, merge the latest encrypted vault and return asynchronous acknowledgement. Environment client secrets are not copied into SQLite or token-rotation persistence. Internal expiry/pending fields are not editable in the credentials dialog.
- HTTPS endpoint allowlists, disabled redirects, response size/type/schema checks and fixed reason codes protect secrets. No raw auth responses, HTTP messages, artwork or credentials enter the catalogue cache. Apple Search's observed JavaScript MIME label is accepted only at the allowlisted iTunes endpoint and still parsed strictly as JSON; JSONP is rejected. Deezer caches only selected text/identifier fields, never album images. [Official Deezer developer restrictions](https://support.deezer.com/hc/en-gb/articles/360011538897-Deezer-FAQs-For-Developers).
- Tools now exposes provider consent, exhaustive mode, existing Spotify access and request budget. Source status uses cached worker observations; SQLite/media I/O remains off-GUI. Original NEOWULF scripts, plugin UUID/version, music files and existing Picard session are preserved.

## Evidence

- **145 unit/contract tests PASS on Legion**; compilation passes. Six-provider capability/parser coverage includes 401/403, 429, 503, network loss, invalid JSON/schema/type, oversized response, HTTP-date/7,200-second waits, disabled providers, missing/invalid tokens, persistent budgets/circuit, uncertain refresh, quota-before-consumption and worker-side vault merge.
- Independent read-only review found three P1 defects: refresh blocking its own pending marker; quota restarting multi-request adapters forever; album pool bypassing this job's deferred checkpoint. All were reproduced by failing regressions, fixed and verified green. No deferred findings. A live iTunes MIME incompatibility was also reproduced by a failing fixture and corrected without executing scripts.
- **Real Qt 39k load PASS:** 29,000 historical + 10,000 new synthetic identities; staging maximum 2,048; additional peak 36.54 MiB; event-loop lag p95 **4.24 ms**, p99 **8.18 ms**, max **32.17 ms**; elapsed 20.84 s; zero GUI SQLite calls. Accelerated fixture pacing is not BMAX acceptance.
- Existing real Qt six-case backup/identity, forced-result generation and manual-force backpressure probes pass. New real Qt operator-dialog probe confirms consent/budget settings, hidden internal token fields and non-blocking credential acknowledgement. No actual credentials, personal track data or original media are used by these tests.
- **Anonymous live probes PASS** on MusicBrainz, Deezer and iTunes: each returned a valid catalogue list containing one result for a fixed public `Bach Air` query. Only aggregate status/counts were recorded; no body/artwork cache or personal music was submitted. Deezer public search is tested independently of app-registration availability.
- Spotify, SoundCloud and Last.fm are **UNAVAILABLE_FOR_THIS_VALIDATION / unprobed**: no legitimate credentials were supplied to these probes. Synthetic parser/auth/policy tests are not proof of live entitlement, token storage on BMAX or individual quota access.

Reproduce locally (network probe is opt-in, outside unittest discovery):

```sh
python3 -m unittest discover -s tests -q
python3 -m compileall -q neowulf_picard_repair tests
QT_QPA_PLATFORM=offscreen /tmp/picardwulf-s1-venv/bin/python tests/qt_scheduler_probe.py
QT_QPA_PLATFORM=offscreen /tmp/picardwulf-s1-venv/bin/python tests/qt_native_refresh_probe.py
QT_QPA_PLATFORM=offscreen /tmp/picardwulf-s1-venv/bin/python tests/qt_provider_policy_probe.py
python3 tests/public_provider_probe.py
git diff --check
```

## Remaining gates

**S0/BMAX runtime remains OPEN**, with the prior SSH host-key refusal preserved; no trust bypass or repeated failed access mechanism was attempted. No Picard shutdown/restart, deployment, music modification or new paid service occurred. S2's credentialed live validation remains OPEN where credentials are unavailable. Next source work is S3 release/edition ranking and abstention; S4 real-media save receipts/rollback and S5 controlled deployment/complete translations still require their separate gates. This is not a stable v1.0 release/tag.
