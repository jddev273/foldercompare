# FolderCompare

![Windows Validation](https://github.com/jddev273/foldercompare/actions/workflows/windows-validation.yml/badge.svg)

## Did the files copy? Verify their contents.

FolderCompare is a deliberately narrow, Windows-first verifier for the person who copied a folder, migrated a drive, made a backup, or restored data and wants one answer: **which ordinary files are missing or have different data?**

It is not a sync engine and it is not a code-diff cockpit. Pick the **original** and the **copy / backup**. FolderCompare verifies matching file content, gives you four plain-English counts, and hides verified matches by default so the problems are obvious.

## Usage

1. Choose the **Original folder**.
2. Choose the **Copy / backup folder**.
3. Click **Verify folders**. Review the problems; if a regular file is missing from the copy, FolderCompare can add that one file without overwriting anything already there.

Changed files, folders, links, junctions, and special filesystem objects are compare-only in this safety-first release.

## The four answers

- **Verified** — content matches. Size or timestamp alone can never earn this state.
- **Changed** — both sides exist, but type/content/subtree differs or could not be safely verified.
- **Missing from copy** — present in the original, absent from the copy.
- **Extra in copy** — present in the copy, absent from the original.

Default verification uses SHA-256 over same-sized candidate files. **Extra assurance: byte-for-byte verify matches** reads both files directly and compares every byte.

### Verification scope

**Verified means the ordinary file data stream matches for the paths FolderCompare checks.** FolderCompare is not a forensic NTFS clone verifier: alternate data streams, ACL/security descriptors, extended attributes, hardlink topology, sparse/compression flags, and other filesystem-specific metadata are outside V1 scope. If you need preservation of those properties, use a backup/migration tool designed to verify them.

## Safety model

Comparison itself is read-only.

FolderCompare deliberately rejects identical roots and parent/child root pairs. Copy operations are bound to the exact roots that produced the displayed results; editing either folder invalidates those results. Paths that escape a selected root are rejected.

The one V1 mutation is **Copy missing file → backup**. It is intentionally add-only: only a regular file that is absent from the copy is eligible. FolderCompare stages and byte-verifies that file, then publishes it with an atomic **no-replace** operation. If anything creates the destination first, the repair aborts instead of overwriting it.

Existing files, whole folders, links, Windows junctions, and special filesystem objects are never overwritten by FolderCompare. They remain compare-only so verification cannot become a destructive sync operation.

There is no sync, merge, delete command, rename detection, cloud account, AI, plugin system, or background filesystem mutation.

## Installation

Use the latest release: **[GitHub Releases](https://github.com/jddev273/foldercompare/releases/latest)**.

The release workflow builds a portable x64 ZIP and per-user Inno Setup installer on a clean Windows runner, exercises the packaged Windows core and GUI, and publishes SHA-256 checksums.

> The current community build is not Authenticode-signed. Windows SmartScreen may show an Unknown Publisher / reputation warning until signing is added.

## Run from source

Python **3.12+** with Tk available:

```bash
python -m foldercompare
```

No runtime packages are required.

## Tests

```bash
python -m unittest discover -s tests -v
python fixtures/build_fixture.py ./fixture-corpus
```

The suite includes same-content/different-metadata, same-size/different-content, nested and empty folders, Unicode, zero-byte and multi-chunk files, read-only files, special objects, links, identical/overlapping-root rejection, path traversal rejection, failed-staging preservation, and failed-commit rollback. Windows CI adds packaged executable/install checks.

## Why this instead of WinMerge?

If you want source merging, three-way diffs, plugins, archive comparison, editors, filters, or scripting, use a full diff tool. FolderCompare is for the narrower job: **verify that a copy is intact with as little interpretation and destructive surface area as possible.**

## Packaging

- `.github/workflows/release.yml` builds the portable ZIP and installer.
- `packaging/winget/` records WinGet submission notes.
- `packaging/scoop/` is updated on `main` after release hashes are available.

## Support

If FolderCompare saves you time, GitHub Sponsors support can be enabled for `jddev273` via `.github/FUNDING.yml`.

## License

MIT
