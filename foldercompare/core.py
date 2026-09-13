from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import hashlib
import os
import shutil
from typing import Callable, Iterable


class CompareState(str, Enum):
    SAME = "Same"
    MODIFIED = "Modified"
    LEFT_ONLY = "Left only"
    RIGHT_ONLY = "Right only"


class EntryType(str, Enum):
    FILE = "File"
    DIRECTORY = "Folder"
    LINK = "Link"
    OTHER = "Other"


@dataclass(frozen=True)
class ScanItem:
    rel_path: str
    abs_path: Path
    kind: EntryType
    size: int | None
    mtime_ns: int | None
    link_target: str | None = None


@dataclass(frozen=True)
class CompareEntry:
    rel_path: str
    state: CompareState
    kind: EntryType
    left: ScanItem | None
    right: ScanItem | None
    detail: str = ""


def _is_junction(path: Path) -> bool:
    fn = getattr(os.path, "isjunction", None)
    if fn is None:
        return False
    try:
        return bool(fn(path))
    except OSError:
        return False


def _link_target(path: Path) -> str:
    try:
        return os.readlink(path)
    except OSError:
        return "<unreadable link>"


def scan_tree(root: str | os.PathLike[str]) -> dict[str, ScanItem]:
    root_path = Path(root).resolve()
    if not root_path.is_dir():
        raise ValueError(f"Not a folder: {root_path}")
    result: dict[str, ScanItem] = {}

    def walk(directory: Path, rel_base: Path) -> None:
        try:
            entries = list(os.scandir(directory))
        except OSError as exc:
            rel = rel_base.as_posix() or "."
            result[rel] = ScanItem(rel, directory, EntryType.OTHER, None, None, None)
            return
        entries.sort(key=lambda e: e.name.casefold())
        for entry in entries:
            rel_path = (rel_base / entry.name).as_posix()
            path = Path(entry.path)
            try:
                st = entry.stat(follow_symlinks=False)
                mtime_ns = getattr(st, "st_mtime_ns", None)
            except OSError:
                st = None
                mtime_ns = None

            is_link = entry.is_symlink() or _is_junction(path)
            if is_link:
                result[rel_path] = ScanItem(rel_path, path, EntryType.LINK, None, mtime_ns, _link_target(path))
                continue
            try:
                if entry.is_dir(follow_symlinks=False):
                    result[rel_path] = ScanItem(rel_path, path, EntryType.DIRECTORY, None, mtime_ns)
                    walk(path, rel_base / entry.name)
                elif entry.is_file(follow_symlinks=False):
                    result[rel_path] = ScanItem(rel_path, path, EntryType.FILE, st.st_size if st else None, mtime_ns)
                else:
                    result[rel_path] = ScanItem(rel_path, path, EntryType.OTHER, st.st_size if st else None, mtime_ns)
            except OSError:
                result[rel_path] = ScanItem(rel_path, path, EntryType.OTHER, None, mtime_ns)
    walk(root_path, Path())
    return result


def _sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _byte_equal(left: Path, right: Path, chunk_size: int = 1024 * 1024) -> bool:
    with left.open("rb") as lf, right.open("rb") as rf:
        while True:
            a = lf.read(chunk_size)
            b = rf.read(chunk_size)
            if a != b:
                return False
            if not a:
                return True


def _file_state(left: ScanItem, right: ScanItem, full_verify: bool) -> tuple[CompareState, str]:
    if left.size != right.size:
        return CompareState.MODIFIED, "size differs"
    metadata_same = left.mtime_ns == right.mtime_ns
    if full_verify:
        same = _byte_equal(left.abs_path, right.abs_path)
        return (CompareState.SAME if same else CompareState.MODIFIED,
                "byte-for-byte verified" if same else "content differs")
    # Metadata is a cheap hint only. A file is never called Same from metadata alone.
    same = _sha256(left.abs_path) == _sha256(right.abs_path)
    if same:
        return CompareState.SAME, "SHA-256 content match" + ("" if metadata_same else "; metadata differs")
    return CompareState.MODIFIED, "content differs"


def compare_trees(
    left_root: str | os.PathLike[str],
    right_root: str | os.PathLike[str],
    *,
    full_verify: bool = False,
    on_entry: Callable[[CompareEntry], None] | None = None,
) -> list[CompareEntry]:
    left_map = scan_tree(left_root)
    right_map = scan_tree(right_root)
    all_paths = sorted(set(left_map) | set(right_map), key=lambda p: (p.count('/'), p.casefold()))
    results: dict[str, CompareEntry] = {}
    directories: list[str] = []

    for rel in all_paths:
        left = left_map.get(rel)
        right = right_map.get(rel)
        present = left or right
        assert present is not None
        kind = present.kind
        if left is None:
            entry = CompareEntry(rel, CompareState.RIGHT_ONLY, kind, None, right, "missing on left")
        elif right is None:
            entry = CompareEntry(rel, CompareState.LEFT_ONLY, kind, left, None, "missing on right")
        elif left.kind != right.kind:
            entry = CompareEntry(rel, CompareState.MODIFIED, left.kind, left, right, f"type differs: {left.kind.value} vs {right.kind.value}")
        elif left.kind == EntryType.DIRECTORY:
            directories.append(rel)
            continue
        elif left.kind == EntryType.LINK:
            same = left.link_target == right.link_target
            entry = CompareEntry(rel, CompareState.SAME if same else CompareState.MODIFIED, EntryType.LINK, left, right,
                                 "link target matches" if same else "link target differs")
        elif left.kind == EntryType.FILE:
            try:
                state, detail = _file_state(left, right, full_verify)
            except OSError as exc:
                state, detail = CompareState.MODIFIED, f"read error: {exc}"
            entry = CompareEntry(rel, state, EntryType.FILE, left, right, detail)
        else:
            same = (left.size, left.mtime_ns) == (right.size, right.mtime_ns)
            entry = CompareEntry(rel, CompareState.SAME if same else CompareState.MODIFIED, EntryType.OTHER, left, right,
                                 "metadata match" if same else "metadata differs")
        results[rel] = entry
        if on_entry:
            on_entry(entry)

    # Finalize folders after children, so folder status reflects the subtree rather than metadata.
    for rel in sorted(directories, key=lambda p: (-p.count('/'), p.casefold())):
        left = left_map[rel]
        right = right_map[rel]
        prefix = rel + "/"
        descendants = [e for p, e in results.items() if p.startswith(prefix)]
        state = CompareState.SAME if all(e.state == CompareState.SAME for e in descendants) else CompareState.MODIFIED
        entry = CompareEntry(rel, state, EntryType.DIRECTORY, left, right,
                             "subtree content-equivalent" if state == CompareState.SAME else "subtree differs")
        results[rel] = entry
        if on_entry:
            on_entry(entry)

    return [results[p] for p in sorted(results, key=lambda p: (p.count('/'), p.casefold()))]


def copy_selected(source_root: str | os.PathLike[str], destination_root: str | os.PathLike[str], rel_path: str, *, overwrite: bool) -> tuple[Path, Path]:
    source = Path(source_root) / Path(rel_path)
    destination = Path(destination_root) / Path(rel_path)
    if not source.exists() and not source.is_symlink() and not _is_junction(source):
        raise FileNotFoundError(source)
    exists = destination.exists() or destination.is_symlink() or _is_junction(destination)
    if exists and not overwrite:
        raise FileExistsError(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if exists:
        if destination.is_symlink() or _is_junction(destination):
            destination.unlink()
        elif destination.is_dir():
            shutil.rmtree(destination)
        else:
            destination.unlink()

    if source.is_symlink() or _is_junction(source):
        target = os.readlink(source)
        os.symlink(target, destination, target_is_directory=source.is_dir())
    elif source.is_dir():
        shutil.copytree(source, destination, symlinks=True)
    else:
        shutil.copy2(source, destination, follow_symlinks=False)
    return source, destination
