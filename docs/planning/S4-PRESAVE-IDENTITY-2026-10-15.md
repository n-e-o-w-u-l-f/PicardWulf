# PicardWulf v1.0 — S4 pre-save identity hardening (2026-10-15)

**Scope:** source-only hardening; no release/tag, BMAX deployment, Picard restart, original audio changes, or paid integration.

## Failure and risk

The full-media backup checks a complete copy and its SHA-256, size,
mtime and file identity. Before this change, the queued Qt callback could
receive proof later and call asynchronous File.save() after the original had
already changed on disk. Protecting only mutable Picard metadata did not detect
an external editor or filesystem replacement.

**FAILURE_FINGERPRINT:** source -> background backup -> delayed Qt receipt ->
File.save(); source changes after backup; acceptance: do not write using a
stale receipt. **Classification:** GOVERNANCE_GAP, second identity gate missing.
No confirmed occurrence on BMAX.

## Implemented

- A pre-save helper compares device, inode, byte size and nanosecond mtime
  to the persistent receipt, rehashes original and backup on a background
  thread and rechecks source identity. Missing identity fields, changed bytes
  despite identical size/mtime, replaced inode and modified backups all fail.
- A second queued Qt acknowledgement is mandatory before File.save() in BOTH
  automatic save and manually confirmed tag write. No GUI-thread file hashing.
- Pausing automatic scanning or editing Picard metadata during verification
  stops the pending automatic save. Verified backups remain available.
- Asynchronous post-save readback and explicit non-overwriting restoration
  are unchanged.

## Validation and limitations

- 223 Python unit/contract tests PASS on Legion, including original byte
  changes with unchanged size/mtime, inode replacement, backup tampering,
  missing receipt identity and save success/error/pause/metadata gates.
- The actual-Qt 39k loader/backup probe covers another rejected identity
  scenario, but Legion system Python has no PyQt6: real Qt execution is
  **NOT RUN**, never described as PASS. No system packages installed.
- The inherent TOCTOU interval between worker acknowledgement and subsequent
  asynchronous Picard save remains. Strict atomicity would require Picard
  internal coordination or an exclusively controlled file operation.
- Real MP3/FLAC/OGG/M4A write/rename/restore and BMAX Picard session checks
  remain OPEN due to the authorized Windows access boundary.

**Release gate:** v1.0 remains a candidate pending BMAX acceptance.
