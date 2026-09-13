from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import hashlib
import os
import stat
from typing import Callable


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
    link_error: str | None = None
    device: int | None = None
    inode: int | None = None
    mode: int | None = None


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
    return bool(fn(path))


def _path_identity(path: Path) -> str:
    return os.path.normcase(os.path.realpath(os.fspath(path)))


def _is_within(child: Path, parent: Path) -> bool:
    child_id = _path_identity(child)
    parent_id = _path_identity(parent)
    try:
        return os.path.commonpath([child_id, parent_id]) == parent_id
    except ValueError:
        return False


def validate_root_pair(left_root: str | os.PathLike[str], right_root: str | os.PathLike[str]) -> tuple[Path, Path]:
    left = Path(left_root).expanduser().resolve(strict=True)
    right = Path(right_root).expanduser().resolve(strict=True)
    if not left.is_dir() or not right.is_dir():
        raise ValueError("Choose two existing folders.")
    left_id, right_id = _path_identity(left), _path_identity(right)
    if left_id == right_id:
        raise ValueError("Choose two different folders. A folder cannot be verified against itself.")
    if _is_within(left, right) or _is_within(right, left):
        raise ValueError("Choose separate folders. One selected folder cannot be inside the other because overlapping verification roots are ambiguous.")
    return left, right



def _read_link(path: Path) -> tuple[str | None, str | None]:
    try:
        return os.readlink(path), None
    except OSError as exc:
        return None, f"{type(exc).__name__}: {exc}"


def _scan_key(rel_path: str) -> str:
    return rel_path.casefold() if os.name == "nt" else rel_path


def scan_tree(root: str | os.PathLike[str]) -> dict[str, ScanItem]:
    root_path = Path(root).expanduser().resolve(strict=True)
    if not root_path.is_dir():
        raise ValueError(f"Not a folder: {root_path}")
    result: dict[str, ScanItem] = {}

    def put(item: ScanItem) -> None:
        key = _scan_key(item.rel_path)
        previous = result.get(key)
        if previous is not None and previous.rel_path != item.rel_path:
            raise OSError(
                "Case-colliding paths cannot be verified safely on Windows: "
                f"{previous.rel_path!r} and {item.rel_path!r}. Rename one before verification."
            )
        result[key] = item

    def walk(directory: Path, rel_base: Path) -> None:
        try:
            entries = list(os.scandir(directory))
        except OSError as exc:
            rel = rel_base.as_posix() or "."
            put(ScanItem(rel, directory, EntryType.OTHER, None, None, None, f"{type(exc).__name__}: {exc}"))
            return
        entries.sort(key=lambda e: (e.name.casefold(), e.name))
        for entry in entries:
            rel_path = (rel_base / entry.name).as_posix()
            path = Path(entry.path)
            try:
                # Use the same no-follow stat primitive used by verification.
                # On Windows, DirEntry.stat() can report st_dev/st_ino as 0/0
                # even when os.lstat()/os.fstat() expose the real identity.
                st = os.lstat(path)
                mtime_ns = getattr(st, "st_mtime_ns", None)
            except OSError as exc:
                put(ScanItem(rel_path, path, EntryType.OTHER, None, None, None, f"{type(exc).__name__}: {exc}"))
                continue
            identity = {"device": st.st_dev, "inode": st.st_ino, "mode": st.st_mode}
            if stat.S_ISLNK(st.st_mode) or _is_junction(path):
                target, error = _read_link(path)
                put(ScanItem(rel_path, path, EntryType.LINK, None, mtime_ns, target, error, **identity))
            elif stat.S_ISDIR(st.st_mode):
                put(ScanItem(rel_path, path, EntryType.DIRECTORY, None, mtime_ns, **identity))
                walk(path, rel_base / entry.name)
            elif stat.S_ISREG(st.st_mode):
                put(ScanItem(rel_path, path, EntryType.FILE, st.st_size, mtime_ns, **identity))
            else:
                put(ScanItem(rel_path, path, EntryType.OTHER, st.st_size, mtime_ns, **identity))
    walk(root_path, Path())
    return result

def _scan_signature(items: dict[str, ScanItem]) -> tuple[tuple[object, ...], ...]:
    """Stable content snapshot used to detect meaningful tree mutation.

    Directory mtimes are deliberately excluded. They are metadata about the
    directory container, not content identity, and Windows can report a changed
    directory timestamp while the rescanned children are unchanged. Added,
    removed, or renamed children are already caught by the key/path set; file
    and link metadata remain part of the signature.
    """
    return tuple(
        sorted(
            (
                key,
                item.rel_path,
                item.kind.value,
                item.size,
                None if item.kind is EntryType.DIRECTORY else item.mtime_ns,
                item.link_target,
                item.link_error,
                item.device,
                item.inode,
                item.mode,
            )
            for key, item in items.items()
        )
    )


def _stat_matches_scan(item: ScanItem, st: os.stat_result) -> bool:
    if item.device is None or item.inode is None or item.mode is None:
        return False
    return (
        st.st_dev == item.device
        and st.st_ino == item.inode
        and stat.S_IFMT(st.st_mode) == stat.S_IFMT(item.mode)
        and st.st_size == item.size
        and st.st_mtime_ns == item.mtime_ns
    )


def _open_scanned_file(item: ScanItem) -> int:
    before = os.lstat(item.abs_path)
    if not stat.S_ISREG(before.st_mode) or not _stat_matches_scan(item, before):
        raise OSError("file identity changed before verification")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    if nofollow:
        flags |= nofollow
    fd = os.open(item.abs_path, flags)
    opened = os.fstat(fd)
    if not stat.S_ISREG(opened.st_mode) or not _stat_matches_scan(item, opened):
        os.close(fd)
        raise OSError("file identity changed while opening for verification")
    return fd


def _sha256_stable(item: ScanItem, chunk_size: int = 1024 * 1024) -> tuple[str, bool]:
    fd = _open_scanned_file(item)
    try:
        h = hashlib.sha256()
        while True:
            chunk = os.read(fd, chunk_size)
            if not chunk:
                break
            h.update(chunk)
        end_handle = os.fstat(fd)
        after = os.lstat(item.abs_path)
        stable = _stat_matches_scan(item, end_handle) and _stat_matches_scan(item, after)
        return h.hexdigest(), stable
    finally:
        os.close(fd)


def _byte_equal_stable(left: ScanItem, right: ScanItem, chunk_size: int = 1024 * 1024) -> tuple[bool, bool]:
    left_fd = _open_scanned_file(left)
    try:
        right_fd = _open_scanned_file(right)
    except Exception:
        os.close(left_fd)
        raise
    try:
        same = True
        while True:
            a = os.read(left_fd, chunk_size)
            b = os.read(right_fd, chunk_size)
            if a != b:
                same = False
                break
            if not a:
                break
        left_end, right_end = os.fstat(left_fd), os.fstat(right_fd)
        left_after, right_after = os.lstat(left.abs_path), os.lstat(right.abs_path)
        stable = (
            _stat_matches_scan(left, left_end)
            and _stat_matches_scan(right, right_end)
            and _stat_matches_scan(left, left_after)
            and _stat_matches_scan(right, right_after)
        )
        return same, stable
    finally:
        os.close(left_fd)
        os.close(right_fd)


def _file_state(left: ScanItem, right: ScanItem, full_verify: bool) -> tuple[CompareState, str]:
    if left.size != right.size:
        return CompareState.MODIFIED, "size differs"
    metadata_same = left.mtime_ns == right.mtime_ns
    if full_verify:
        same, stable = _byte_equal_stable(left, right)
        if not stable:
            return CompareState.MODIFIED, "file identity or content changed during verification; run again"
        return (CompareState.SAME if same else CompareState.MODIFIED,
                "byte-for-byte verified" if same else "content differs")
    left_hash, left_stable = _sha256_stable(left)
    right_hash, right_stable = _sha256_stable(right)
    if not left_stable or not right_stable:
        return CompareState.MODIFIED, "file identity or content changed during comparison; run again"
    if left_hash == right_hash:
        return CompareState.SAME, "SHA-256 content match" + ("" if metadata_same else "; metadata differs")
    return CompareState.MODIFIED, "content differs"

def compare_trees(
    left_root: str | os.PathLike[str],
    right_root: str | os.PathLike[str],
    *,
    full_verify: bool = False,
    on_entry: Callable[[CompareEntry], None] | None = None,
) -> list[CompareEntry]:
    left_root_path, right_root_path = validate_root_pair(left_root, right_root)
    left_map = scan_tree(left_root_path)
    right_map = scan_tree(right_root_path)
    all_keys = sorted(set(left_map) | set(right_map), key=lambda k: ((left_map.get(k) or right_map[k]).rel_path.count('/'), k))
    results: dict[str, CompareEntry] = {}
    directories: list[str] = []
    child_keys: dict[str, list[str]] = {}
    for key in all_keys:
        item = left_map.get(key) or right_map[key]
        parent_rel = Path(item.rel_path).parent.as_posix()
        parent_key = _scan_key(parent_rel) if parent_rel not in (".", "") else ""
        child_keys.setdefault(parent_key, []).append(key)

    for key in all_keys:
        left = left_map.get(key)
        right = right_map.get(key)
        present = left or right
        assert present is not None
        rel = present.rel_path
        kind = present.kind
        if left is None:
            entry = CompareEntry(rel, CompareState.RIGHT_ONLY, kind, None, right, "missing from original")
        elif right is None:
            entry = CompareEntry(rel, CompareState.LEFT_ONLY, kind, left, None, "missing from copy")
        elif left.rel_path != right.rel_path:
            entry = CompareEntry(
                left.rel_path,
                CompareState.MODIFIED,
                left.kind,
                left,
                right,
                f"path spelling differs: {left.rel_path!r} vs {right.rel_path!r}; cannot safely verify",
            )
        elif left.kind != right.kind:
            entry = CompareEntry(rel, CompareState.MODIFIED, left.kind, left, right, f"type differs: {left.kind.value} vs {right.kind.value}")
        elif left.kind == EntryType.DIRECTORY:
            directories.append(key)
            continue
        elif left.kind == EntryType.LINK:
            if left.link_error or right.link_error or left.link_target is None or right.link_target is None:
                entry = CompareEntry(rel, CompareState.MODIFIED, EntryType.LINK, left, right, "link target unreadable; cannot verify")
            else:
                same = left.link_target == right.link_target
                detail = "link target matches" if same else "link target differs"
                entry = CompareEntry(rel, CompareState.SAME if same else CompareState.MODIFIED, EntryType.LINK, left, right, detail)
        elif left.kind == EntryType.FILE:
            try:
                state, detail = _file_state(left, right, full_verify)
            except OSError as exc:
                state, detail = CompareState.MODIFIED, f"read error: {exc}"
            entry = CompareEntry(rel, state, EntryType.FILE, left, right, detail)
        else:
            entry = CompareEntry(rel, CompareState.MODIFIED, EntryType.OTHER, left, right, "unsupported special filesystem type")
        results[key] = entry
        if on_entry:
            on_entry(entry)

    for key in sorted(directories, key=lambda k: -(left_map.get(k) or right_map[k]).rel_path.count('/')):
        left = left_map[key]
        right = right_map[key]
        states = [results[child].state for child in child_keys.get(key, []) if child in results]
        state = CompareState.SAME if all(s is CompareState.SAME for s in states) else CompareState.MODIFIED
        rel = left.rel_path
        detail = "subtree content-equivalent" if state is CompareState.SAME else "subtree differs"
        entry = CompareEntry(rel, state, EntryType.DIRECTORY, left, right, detail)
        results[key] = entry
        if on_entry:
            on_entry(entry)

    left_after = scan_tree(left_root_path)
    right_after = scan_tree(right_root_path)
    if _scan_signature(left_map) != _scan_signature(left_after) or _scan_signature(right_map) != _scan_signature(right_after):
        raise OSError("Folder contents changed during verification; results discarded. Run again when both folders are idle.")

    return [results[k] for k in all_keys]