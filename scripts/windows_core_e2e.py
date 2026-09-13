from __future__ import annotations

from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from foldercompare.core import CompareState, EntryType, compare_trees, copy_selected, scan_tree


def states(left: Path, right: Path) -> dict[str, CompareState]:
    return {entry.rel_path.replace('\\', '/'): entry.state for entry in compare_trees(left, right)}


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

        before = states(left, right)
        assert before["same.txt"] is CompareState.SAME, before
        assert before["modified.txt"] is CompareState.MODIFIED, before
        assert before["left-only.txt"] is CompareState.LEFT_ONLY, before
        assert before["right-only.txt"] is CompareState.RIGHT_ONLY, before
        assert before["nested/same.bin"] is CompareState.SAME, before

        # Safety-first repair is add-only and one-way: a missing original-side file
        # may be added to the copy, but changed/existing files are never replaced.
        try:
            copy_selected(left, right, "modified.txt", overwrite=True)
            raise AssertionError("existing destination overwrite was not blocked")
        except FileExistsError:
            pass
        assert (right / "modified.txt").read_text(encoding="utf-8") == "rite\n"
        copy_selected(left, right, "left-only.txt", overwrite=False)

        # A concurrently appearing destination must win; no-replace publication
        # must never overwrite data another process created.
        (left / "race.txt").write_text("source", encoding="utf-8")
        (right / "race.txt").write_text("external", encoding="utf-8")
        try:
            copy_selected(left, right, "race.txt", overwrite=False)
            raise AssertionError("existing race destination was not blocked")
        except FileExistsError:
            pass
        assert (right / "race.txt").read_text(encoding="utf-8") == "external"

        # Safety regressions: same roots and overlapping roots must fail before mutation.
        protected = left / "protected.txt"
        protected.write_text("keep me", encoding="utf-8")
        try:
            copy_selected(left, left, "protected.txt", overwrite=True)
            raise AssertionError("same-root copy was not blocked")
        except ValueError:
            pass
        assert protected.read_text(encoding="utf-8") == "keep me"
        child = left / "nested-root"
        child.mkdir()
        try:
            compare_trees(left, child)
            raise AssertionError("overlapping roots were not blocked")
        except ValueError:
            pass

        # Windows junctions must be classified as links and never traversed.
        import os, subprocess
        target = tmp / "junction-target"
        target.mkdir()
        (target / "inside.txt").write_text("target", encoding="utf-8")
        junction = left / "junction"
        subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), str(target)], check=True, capture_output=True, text=True)
        scan = scan_tree(left)
        assert scan["junction"].kind is EntryType.LINK, scan["junction"]
        assert "junction/inside.txt" not in scan
        os.rmdir(junction)
        protected.unlink()
        child.rmdir()

        after = states(left, right)
        assert after["left-only.txt"] is CompareState.SAME, after
        assert after["modified.txt"] is CompareState.MODIFIED, after
        assert after["right-only.txt"] is CompareState.RIGHT_ONLY, after
        assert after["race.txt"] is CompareState.MODIFIED, after
        print(f"WINDOWS_CORE_E2E_OK items={len(after)} add_only_repair=pass existing_destination_preserved=pass")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
