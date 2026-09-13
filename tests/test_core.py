import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from foldercompare.core import CompareState, EntryType, compare_trees, copy_selected, scan_tree, validate_root_pair


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
        self.write(self.left, "a.txt", b"hello"); self.write(self.right, "a.txt", b"hello")
        self.assertEqual(states(self.left, self.right)["a.txt"].state, CompareState.SAME)

    def test_same_content_different_mtime_is_still_same(self):
        a=self.write(self.left,"a.txt",b"hello"); b=self.write(self.right,"a.txt",b"hello")
        os.utime(a,(1,1)); os.utime(b,(2,2)); e=states(self.left,self.right)["a.txt"]
        self.assertEqual(e.state, CompareState.SAME); self.assertIn("metadata differs", e.detail)

    def test_same_size_different_content_is_modified(self):
        self.write(self.left,"a.bin",b"AAAA"); self.write(self.right,"a.bin",b"BBBB")
        self.assertEqual(states(self.left,self.right)["a.bin"].state, CompareState.MODIFIED)

    def test_size_short_circuit(self):
        self.write(self.left,"a.bin",b"A"); self.write(self.right,"a.bin",b"BBBB")
        self.assertEqual(states(self.left,self.right)["a.bin"].detail, "size differs")

    def test_left_and_right_only(self):
        self.write(self.left,"left.txt",b"L"); self.write(self.right,"right.txt",b"R"); s=states(self.left,self.right)
        self.assertEqual(s["left.txt"].state,CompareState.LEFT_ONLY); self.assertEqual(s["right.txt"].state,CompareState.RIGHT_ONLY)

    def test_type_mismatch(self):
        self.write(self.left,"thing",b"file"); (self.right/"thing").mkdir()
        self.assertEqual(states(self.left,self.right)["thing"].state,CompareState.MODIFIED)

    def test_nested_folder_reflects_child_difference(self):
        self.write(self.left,"nested/a.txt",b"A"); self.write(self.right,"nested/a.txt",b"B"); s=states(self.left,self.right)
        self.assertEqual(s["nested/a.txt"].state,CompareState.MODIFIED); self.assertEqual(s["nested"].state,CompareState.MODIFIED)

    def test_empty_folder_same(self):
        (self.left/"empty").mkdir(); (self.right/"empty").mkdir()
        self.assertEqual(states(self.left,self.right)["empty"].state,CompareState.SAME)

    def test_unicode_and_zero_byte(self):
        self.write(self.left,"日本語/é.txt",b""); self.write(self.right,"日本語/é.txt",b"")
        self.assertEqual(states(self.left,self.right)["日本語/é.txt"].state,CompareState.SAME)

    def test_full_byte_verification(self):
        self.write(self.left,"a",b"x"*1024); self.write(self.right,"a",b"x"*1024)
        self.assertEqual(states(self.left,self.right,full=True)["a"].detail,"byte-for-byte verified")

    def test_copy_missing_file_succeeds_without_overwrite(self):
        self.write(self.left, "a.txt", b"new")
        copy_selected(self.left, self.right, "a.txt", overwrite=False)
        self.assertEqual((self.right / "a.txt").read_bytes(), b"new")

    def test_existing_destination_is_never_overwritten(self):
        self.write(self.left, "a.txt", b"new")
        dst = self.write(self.right, "a.txt", b"old-important")
        with self.assertRaises(FileExistsError):
            copy_selected(self.left, self.right, "a.txt", overwrite=True)
        self.assertEqual(dst.read_bytes(), b"old-important")

    def test_folder_copy_is_compare_only(self):
        self.write(self.left, "d/new.txt", b"new")
        with self.assertRaises(ValueError):
            copy_selected(self.left, self.right, "d", overwrite=False)
        self.assertFalse((self.right / "d").exists())

    def test_same_root_is_rejected_without_mutation(self):
        victim = self.write(self.left, "victim.txt", b"important")
        with self.assertRaises(ValueError):
            copy_selected(self.left, self.left, "victim.txt", overwrite=True)
        self.assertEqual(victim.read_bytes(), b"important")
        with self.assertRaises(ValueError):
            compare_trees(self.left, self.left)

    def test_overlapping_roots_are_rejected_both_directions(self):
        child = self.left / "child"
        child.mkdir()
        with self.assertRaises(ValueError):
            validate_root_pair(self.left, child)
        with self.assertRaises(ValueError):
            validate_root_pair(child, self.left)
        with self.assertRaises(ValueError):
            compare_trees(self.left, child)

    def test_relpath_escape_is_rejected(self):
        outside = self.left.parent / "outside.txt"
        outside.write_bytes(b"secret")
        with self.assertRaises(ValueError):
            copy_selected(self.left, self.right, "../outside.txt", overwrite=True)
        self.assertEqual(outside.read_bytes(), b"secret")

    def test_failed_staging_leaves_destination_missing(self):
        self.write(self.left, "a.txt", b"new-important")
        with mock.patch("foldercompare.core.shutil.copy2", side_effect=OSError("simulated disk failure")):
            with self.assertRaises(OSError):
                copy_selected(self.left, self.right, "a.txt", overwrite=False)
        self.assertFalse((self.right / "a.txt").exists())

    def test_destination_created_during_staging_is_never_overwritten(self):
        self.write(self.left, "a.txt", b"new-important")
        dst = self.right / "a.txt"
        from foldercompare import core
        real_copy = core._copy_plain_object
        def mutate_after_stage(source, staging):
            real_copy(source, staging)
            dst.write_bytes(b"external-change")
        with mock.patch("foldercompare.core._copy_plain_object", side_effect=mutate_after_stage):
            with self.assertRaises((FileExistsError, OSError)):
                copy_selected(self.left, self.right, "a.txt", overwrite=False)
        self.assertEqual(dst.read_bytes(), b"external-change")

    def test_publish_failure_cleans_staging_without_creating_destination(self):
        self.write(self.left, "a.txt", b"new-important")
        dst = self.right / "a.txt"
        with mock.patch("foldercompare.core._commit_missing_file_no_replace", side_effect=OSError("simulated publish failure")):
            with self.assertRaises(OSError):
                copy_selected(self.left, self.right, "a.txt", overwrite=False)
        self.assertFalse(dst.exists())
        self.assertFalse(any(self.right.glob(".a.txt.foldercompare-stage-*")))

    def test_casefold_key_collision_fails_closed(self):
        self.write(self.left, "A.txt", b"one")
        self.write(self.left, "a.txt", b"two")
        with mock.patch("foldercompare.core._scan_key", side_effect=lambda rel: rel.casefold()):
            with self.assertRaises(OSError):
                scan_tree(self.left)

    @unittest.skipUnless(hasattr(os,"symlink"),"symlink unavailable")
    def test_symlink_is_compared_as_link_not_followed_and_copy_blocked(self):
        self.write(self.left,"target.txt",b"left"); self.write(self.right,"target.txt",b"right")
        try:
            os.symlink("target.txt",self.left/"link.txt"); os.symlink("target.txt",self.right/"link.txt")
        except OSError as exc: self.skipTest(f"symlink unavailable: {exc}")
        self.assertEqual(scan_tree(self.left)["link.txt"].kind,EntryType.LINK)
        self.assertEqual(states(self.left,self.right)["link.txt"].state,CompareState.SAME)
        with self.assertRaises(ValueError): copy_selected(self.left,self.right,"link.txt",overwrite=True)

    @unittest.skipUnless(hasattr(os,"symlink"),"symlink unavailable")
    def test_unreadable_link_fails_closed_not_same(self):
        try:
            os.symlink("one",self.left/"link"); os.symlink("two",self.right/"link")
        except OSError as exc: self.skipTest(f"symlink unavailable: {exc}")
        with mock.patch("foldercompare.core.os.readlink",side_effect=OSError("nope")):
            e=states(self.left,self.right)["link"]
        self.assertEqual(e.state,CompareState.MODIFIED); self.assertIn("unreadable",e.detail)

    def test_readonly_file_compares(self):
        a=self.write(self.left,"ro.txt",b"same"); b=self.write(self.right,"ro.txt",b"same")
        a.chmod(stat.S_IREAD); b.chmod(stat.S_IREAD)
        self.assertEqual(states(self.left,self.right)["ro.txt"].state,CompareState.SAME)

    @unittest.skipUnless(hasattr(os,"mkfifo"),"FIFO unavailable")
    def test_special_type_fails_closed_not_same(self):
        os.mkfifo(self.left/"pipe"); os.mkfifo(self.right/"pipe"); e=states(self.left,self.right)["pipe"]
        self.assertEqual(e.kind,EntryType.OTHER); self.assertEqual(e.state,CompareState.MODIFIED)
        with self.assertRaises(ValueError): copy_selected(self.left,self.right,"pipe",overwrite=True)

    def test_large_multichunk_file(self):
        data=b"0123456789abcdef"*200000; self.write(self.left,"large.bin",data); self.write(self.right,"large.bin",data)
        self.assertEqual(states(self.left,self.right)["large.bin"].state,CompareState.SAME)


if __name__ == "__main__": unittest.main()
