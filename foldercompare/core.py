from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import hashlib
import os
import shutil
import uuid
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
        raise ValueError("Choose two different folders. FolderCompare blocks same-folder operations to protect your files.")
    if _is_within(left, right) or _is_within(right, left):
        raise ValueError("Choose separate folders. One selected folder cannot be inside the other because copy operations would be unsafe.")
    return left, right


def _safe_rel_path(rel_path: str) -> Path:
    rel = Path(rel_path)
    if not rel_path or rel.is_absolute() or rel.drive or any(part in ("..", "") for part in rel.parts):
        raise ValueError("Unsafe relative path.")
    if rel == Path(".") or any(part == "." for part in rel.parts):
        raise ValueError("Unsafe relative path.")
    return rel


def _ensure_plain_parents(root: Path, rel: Path) -> None:
    current = root
    for part in rel.parts[:-1]:
        current = current / part
        if current.is_symlink() or _is_junction(current):
            raise ValueError("Copy path passes through a link or junction; operation blocked for safety.")


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
                st = entry.stat(follow_symlinks=False)
                mtime_ns = getattr(st, "st_mtime_ns", None)
            except OSError:
                st = None
                mtime_ns = None
            if entry.is_symlink() or _is_junction(path):
                target, error = _read_link(path)
                put(ScanItem(rel_path, path, EntryType.LINK, None, mtime_ns, target, error))
                continue
            try:
                if entry.is_dir(follow_symlinks=False):
                    put(ScanItem(rel_path, path, EntryType.DIRECTORY, None, mtime_ns))
                    walk(path, rel_base / entry.name)
                elif entry.is_file(follow_symlinks=False):
                    put(ScanItem(rel_path, path, EntryType.FILE, st.st_size if st else None, mtime_ns))
                else:
                    put(ScanItem(rel_path, path, EntryType.OTHER, st.st_size if st else None, mtime_ns))
            except OSError as exc:
                put(ScanItem(rel_path, path, EntryType.OTHER, None, mtime_ns, None, f"{type(exc).__name__}: {exc}"))
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
            )
            for key, item in items.items()
        )
    )


def _sha256_stable(path: Path, chunk_size: int = 1024 * 1024) -> tuple[str, bool]:
    before = path.stat()
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    after = path.stat()
    stable = (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
    return h.hexdigest(), stable


def _byte_equal_stable(left: Path, right: Path, chunk_size: int = 1024 * 1024) -> tuple[bool, bool]:
    lb, rb = left.stat(), right.stat()
    same = True
    with left.open("rb") as lf, right.open("rb") as rf:
        while True:
            a = lf.read(chunk_size)
            b = rf.read(chunk_size)
            if a != b:
                same = False
                break
            if not a:
                break
    la, ra = left.stat(), right.stat()
    stable = ((lb.st_size, lb.st_mtime_ns) == (la.st_size, la.st_mtime_ns)
              and (rb.st_size, rb.st_mtime_ns) == (ra.st_size, ra.st_mtime_ns))
    return same, stable


def _file_state(left: ScanItem, right: ScanItem, full_verify: bool) -> tuple[CompareState, str]:
    if left.size != right.size:
        return CompareState.MODIFIED, "size differs"
    metadata_same = left.mtime_ns == right.mtime_ns
    if full_verify:
        same, stable = _byte_equal_stable(left.abs_path, right.abs_path)
        if not stable:
            return CompareState.MODIFIED, "file changed during verification; run again"
        return (CompareState.SAME if same else CompareState.MODIFIED,
                "byte-for-byte verified" if same else "content differs")
    left_hash, left_stable = _sha256_stable(left.abs_path)
    right_hash, right_stable = _sha256_stable(right.abs_path)
    if not left_stable or not right_stable:
        return CompareState.MODIFIED, "file changed during comparison; run again"
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


def path_present(path: Path) -> bool:
    return path.exists() or path.is_symlink() or _is_junction(path)


def _path_signature(path: Path):
    if not path_present(path):
        return None
    st = os.lstat(path)
    return (st.st_dev, st.st_ino, st.st_mode, st.st_size, st.st_mtime_ns, path.is_symlink(), _is_junction(path))


def _verify_staged_copy(source: Path, staging: Path) -> None:
    if source.is_file():
        same, stable = _byte_equal_stable(source, staging)
        if not same or not stable:
            raise OSError("Source changed or staged file failed final verification; destination was not changed.")
        return
    if source.is_dir():
        results = compare_trees(source, staging, full_verify=True)
        if any(entry.state is not CompareState.SAME for entry in results):
            raise OSError("Source changed or staged folder failed final verification; destination was not changed.")
        return
    raise ValueError(f"Unsupported special filesystem type: {source}")


def _remove_path(path: Path) -> None:
    if _is_junction(path):
        os.rmdir(path)
    elif path.is_symlink():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def _copy_plain_object(source: Path, staging: Path) -> None:
    if source.is_symlink() or _is_junction(source):
        raise ValueError("Copying links and Windows junctions is disabled in V1 for safety. FolderCompare still compares them without following them.")
    if source.is_file():
        shutil.copy2(source, staging, follow_symlinks=False)
        same, stable = _byte_equal_stable(source, staging)
        if not same or not stable:
            raise OSError("Staged file did not verify against the source; destination was not changed.")
        return
    if source.is_dir():
        staging.mkdir()
        for entry in os.scandir(source):
            child_source = Path(entry.path)
            child_dest = staging / entry.name
            if entry.is_symlink() or _is_junction(child_source):
                raise ValueError("Folder contains a link or junction. Copy blocked so FolderCompare cannot accidentally follow or change link semantics.")
            if entry.is_dir(follow_symlinks=False):
                _copy_plain_object(child_source, child_dest)
            elif entry.is_file(follow_symlinks=False):
                shutil.copy2(child_source, child_dest, follow_symlinks=False)
                same, stable = _byte_equal_stable(child_source, child_dest)
                if not same or not stable:
                    raise OSError(f"Staged file did not verify: {child_source}")
            else:
                raise ValueError(f"Unsupported special filesystem type: {child_source}")
        return
    raise ValueError(f"Unsupported special filesystem type: {source}")


def _commit_missing_file_no_replace(staging: Path, destination: Path) -> None:
    """Publish a staged regular file only if destination is still absent."""
    if os.name == "nt":
        # Windows rename fails when the destination already exists.
        os.rename(staging, destination)
        return
    # POSIX hard-link creation is atomic and fails with EEXIST. Staging is a
    # sibling regular file, so source and destination are on the same filesystem.
    os.link(staging, destination, follow_symlinks=False)
    staging.unlink()


def copy_selected(source_root: str | os.PathLike[str], destination_root: str | os.PathLike[str], rel_path: str, *, overwrite: bool) -> tuple[Path, Path]:
    """Repair one missing regular file from original to copy without overwriting."""
    source_root_path, destination_root_path = validate_root_pair(source_root, destination_root)
    rel = _safe_rel_path(rel_path)
    _ensure_plain_parents(source_root_path, rel)
    _ensure_plain_parents(destination_root_path, rel)
    source = source_root_path / rel
    destination = destination_root_path / rel
    if not source.exists() and not source.is_symlink() and not _is_junction(source):
        raise FileNotFoundError(source)
    if _path_identity(source) == _path_identity(destination):
        raise ValueError("Source and destination resolve to the same path; copy blocked.")
    if source.is_symlink() or _is_junction(source) or not source.is_file():
        raise ValueError("Safe repair copies only missing regular files. Folders, links, junctions, and special objects are compare-only.")
    if _path_signature(destination) is not None:
        raise FileExistsError("Destination already exists. FolderCompare will not overwrite existing data; review changed items manually.")
    destination.parent.mkdir(parents=True, exist_ok=True)

    token = uuid.uuid4().hex
    staging = destination.parent / f".{destination.name}.foldercompare-stage-{token}"
    try:
        _copy_plain_object(source, staging)
        _verify_staged_copy(source, staging)
        _ensure_plain_parents(destination_root_path, rel)
        _commit_missing_file_no_replace(staging, destination)
        return source, destination
    except Exception:
        if staging.exists() or staging.is_symlink() or _is_junction(staging):
            try:
                _remove_path(staging)
            except OSError:
                pass
        raise
