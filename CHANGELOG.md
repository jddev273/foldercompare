# Changelog

## 0.1.6 - 2026-09-13

- Make V1 strictly read-only: remove the add-only repair API, GUI action, and packaged repair proof so FolderCompare only verifies and reports differences.
- Fix matching files being falsely reported as Changed on Windows by capturing scan identity with `os.lstat()`, consistent with the later `lstat`/`fstat` verification checks.
- Add a regression proving scan identity does not depend on `DirEntry.stat()`, whose Windows device/inode fields may be zero.
- Install lowest-privilege Windows builds under the per-user LocalAppData Programs directory instead of Program Files.
- Make third-party-notice generation compatible with Windows PowerShell 5.1 while retaining UTF-8 without BOM.
- Clarify read-only root-validation messages and label synthetic parent rows in filtered result views.

## 0.1.5 - 2026-09-13

- **Superseded by 0.1.6:** the published Windows build could falsely classify matching regular files as Changed because scan-time `DirEntry.stat()` identity did not match later `lstat`/`fstat` identity.
- Fail closed when normalized cross-root paths differ in exact spelling, preventing case-sensitive Windows paths from being falsely verified.
- Re-scan both trees before returning results and discard verification if paths, types, sizes, timestamps, or link state changed during the run.
- Add deterministic regressions for case-only cross-root names and files added during verification.
- Extend packaged Windows GUI proof to execute and verify the add-only missing-file repair, not just open its confirmation dialog.
- Include the project MIT license plus exact-build Python/Tcl/Tk/PyInstaller notices in both Windows distributables, with packaging assertions.
- Make the deterministic manual QA fixture builder safely rerunnable by recreating only its `left`/`right` corpus trees.

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
