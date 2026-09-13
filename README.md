# FolderCompare

![Windows Validation](https://github.com/jddev273/foldercompare/actions/workflows/windows-validation.yml/badge.svg)

## Did everything copy? Know for sure.

FolderCompare is a deliberately narrow, Windows-first verifier for the person who copied a folder, migrated a drive, made a backup, or restored data and wants one answer: **what is actually different?**

It is not a sync engine and it is not a code-diff cockpit. Pick the **original** and the **copy / backup**. FolderCompare verifies matching file content, gives you four plain-English counts, and hides verified matches by default so the problems are obvious.


## The four answers

- **Verified** — content matches. Size or timestamp alone can never earn this state.
- **Changed** — both sides exist, but type/content/subtree differs or could not be safely verified.
- **Missing from copy** — present in the original, absent from the copy.
- **Extra in copy** — present in the copy, absent from the original.

Default verification uses SHA-256 over same-sized candidate files. **Extra assurance: byte-for-byte verify matches** reads both files directly and compares every byte.

## Safety model

Comparison itself is read-only.

FolderCompare deliberately rejects identical roots and parent/child root pairs. Copy operations are bound to the exact roots that produced the displayed results; editing either folder invalidates those results. Paths that escape a selected root are rejected.

The one V1 mutation is **Copy selected → backup**, available only for changed/missing ordinary files and folders from the original side. Before replacing anything, FolderCompare:

1. copies into a hidden sibling staging path,
2. verifies staged file bytes while copying,
3. moves an existing destination aside,
4. commits the staged replacement, and
5. rolls the original destination back if the commit fails.

Folder and file type replacement is called out explicitly in the confirmation dialog, whose destructive default is **No**. Links and Windows junctions are compared without traversal but are intentionally **not copied in V1**; preserving reparse semantics is safer than silently converting them.

There is no sync, merge, delete command, rename detection, cloud account, AI, plugin system, or background filesystem mutation.

## Download for Windows

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
- `packaging/scoop/` contains the Scoop manifest for the current release.

## Support

If FolderCompare saves you time, GitHub Sponsors support can be enabled for `jddev273` via `.github/FUNDING.yml`.

## License

MIT
