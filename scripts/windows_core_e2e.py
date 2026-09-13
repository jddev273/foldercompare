from __future__ import annotations

from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from foldercompare.core import CompareState, compare_trees, copy_selected


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

        copy_selected(left, right, "modified.txt", overwrite=True)
        copy_selected(left, right, "left-only.txt", overwrite=False)
        copy_selected(right, left, "right-only.txt", overwrite=False)

        after = states(left, right)
        bad = {path: state.value for path, state in after.items() if state is not CompareState.SAME}
        assert not bad, bad
        print(f"WINDOWS_CORE_E2E_OK items={len(after)}")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
