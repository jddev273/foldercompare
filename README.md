# FolderCompare

**Open two folders. See what differs.**

FolderCompare is a deliberately narrow, Windows-first open-source folder comparison utility. It shows four states — **Same**, **Modified**, **Left only**, and **Right only** — and lets you explicitly copy a selected item in either direction.

## What V1 does

- Progressive comparison: path → type → size → metadata → content/hash as needed.
- A file is **never** marked Same from timestamps or size alone. Default comparison reads same-sized candidate content with SHA-256; optional **Verify contents fully** performs a byte-for-byte check.
- Tree UI with four live summary counts.
- Explicit one-way copy of a selected file, folder, or link. The confirmation dialog shows the exact source, exact destination, and whether overwrite is **YES** or **NO**.
- Symlinks and Windows junctions are treated as links and are not traversed by the scanner.
- No sync, merge, rename detection, accounts, cloud, AI, plugins, or background filesystem mutation.

## Windows downloads

GitHub Releases builds two artifacts from each `v*` tag on a clean Windows runner:

1. `FolderCompare-<version>-windows-x64-portable.zip` — single-file portable executable.
2. `FolderCompare-<version>-windows-x64-setup.exe` — Inno Setup installer.

The release workflow also publishes SHA-256 checksums.

## Run from source

Python 3.10+ with Tk available:

```bash
python -m foldercompare
```

No runtime packages are required.

## Tests and fixture corpus

```bash
python -m unittest discover -s tests -v
python fixtures/build_fixture.py ./fixture-corpus
```

The corpus covers same-content/different-metadata, same-size/different-content, size differences, left/right-only items, nested differences, empty folders, zero-byte files, Unicode names, multi-chunk files, read-only files, type mismatches, and symlinks when the OS permits them.

## Trust model

Comparison never follows links during scanning. For regular files, path/type/size can prove a difference cheaply, but they cannot prove equality. Equality therefore reaches a content stage. SHA-256 is the default practical content identity check; enable **Verify contents fully** for byte-for-byte equality.

Copy is intentionally not sync. It acts only on the selected path after a confirmation dialog. When overwriting a folder, the destination folder at that exact path is replaced rather than merged.

## Packaging / future distribution

- `.github/workflows/release.yml` builds the portable ZIP and installer.
- `packaging/winget/` records the published installer URL/SHA-256 and the safe `wingetcreate` path for later submission.
- `packaging/scoop/` contains a versioned manifest with the published portable ZIP SHA-256.


## License

MIT
