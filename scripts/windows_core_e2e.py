from __future__ import annotations

import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from foldercompare import core
from foldercompare.core import CompareState, EntryType, compare_trees, scan_tree


def states(left: Path, right: Path) -> dict[str, CompareState]:
    return {entry.rel_path.replace("\\", "/"): entry.state for entry in compare_trees(left, right)}


def snapshot(root: Path):
    rows = []
    for path in sorted(root.rglob("*"), key=lambda p: str(p).casefold()):
        st = os.lstat(path)
        rel = path.relative_to(root).as_posix()
        if path.is_symlink():
            payload = ("link", os.readlink(path))
        elif stat.S_ISREG(st.st_mode):
            payload = ("file", path.read_bytes())
        elif stat.S_ISDIR(st.st_mode):
            payload = ("dir", None)
        else:
            payload = ("other", None)
        rows.append((rel, stat.S_IFMT(st.st_mode), st.st_size, st.st_mtime_ns, payload))
    return tuple(rows)


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="foldercompare-windows-e2e-"))
    try:
        left = tmp / "left"
        right = tmp / "right"
        left.mkdir()
        right.mkdir()

        (left / "same.txt").write_text("same\n", encoding="utf-8")
        (right / "same.txt").write_text("same\n", encoding="utf-8")
        (left / "modified.txt").write_text("left\n", encoding="utf-8")
        (right / "modified.txt").write_text("rite\n", encoding="utf-8")
        (left / "left-only.txt").write_text("left only\n", encoding="utf-8")
        (right / "right-only.txt").write_text("right only\n", encoding="utf-8")
        (left / "nested").mkdir()
        (right / "nested").mkdir()
        (left / "nested" / "same.bin").write_bytes(bytes(range(64)))
        (right / "nested" / "same.bin").write_bytes(bytes(range(64)))

        before_snapshot = (snapshot(left), snapshot(right))
        result = states(left, right)
        assert result["same.txt"] is CompareState.SAME, result
        assert result["modified.txt"] is CompareState.MODIFIED, result
        assert result["left-only.txt"] is CompareState.LEFT_ONLY, result
        assert result["right-only.txt"] is CompareState.RIGHT_ONLY, result
        assert result["nested/same.bin"] is CompareState.SAME, result
        assert (snapshot(left), snapshot(right)) == before_snapshot, "comparison mutated selected folders"

        for forbidden in (
            "copy_selected",
            "_copy_plain_object",
            "_verify_staged_copy",
            "_commit_missing_file_no_replace",
            "_remove_path",
        ):
            assert not hasattr(core, forbidden), f"mutation API still exposed: {forbidden}"

        # Same and overlapping roots remain rejected even though V1 is read-only;
        # they are ambiguous comparisons and previously formed part of the safety boundary.
        try:
            compare_trees(left, left)
            raise AssertionError("same-root verification was not blocked")
        except ValueError:
            pass
        child = left / "nested-root"
        child.mkdir()
        try:
            compare_trees(left, child)
            raise AssertionError("overlapping roots were not blocked")
        except ValueError:
            pass
        child.rmdir()

        # Real Windows junctions must be classified as links and never traversed.
        target = tmp / "junction-target"
        target.mkdir()
        (target / "inside.txt").write_text("target", encoding="utf-8")
        junction = left / "junction"
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(junction), str(target)],
            check=True,
            capture_output=True,
            text=True,
        )
        scan = scan_tree(left)
        assert scan["junction"].kind is EntryType.LINK, scan["junction"]
        assert "junction/inside.txt" not in scan
        os.rmdir(junction)

        # Exact-object identity must be populated on native Windows and remain
        # stable through a normal read-only verification pass.
        scanned = scan_tree(left)["same.txt"]
        assert scanned.device is not None
        assert scanned.inode is not None
        assert scanned.mode is not None
        assert states(left, right)["same.txt"] is CompareState.SAME

        assert (left / "left-only.txt").read_text(encoding="utf-8") == "left only\n"
        assert not (right / "left-only.txt").exists(), "read-only verifier unexpectedly copied a missing file"
        print(f"WINDOWS_CORE_E2E_OK items={len(result)} read_only=pass junction=pass identity=pass")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
