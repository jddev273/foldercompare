import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from foldercompare import core
from foldercompare.core import CompareState, EntryType, compare_trees, scan_tree, validate_root_pair


def states(left: Path, right: Path, full=False):
    return {e.rel_path: e for e in compare_trees(left, right, full_verify=full)}


def tree_snapshot(root: Path):
    """Content/object snapshot that deliberately ignores access time."""
    rows = []
    for path in sorted(root.rglob("*"), key=lambda p: p.as_posix()):
        rel = path.relative_to(root).as_posix()
        st = os.lstat(path)
        kind = stat.S_IFMT(st.st_mode)
        if path.is_symlink():
            payload = ("link", os.readlink(path))
        elif stat.S_ISREG(st.st_mode):
            payload = ("file", path.read_bytes())
        elif stat.S_ISDIR(st.st_mode):
            payload = ("dir", None)
        else:
            payload = ("other", None)
        rows.append((rel, kind, st.st_size, st.st_mtime_ns, payload))
    return tuple(rows)


class CompareCoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.left = base / "left"
        self.right = base / "right"
        self.left.mkdir()
        self.right.mkdir()

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
        os.utime(a, (1, 1))
        os.utime(b, (2, 2))
        entry = states(self.left, self.right)["a.txt"]
        self.assertEqual(entry.state, CompareState.SAME)
        self.assertIn("metadata differs", entry.detail)

    def test_same_size_different_content_is_modified(self):
        self.write(self.left, "a.bin", b"AAAA")
        self.write(self.right, "a.bin", b"BBBB")
        self.assertEqual(states(self.left, self.right)["a.bin"].state, CompareState.MODIFIED)

    def test_size_short_circuit(self):
        self.write(self.left, "a.bin", b"A")
        self.write(self.right, "a.bin", b"BBBB")
        self.assertEqual(states(self.left, self.right)["a.bin"].detail, "size differs")

    def test_left_and_right_only(self):
        self.write(self.left, "left.txt", b"L")
        self.write(self.right, "right.txt", b"R")
        result = states(self.left, self.right)
        self.assertEqual(result["left.txt"].state, CompareState.LEFT_ONLY)
        self.assertEqual(result["right.txt"].state, CompareState.RIGHT_ONLY)

    def test_type_mismatch(self):
        self.write(self.left, "thing", b"file")
        (self.right / "thing").mkdir()
        self.assertEqual(states(self.left, self.right)["thing"].state, CompareState.MODIFIED)

    def test_nested_folder_reflects_child_difference(self):
        self.write(self.left, "nested/a.txt", b"A")
        self.write(self.right, "nested/a.txt", b"B")
        result = states(self.left, self.right)
        self.assertEqual(result["nested/a.txt"].state, CompareState.MODIFIED)
        self.assertEqual(result["nested"].state, CompareState.MODIFIED)

    def test_empty_folder_same(self):
        (self.left / "empty").mkdir()
        (self.right / "empty").mkdir()
        self.assertEqual(states(self.left, self.right)["empty"].state, CompareState.SAME)

    def test_unicode_and_zero_byte(self):
        self.write(self.left, "日本語/é.txt", b"")
        self.write(self.right, "日本語/é.txt", b"")
        self.assertEqual(states(self.left, self.right)["日本語/é.txt"].state, CompareState.SAME)

    def test_full_byte_verification(self):
        self.write(self.left, "a", b"x" * 1024)
        self.write(self.right, "a", b"x" * 1024)
        self.assertEqual(states(self.left, self.right, full=True)["a"].detail, "byte-for-byte verified")

    def test_public_core_has_no_mutation_api(self):
        for name in (
            "copy_selected",
            "_copy_plain_object",
            "_verify_staged_copy",
            "_commit_missing_file_no_replace",
            "_remove_path",
        ):
            self.assertFalse(hasattr(core, name), name)

    def test_successful_verification_preserves_both_trees(self):
        self.write(self.left, "same.txt", b"same")
        self.write(self.right, "same.txt", b"same")
        self.write(self.left, "missing.txt", b"only-original")
        before = (tree_snapshot(self.left), tree_snapshot(self.right))
        compare_trees(self.left, self.right, full_verify=True)
        after = (tree_snapshot(self.left), tree_snapshot(self.right))
        self.assertEqual(after, before)

    def test_same_root_is_rejected_without_mutation(self):
        victim = self.write(self.left, "victim.txt", b"important")
        before = tree_snapshot(self.left)
        with self.assertRaises(ValueError):
            compare_trees(self.left, self.left)
        self.assertEqual(tree_snapshot(self.left), before)
        self.assertEqual(victim.read_bytes(), b"important")

    def test_overlapping_roots_are_rejected_both_directions(self):
        child = self.left / "child"
        child.mkdir()
        with self.assertRaises(ValueError):
            validate_root_pair(self.left, child)
        with self.assertRaises(ValueError):
            validate_root_pair(child, self.left)
        with self.assertRaises(ValueError):
            compare_trees(self.left, child)

    def test_cross_side_case_only_name_never_verifies_same(self):
        self.write(self.left, "A.txt", b"MATCH")
        self.write(self.right, "a.txt", b"MATCH")
        with mock.patch("foldercompare.core._scan_key", side_effect=lambda rel: rel.casefold()):
            result = compare_trees(self.left, self.right, full_verify=True)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].state, CompareState.MODIFIED)
        self.assertIn("path spelling differs", result[0].detail)

    def test_tree_mutation_during_verification_fails_closed(self):
        self.write(self.left, "same.txt", b"same")
        self.write(self.right, "same.txt", b"same")
        real_scan = core.scan_tree
        call_count = 0

        def mutate_after_first_scan(root):
            nonlocal call_count
            snapshot = real_scan(root)
            call_count += 1
            if call_count == 1:
                self.write(self.left, "added-during-verify.txt", b"late")
            return snapshot

        with mock.patch("foldercompare.core.scan_tree", side_effect=mutate_after_first_scan):
            with self.assertRaisesRegex(OSError, "changed during verification"):
                compare_trees(self.left, self.right, full_verify=True)

    def test_same_bytes_same_mtime_object_swap_never_verifies_same(self):
        left_file = self.write(self.left, "same.txt", b"MATCH").resolve()
        self.write(self.right, "same.txt", b"MATCH")
        original = core._sha256_stable
        swapped = False

        def swap_before_read(item, *args, **kwargs):
            nonlocal swapped
            if item.abs_path == left_file and not swapped:
                swapped = True
                parked = left_file.with_name("same.parked")
                scanned = os.lstat(left_file)
                left_file.rename(parked)
                left_file.write_bytes(b"MATCH")
                os.utime(left_file, ns=(scanned.st_atime_ns, scanned.st_mtime_ns))
                try:
                    return original(item, *args, **kwargs)
                finally:
                    left_file.unlink()
                    parked.rename(left_file)
            return original(item, *args, **kwargs)

        with mock.patch("foldercompare.core._sha256_stable", side_effect=swap_before_read):
            entry = states(self.left, self.right)["same.txt"]
        self.assertEqual(entry.state, CompareState.MODIFIED)
        self.assertIn("identity", entry.detail)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink unavailable")
    def test_regular_file_becoming_symlink_before_read_never_verifies_same(self):
        left_file = self.write(self.left, "same.txt", b"MATCH").resolve()
        self.write(self.right, "same.txt", b"MATCH")
        original = core._sha256_stable
        swapped = False

        def link_swap_before_read(item, *args, **kwargs):
            nonlocal swapped
            if item.abs_path == left_file and not swapped:
                swapped = True
                parked = left_file.with_name("same.parked")
                left_file.rename(parked)
                try:
                    os.symlink(parked.name, left_file)
                except OSError as exc:
                    parked.rename(left_file)
                    self.skipTest(f"symlink unavailable: {exc}")
                try:
                    return original(item, *args, **kwargs)
                finally:
                    left_file.unlink()
                    parked.rename(left_file)
            return original(item, *args, **kwargs)

        with mock.patch("foldercompare.core._sha256_stable", side_effect=link_swap_before_read):
            entry = states(self.left, self.right)["same.txt"]
        self.assertEqual(entry.state, CompareState.MODIFIED)
        self.assertIn("identity", entry.detail)

    def test_lstat_error_is_reported_as_unsupported_not_guessed(self):
        blocked = self.write(self.left, "blocked.txt", b"x").resolve()
        real_lstat = os.lstat

        def guarded_lstat(path):
            if Path(path) == blocked:
                raise PermissionError("denied")
            return real_lstat(path)

        with mock.patch("foldercompare.core.os.lstat", side_effect=guarded_lstat):
            item = scan_tree(self.left)["blocked.txt"]
        self.assertEqual(item.kind, EntryType.OTHER)
        self.assertIn("PermissionError", item.link_error or "")

    def test_scan_identity_comes_from_lstat_not_direntry_stat(self):
        file_path = self.write(self.left, "same.txt", b"same")
        expected = os.lstat(file_path)

        class MisleadingEntry:
            name = "same.txt"
            path = str(file_path)

            def stat(self, *, follow_symlinks=False):
                raise AssertionError("DirEntry.stat identity must not be used")

        with mock.patch("foldercompare.core.os.scandir", return_value=[MisleadingEntry()]):
            item = scan_tree(self.left)["same.txt"]
        self.assertEqual(item.kind, EntryType.FILE)
        self.assertEqual((item.device, item.inode), (expected.st_dev, expected.st_ino))

    def test_casefold_key_collision_fails_closed(self):
        base = self.left

        class FakeEntry:
            def __init__(self, name):
                self.name = name
                self.path = str(base / name)

            def stat(self, *, follow_symlinks=False):
                return type(
                    "Stat",
                    (),
                    {
                        "st_dev": 1,
                        "st_ino": 1 if self.name == "A.txt" else 2,
                        "st_mode": stat.S_IFREG | 0o644,
                        "st_mtime_ns": 0,
                        "st_size": 1,
                    },
                )()

            def is_symlink(self):
                return False

            def is_dir(self, *, follow_symlinks=False):
                return False

            def is_file(self, *, follow_symlinks=False):
                return True

        entries = [FakeEntry("A.txt"), FakeEntry("a.txt")]
        with mock.patch("foldercompare.core.os.scandir", return_value=entries), mock.patch(
            "foldercompare.core._scan_key", side_effect=lambda rel: rel.casefold()
        ):
            with self.assertRaises(OSError):
                scan_tree(self.left)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink unavailable")
    def test_symlink_is_compared_as_link_not_followed(self):
        self.write(self.left, "target.txt", b"left")
        self.write(self.right, "target.txt", b"right")
        try:
            os.symlink("target.txt", self.left / "link.txt")
            os.symlink("target.txt", self.right / "link.txt")
        except OSError as exc:
            self.skipTest(f"symlink unavailable: {exc}")
        self.assertEqual(scan_tree(self.left)["link.txt"].kind, EntryType.LINK)
        self.assertEqual(states(self.left, self.right)["link.txt"].state, CompareState.SAME)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink unavailable")
    def test_unreadable_link_fails_closed_not_same(self):
        try:
            os.symlink("one", self.left / "link")
            os.symlink("two", self.right / "link")
        except OSError as exc:
            self.skipTest(f"symlink unavailable: {exc}")
        with mock.patch("foldercompare.core.os.readlink", side_effect=OSError("nope")):
            entry = states(self.left, self.right)["link"]
        self.assertEqual(entry.state, CompareState.MODIFIED)
        self.assertIn("unreadable", entry.detail)

    def test_junction_detection_error_fails_closed(self):
        self.write(self.left, "a.txt", b"same")
        with mock.patch("foldercompare.core.os.path.isjunction", side_effect=OSError("cannot classify"), create=True):
            with self.assertRaises(OSError):
                scan_tree(self.left)

    def test_readonly_file_compares(self):
        a = self.write(self.left, "ro.txt", b"same")
        b = self.write(self.right, "ro.txt", b"same")
        a.chmod(stat.S_IREAD)
        b.chmod(stat.S_IREAD)
        self.assertEqual(states(self.left, self.right)["ro.txt"].state, CompareState.SAME)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO unavailable")
    def test_special_type_fails_closed_not_same(self):
        os.mkfifo(self.left / "pipe")
        os.mkfifo(self.right / "pipe")
        entry = states(self.left, self.right)["pipe"]
        self.assertEqual(entry.kind, EntryType.OTHER)
        self.assertEqual(entry.state, CompareState.MODIFIED)

    def test_large_multichunk_file(self):
        data = b"0123456789abcdef" * 200000
        self.write(self.left, "large.bin", data)
        self.write(self.right, "large.bin", data)
        self.assertEqual(states(self.left, self.right)["large.bin"].state, CompareState.SAME)


if __name__ == "__main__":
    unittest.main()
