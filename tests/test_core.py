import os
import stat
import tempfile
import time
import unittest
from pathlib import Path

from foldercompare.core import CompareState, EntryType, compare_trees, copy_selected, scan_tree


def states(left: Path, right: Path, full=False):
    return {e.rel_path: e for e in compare_trees(left, right, full_verify=full)}


class CompareCoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.left = base / "left"
        self.right = base / "right"
        self.left.mkdir(); self.right.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, side: Path, rel: str, data: bytes):
        path = side / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def test_same_content_is_same(self):
        self.write(self.left, "a.txt", b"hello")
        self.write(self.right, "a.txt", b"hello")
        self.assertEqual(states(self.left, self.right)["a.txt"].state, CompareState.SAME)

    def test_same_content_different_mtime_is_still_same(self):
        a = self.write(self.left, "a.txt", b"hello")
        b = self.write(self.right, "a.txt", b"hello")
        os.utime(a, (1, 1)); os.utime(b, (2, 2))
        e = states(self.left, self.right)["a.txt"]
        self.assertEqual(e.state, CompareState.SAME)
        self.assertIn("metadata differs", e.detail)

    def test_same_size_different_content_is_modified(self):
        self.write(self.left, "a.bin", b"AAAA")
        self.write(self.right, "a.bin", b"BBBB")
        self.assertEqual(states(self.left, self.right)["a.bin"].state, CompareState.MODIFIED)

    def test_size_short_circuit(self):
        self.write(self.left, "a.bin", b"A")
        self.write(self.right, "a.bin", b"BBBB")
        e = states(self.left, self.right)["a.bin"]
        self.assertEqual(e.state, CompareState.MODIFIED)
        self.assertEqual(e.detail, "size differs")

    def test_left_and_right_only(self):
        self.write(self.left, "left.txt", b"L")
        self.write(self.right, "right.txt", b"R")
        s = states(self.left, self.right)
        self.assertEqual(s["left.txt"].state, CompareState.LEFT_ONLY)
        self.assertEqual(s["right.txt"].state, CompareState.RIGHT_ONLY)

    def test_type_mismatch(self):
        self.write(self.left, "thing", b"file")
        (self.right / "thing").mkdir()
        self.assertEqual(states(self.left, self.right)["thing"].state, CompareState.MODIFIED)

    def test_nested_folder_reflects_child_difference(self):
        self.write(self.left, "nested/a.txt", b"A")
        self.write(self.right, "nested/a.txt", b"B")
        s = states(self.left, self.right)
        self.assertEqual(s["nested/a.txt"].state, CompareState.MODIFIED)
        self.assertEqual(s["nested"].state, CompareState.MODIFIED)

    def test_empty_folder_same(self):
        (self.left / "empty").mkdir(); (self.right / "empty").mkdir()
        self.assertEqual(states(self.left, self.right)["empty"].state, CompareState.SAME)

    def test_unicode_and_zero_byte(self):
        self.write(self.left, "日本語/é.txt", b"")
        self.write(self.right, "日本語/é.txt", b"")
        s = states(self.left, self.right)
        self.assertEqual(s["日本語/é.txt"].state, CompareState.SAME)

    def test_full_byte_verification(self):
        self.write(self.left, "a", b"x" * 1024)
        self.write(self.right, "a", b"x" * 1024)
        e = states(self.left, self.right, full=True)["a"]
        self.assertEqual(e.state, CompareState.SAME)
        self.assertEqual(e.detail, "byte-for-byte verified")

    def test_copy_requires_overwrite_and_then_replaces(self):
        self.write(self.left, "a.txt", b"new")
        self.write(self.right, "a.txt", b"old")
        with self.assertRaises(FileExistsError):
            copy_selected(self.left, self.right, "a.txt", overwrite=False)
        copy_selected(self.left, self.right, "a.txt", overwrite=True)
        self.assertEqual((self.right / "a.txt").read_bytes(), b"new")

    def test_copy_folder_replaces_existing_tree(self):
        self.write(self.left, "d/new.txt", b"new")
        self.write(self.right, "d/old.txt", b"old")
        copy_selected(self.left, self.right, "d", overwrite=True)
        self.assertTrue((self.right / "d/new.txt").exists())
        self.assertFalse((self.right / "d/old.txt").exists())

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink unavailable")
    def test_symlink_is_compared_as_link_not_followed(self):
        self.write(self.left, "target.txt", b"left")
        self.write(self.right, "target.txt", b"right")
        try:
            os.symlink("target.txt", self.left / "link.txt")
            os.symlink("target.txt", self.right / "link.txt")
        except OSError as exc:
            self.skipTest(f"symlink creation unavailable: {exc}")
        scan = scan_tree(self.left)
        self.assertEqual(scan["link.txt"].kind, EntryType.LINK)
        s = states(self.left, self.right)
        self.assertEqual(s["link.txt"].state, CompareState.SAME)
        self.assertEqual(s["target.txt"].state, CompareState.MODIFIED)

    def test_readonly_file_compares(self):
        a = self.write(self.left, "ro.txt", b"same")
        b = self.write(self.right, "ro.txt", b"same")
        a.chmod(stat.S_IREAD); b.chmod(stat.S_IREAD)
        self.assertEqual(states(self.left, self.right)["ro.txt"].state, CompareState.SAME)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO unavailable")
    def test_special_type_fails_closed_not_same(self):
        os.mkfifo(self.left / "pipe")
        os.mkfifo(self.right / "pipe")
        e = states(self.left, self.right)["pipe"]
        self.assertEqual(e.kind, EntryType.OTHER)
        self.assertEqual(e.state, CompareState.MODIFIED)
        self.assertIn("unsupported", e.detail)
        with self.assertRaises(ValueError):
            copy_selected(self.left, self.right, "pipe", overwrite=True)

    def test_large_multichunk_file(self):
        data = (b"0123456789abcdef" * 200000)
        self.write(self.left, "large.bin", data)
        self.write(self.right, "large.bin", data)
        self.assertEqual(states(self.left, self.right)["large.bin"].state, CompareState.SAME)


if __name__ == "__main__":
    unittest.main()
