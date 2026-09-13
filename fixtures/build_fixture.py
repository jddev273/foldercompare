"""Build a deterministic manual QA corpus.

Usage: python fixtures/build_fixture.py <output-dir>
Creates left/ and right/ without following links.
"""
from pathlib import Path
import os, stat, sys

base = Path(sys.argv[1] if len(sys.argv) > 1 else "fixture-corpus")
left, right = base / "left", base / "right"
for p in (left, right): p.mkdir(parents=True, exist_ok=True)

def w(root, rel, data):
    p = root / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(data); return p

for r in (left, right):
    w(r, "same.txt", b"same\n")
    w(r, "empty.bin", b"")
    w(r, "unicode/日本語-é.txt", "snowman ☃\n".encode())
    w(r, "large/multichunk.bin", b"0123456789abcdef" * 150000)
w(left, "modified-same-size.bin", b"AAAA")
w(right, "modified-same-size.bin", b"BBBB")
w(left, "modified-size.txt", b"short")
w(right, "modified-size.txt", b"much longer")
w(left, "left-only.txt", b"left")
w(right, "right-only.txt", b"right")
w(left, "type-mismatch", b"file")
(right / "type-mismatch").mkdir()
w(left, "nested/child.txt", b"before")
w(right, "nested/child.txt", b"after!")
(left / "empty-folder").mkdir(); (right / "empty-folder").mkdir()
os.utime(left / "same.txt", (1, 1)); os.utime(right / "same.txt", (2, 2))
try:
    os.symlink("same.txt", left / "same-link")
    os.symlink("same.txt", right / "same-link")
    os.symlink("left-only.txt", left / "different-link")
    os.symlink("right-only.txt", right / "different-link")
except OSError:
    pass
try:
    (left / "readonly.txt").write_text("read only", encoding="utf-8")
    (right / "readonly.txt").write_text("read only", encoding="utf-8")
    (left / "readonly.txt").chmod(stat.S_IREAD)
    (right / "readonly.txt").chmod(stat.S_IREAD)
except OSError:
    pass
print(base.resolve())
