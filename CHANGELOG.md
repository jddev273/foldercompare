# Changelog

## 0.1.5 - 2026-09-13

- Fail closed when normalized cross-root paths differ in exact spelling, preventing case-sensitive Windows paths from being falsely verified.
- Re-scan both trees before returning results and discard verification if paths, types, sizes, timestamps, or link state changed during the run.
- Add deterministic regressions for case-only cross-root names and files added during verification.
- Extend packaged Windows GUI proof to execute and verify the add-only missing-file repair, not just open its confirmation dialog.

## 0.1.4 - 2026-09-13

- Make repair add-only: copy only missing regular files and never overwrite existing destination data.
- Publish staged repairs with an atomic no-replace operation, closing the commit-time destination race.
- Fail closed on Windows casefold path collisions instead of silently dropping one entry.
- Lock verification mode while work runs and invalidate displayed results when the mode changes.
- Block normal window close while verification or copy is active.
- Refresh release metadata and gate tag releases with packaged Windows GUI proof.

## 0.1.3 - 2026-09-13

- Reframe the UI around original-vs-copy verification with plain-English results and Problems-only default.
- Add same/overlapping-root guards, path traversal protection, staged-copy verification, stale-root invalidation, and safer link handling.
- Pin Windows build dependencies and add deterministic packaged-GUI validation.

## 0.1.2 - 2026-09-13

- Add native Windows visual proof for the packaged app and exact-copy confirmation flow.
- Add startup folder arguments used by Windows end-to-end validation (`--left`, `--right`, `--verify`).
- Strengthen Windows validation to exercise portable launch, install, installed launch, copy confirmation, screenshot capture, and uninstall.

## 0.1.1 - 2026-09-13

- Fail closed on unsupported special filesystem objects so metadata can never produce a false Same.
- Refuse copy of unsupported special filesystem objects.
- Refresh first-party GitHub Actions and release publishing.

## 0.1.0 - 2026-09-13

- Initial Windows-first release.
- Four-state folder comparison with content-backed Same.
- Tree UI and explicit selected-item copy with overwrite confirmation.
- Symlink/junction-safe scanning.
- Portable ZIP + installer release automation.
