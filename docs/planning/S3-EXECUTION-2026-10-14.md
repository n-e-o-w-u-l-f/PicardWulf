# v1.0 S3 release ranking — 2026-10-14

Starting main HEAD: `562618ba12625ffefd525837e63955b40d79a4a9`, verified against origin and GitHub connector. LAST_TASKS identified S3 as next source phase. Canonical Legion checkout was clean; changes developed in a separate S3 worktree. Target remains **v1.0**, no release/tag or BMAX deployment.

## Decision model

`release-v2` retains the existing weights and 93.5/100 abstention threshold, with edition disqualification before scoring. These are **matching points, not a statistical probability**. Each sorted candidate includes the model, weights, contributions, edition conflicts, independent source support and distinct sibling-track support. All bounded adapter alternatives remain in the result payload; the review table shows a short view.

Recording identifiers cannot establish an edition. Year/date, region, barcode, edition comment, track/disc position and totals are distinct evidence; incompatible supplied fields reject a candidate, and missing required edition evidence abstains. Exact recording/release MBID conflicts reject matches, and preexisting native IDs require explicit review before an external proposal. Provider album IDs remain namespaced; external IDs never become release MBIDs.

Accent/case/punctuation and featuring/ft credit spelling normalize while retaining collaborators. Live/remix/clean/explicit/remaster/acoustic/instrumental and edition suffixes remain significant. Cross-script transliterations lacking verified alias evidence abstain; no guessed artist credit is written.

Album-local consensus counts distinct identified sibling recordings from **completed safe decisions**, not raw search alternatives, and only within the same source album ID, compatible album credit and edition. The cluster uses album artist, including VA across differing track artists. Cache entries are bounded at 200 and expire under the existing TTL. Two verified distinct sibling recordings can resolve a same-source, otherwise compatible edition-ID tie when competing editions have no such support; they cannot override conflicting edition fields or a low score. Unresolved editions still require review. Full tracklists are not fetched from extra endpoints; missing position/total evidence abstains instead of pretending a tracklist is complete.

Results retain the compatible `ready/review/ambiguous/no_match` consumer states and additionally expose `SAFE_WINNER/COMPLETE/AMBIGUOUS/INCOMPLETE`, stable reason codes and matching-point metadata. Unfinished providers remain INCOMPLETE. A successfully applied preview stores a private decision fingerprint. Repeated or conflicting automatic applications cannot replace it; an explicit subsequent refresh with conflicting results marks `LATER_RELEASE_CONFLICT` for review. Private provenance fields never become artist/albumartist.

Query cache keys now include edition, credit, duration and inferred-input context under `release-v2`. Snapshot normalization preserves internal fields on repeated admission; a regression first reproduced the lost duration/date/recording-ID problem and then passed after correction. Existing cache/queue data is retained; no schema migration or DB deletion.

## Evidence

- Curated **synthetic**, checked-in corpus: `tests/fixtures/s3_release_corpus.json`, 41 cases covering Curtain Call 2, solo/VA compilation, provider-name corruption, better Deezer/Spotify, single/album, two-disc matches/conflicts, wrong existing MBID, missing tags, Unicode and unverified transliteration, featuring and version/edition variants.
- Confusion matrix: safe assigned **10**, safe abstained **0**, unsafe assigned **0**, unsafe abstained **31**. False automatic release assignment **0/41**, provider-name artist corruption **0**, review/abstention ratio **31/41 = 75.61%**. Positive cases also pass the native proposal gate. These results describe the curated corpus only, not catalogue-wide accuracy or actual media writes.
- Dedicated edition, alternatives, cache-key, album-consensus, fixed-decision and normalization regressions ran RED→GREEN. Final whole-suite counts are recorded below.
- Real Qt synthetic 29k historical + 10k new identities: staging maximum **2,048**, extra peak **44.11 MiB**, event lag p95 **6.67 ms**, p99 **15.41 ms**, maximum **40.61 ms**, elapsed **60.38 s**, GUI SQLite calls **0**. Six backup/identity scenarios and forced-refresh generation fence pass; GUI media operations **0**.
- Real Qt manual forced refresh/backpressure and provider options/async credential acknowledgement probes PASS.

Commands: `python3 -m unittest discover -s tests -q`; independently `QT_QPA_PLATFORM=offscreen /tmp/picardwulf-s1-venv/bin/python tests/qt_scheduler_probe.py`, `tests/qt_native_refresh_probe.py`, `tests/qt_provider_policy_probe.py` on Legion's isolated S3 worktree. No network in these tests; synthetic files/temporary DB only.

## Contract references and limits

Existing documented response fields checked against [Spotify search reference](https://developer.spotify.com/documentation/web-api/reference/search), [Apple iTunes response documentation](https://developer.apple.com/library/archive/documentation/AudioVideo/Conceptual/iTuneSearchAPI/UnderstandingSearchResults.html) and the repository's existing MusicBrainz adapter contracts. No repeated Deep Research, paid account, new endpoint fan-out or personal-music API query.

**S0 / BMAX runtime remains OPEN (EXTERNAL_BOUNDARY)** as recorded in S1/S2. Existing access failure was not repeated; host trust was not bypassed. Picard was neither stopped nor restarted; original music and installed plugin were untouched. S4 media-write/rollback and S5 runtime/release acceptance remain separate. Source tests cannot establish BMAX responsiveness or a stable v1.0 release.

## Independent final review ledger

- Final: fixed Critical production snapshot omission — `test_production_snapshot_preserves_edition_and_fixed_decision` RED→GREEN. Both live and original snapshots now preserve release MBID and every edition field.
- Final: fixed Important unreachable later-conflict reopening — `test_forced_conflict_reopens_review_using_production_snapshot` RED→GREEN using the actual configured snapshot and controller polling. Frozen preview stays unchanged except private review status. Pending providers do not masquerade as new release conflicts.
- Final: fixed Important unused album consensus — `test_verified_siblings_resolve_same_source_edition_tie` RED→GREEN. Additional VA/different-artist and repeated-recording guards pass.
- Final: fixed incomplete-evidence state — `test_missing_edition_evidence_is_incomplete` RED→GREEN; stable `EDITION_EVIDENCE_MISSING` reason.
- Final: minor (deferred): native matching window still displays score with `%`; the aggregator dialog uses matching points. Align the native window wording in the next UI pass; no probability calibration is claimed here.
- Final: Ruling: cross-script aliases not independently verified — abstain rather than guess/transliterate artist credit; cost is additional manual review, not an unsupported automatic identity claim.
- Final: Ruling: complete remote tracklists unavailable in current bounded search adapters — preserve known position/total guards and abstain on missing evidence; cost is fewer unattended selections. Do not claim complete tracklist verification.
- Final: Ruling: explicitly confirmed manual native-release reassignment remains allowed — automatic rank/proposal gates protect prior MBIDs; cost if a user confirms a wrong alternative is an unsaved native assignment requiring correction. S4 media saves are a separate gate.
- Windows full-suite check exposed a preexisting test race: queued-count zero excluded final running workers. The regression now waits for all 115 persisted results as well as an empty queued count; production queue semantics were unchanged.

## Final verification and publication contract

- Final Legion suite: **161/161 PASS**, 4.818 seconds, including every review fix and the VA/different-artist recording guards. Compilation and `git diff --check` PASS.
- Final Windows suite: **161 run, 160 PASS, 1 platform skip**, 25.459 seconds. The corrected durable-drain assertion waits for persisted results rather than treating queued-count zero as completion.
- Post-fix real Qt backup/generation, manual refresh and provider/credential probes PASS; the full 39k load metrics above were collected in this S3 run.
- Publication is a source-only fast-forward commit to `main`. Check GitHub HEAD, LAST_TASKS, this evidence file and ranking/corpus blob IDs against the committed tree, and fast-forward the clean canonical Legion checkout. Exact commit/readback is reported in the task completion response; do not deploy or tag from this source checkpoint.

## Concurrent main integration and final combined verification

Before push, main advanced to `cb01721d888f0240656eaf08b20151e9996b6d01` (Deezer official-detail enrichment and background-search policy). Preserved the complete concurrent commit and merged it into S3; no overwrite or forced push. Resolved adapter/engine/test overlaps by keeping enriched metadata and numeric bounds, new edition fields, idempotent snapshots and context cache keys. Production snapshots also retain optional genre/label/composer/originaldate for the concurrent preservation policy.

The concurrent explicitly confirmed manual proposal may omit an unknown VA album credit; automatic selection must abstain without that credit. `test_missing_album_credit_cannot_auto_choose_va_edition` reproduced ready→review RED→GREEN. Original/VA compilation safeguards and both providers' higher-score winners remain covered.

**Combined Legion: 176/176 PASS**, 4.990 seconds; compilation/diff checks PASS. Combined Windows validation is performed from the exact merged source rather than the earlier checkout. Combined real Qt 39k identities: staging 2,048, extra peak 58.08 MiB, GUI lag p95 5.81 ms / p99 19.09 ms / max 51.42 ms, elapsed 71.14 s, GUI SQLite calls 0. Six backup cases, GUI media operations 0, and refresh generation fencing PASS. These combined results supersede the earlier source-only measurements above.

The S3 development commit is `28b2c69`; the publication merge also preserves the concurrent main parent. Target remains v1.0, BMAX/runtime/media gates OPEN.

**Final exact merged Windows source: 176 tests run, 175 PASS, 1 platform skip**, 19.166 seconds. Post-integration native refresh and provider/credential real Qt probes also PASS.
