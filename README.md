# FolderCompare

![Windows Validation](https://github.com/jddev273/foldercompare/actions/workflows/windows-validation.yml/badge.svg)

## Did the files copy? Verify their contents.

FolderCompare is a deliberately narrow, Windows-first verifier for the person who copied a folder, migrated a drive, made a backup, or restored data and wants one answer: **which ordinary files are missing or have different data?**

It is not a sync engine and it is not a code-diff cockpit. Pick the **original** and the **copy / backup**. FolderCompare verifies matching file content, gives you four plain-English counts, and hides verified matches by default so the problems are obvious.

## Usage

1. Choose the **Original folder**.
2. Choose the **Copy / backup folder**.
3. Click **Verify folders** and review the problems. FolderCompare does not modify either folder; use your normal copy/backup tool if you decide to repair a difference.

Everything in V1 is compare-only. FolderCompare never copies, overwrites, deletes, renames, or edits the selected folders.

## The four answers

- **Verified** — content matches. Size or timestamp alone can never earn this state.
- **Changed** — both sides exist, but type/content/subtree differs or could not be safely verified.
- **Missing from copy** — present in the original, absent from the copy.
- **Extra in copy** — present in the copy, absent from the original.

Default verification uses SHA-256 over same-sized candidate files. **Extra assurance: byte-for-byte verify matches** reads both files directly and compares every byte.

### Verification scope

**Verified means the ordinary file data stream matches for the paths FolderCompare checks.** FolderCompare is not a forensic NTFS clone verifier: alternate data streams, ACL/security descriptors, extended attributes, hardlink topology, sparse/compression flags, and other filesystem-specific metadata are outside V1 scope. If you need preservation of those properties, use a backup/migration tool designed to verify them.

## Safety model

FolderCompare V1 is strictly read-only. It opens ordinary files for reading, reads directory/link metadata, and reports what it observed; it has no copy, overwrite, delete, rename, staging, or repair operation.

FolderCompare deliberately rejects identical roots and parent/child root pairs because they are ambiguous verification targets. Editing either selected root invalidates displayed results in the GUI. Matching-file reads are bound to the filesystem object identity captured during scanning, and the final rescan discards results when ordinary path/type/object/size/timestamp/link changes are observed.

**Trust boundary:** keep both folders idle while verification runs. FolderCompare reads a live filesystem; it does not take an OS-level snapshot or lock the trees, so results describe the files as read during that run rather than guaranteeing the folders cannot change immediately afterward. A final structural re-scan catches ordinary additions, removals, renames, size/timestamp changes, and link changes and discards the run when they are observed, but a process that rewrites same-size data while deliberately preserving timestamps can evade that metadata re-scan. Re-run verification after all copying/restoring activity has stopped.

FolderCompare never writes to the selected trees. Existing files, missing files, folders, links, Windows junctions, and special filesystem objects all remain compare-only so verification cannot become a destructive sync operation.

There is no sync, repair, merge, copy, delete, rename command, cloud account, AI, plugin system, or background filesystem mutation.

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

The suite includes same-content/different-metadata, same-size/different-content, nested and empty folders, Unicode, zero-byte and multi-chunk files, read-only files, special objects, links, identical/overlapping-root rejection, case-only path ambiguity, concurrent tree-mutation rejection, object-identity replacement races, symlink replacement races, and explicit selected-tree preservation. Windows CI adds native junction/identity checks plus packaged executable/install/read-only GUI proof.

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
