# Changelog

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
