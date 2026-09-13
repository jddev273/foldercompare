from __future__ import annotations

import argparse
import ctypes
import hashlib
import os
import shutil
import stat
import subprocess
import time
from pathlib import Path


def build_fixture(root: Path) -> tuple[Path, Path]:
    if root.exists():
        shutil.rmtree(root)
    left = root / "Left"
    right = root / "Right"
    (left / "docs").mkdir(parents=True)
    (right / "docs").mkdir(parents=True)

    (left / "same.txt").write_text("identical content\n", encoding="utf-8")
    (right / "same.txt").write_text("identical content\n", encoding="utf-8")
    (left / "modified.txt").write_text("LEFT version\n", encoding="utf-8")
    (right / "modified.txt").write_text("RIGHT version\n", encoding="utf-8")
    (left / "left-only.txt").write_text("only on the left\n", encoding="utf-8")
    (right / "right-only.txt").write_text("only on the right\n", encoding="utf-8")
    (left / "docs" / "readme.txt").write_text("same nested file\n", encoding="utf-8")
    (right / "docs" / "readme.txt").write_text("same nested file\n", encoding="utf-8")
    (left / "docs" / "notes.txt").write_text("draft A\n", encoding="utf-8")
    (right / "docs" / "notes.txt").write_text("draft B\n", encoding="utf-8")
    return left, right


def tree_fingerprint(root: Path):
    rows = []
    for path in sorted(root.rglob("*"), key=lambda p: str(p).casefold()):
        st = os.lstat(path)
        rel = path.relative_to(root).as_posix()
        mode = stat.S_IFMT(st.st_mode)
        if stat.S_ISREG(st.st_mode):
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            payload = ("file", digest)
        elif path.is_symlink():
            payload = ("link", os.readlink(path))
        elif stat.S_ISDIR(st.st_mode):
            payload = ("dir", None)
        else:
            payload = ("other", None)
        rows.append((rel, mode, st.st_size, st.st_mtime_ns, payload))
    return tuple(rows)


def find_window(title: str, timeout: float = 20.0) -> tuple[int, int]:
    user32 = ctypes.windll.user32
    found: dict[str, int] = {}
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def enum_cb(hwnd, _lparam):
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, len(buf))
        if buf.value == title and user32.IsWindowVisible(hwnd):
            pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            found["hwnd"] = int(hwnd)
            found["pid"] = int(pid.value)
            return False
        return True

    deadline = time.time() + timeout
    callback = WNDENUMPROC(enum_cb)
    while time.time() < deadline:
        found.clear()
        user32.EnumWindows(callback, 0)
        if found:
            return found["hwnd"], found["pid"]
        time.sleep(0.25)
    raise RuntimeError(f"Timed out waiting for visible window titled {title!r}")


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


def get_window_rect(hwnd: int) -> RECT:
    rect = RECT()
    if not ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        raise RuntimeError("GetWindowRect failed")
    return rect


def capture_window(hwnd: int, output: Path, *, min_width: int = 800, min_height: int = 500) -> tuple[int, int]:
    from PIL import ImageGrab, ImageStat

    user32 = ctypes.windll.user32
    rect = get_window_rect(hwnd)
    width = rect.right - rect.left
    height = rect.bottom - rect.top
    if width < min_width or height < min_height:
        raise RuntimeError(f"Unexpected window size: {width}x{height}")

    user32.ShowWindow(hwnd, 9)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.8)
    image = ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom), all_screens=True)
    image_stat = ImageStat.Stat(image.convert("L"))
    if not image_stat.stddev or image_stat.stddev[0] < 8:
        raise RuntimeError(f"Captured image appears blank/flat (stddev={image_stat.stddev})")
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, "PNG")
    return image.size


def main() -> int:
    if os.name != "nt":
        raise SystemExit("windows_visual_proof.py must run on Windows")

    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--read-only-output", required=True)
    args = parser.parse_args()

    exe = Path(args.exe).resolve()
    output = Path(args.output).resolve()
    read_only_output = Path(args.read_only_output).resolve()
    if not exe.is_file():
        raise FileNotFoundError(exe)

    ctypes.windll.user32.SetProcessDPIAware()
    subprocess.run(["taskkill", "/IM", "FolderCompare.exe", "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    fixture_root = Path(os.environ.get("RUNNER_TEMP", os.environ.get("TEMP", "."))) / "FolderCompareProof"
    left, right = build_fixture(fixture_root)
    before = (tree_fingerprint(left), tree_fingerprint(right))
    launcher = subprocess.Popen([str(exe), "--left", str(left), "--right", str(right), "--verify"])
    try:
        hwnd, window_pid = find_window("FolderCompare")
        time.sleep(3.0)
        size = capture_window(hwnd, output)
        if output.stat().st_size < 20_000:
            raise RuntimeError(f"Screenshot is suspiciously small: {output.stat().st_size} bytes")

        # Capture the actual final packaged state a second time after another
        # settle interval, then prove neither selected tree changed.
        time.sleep(1.0)
        second_size = capture_window(hwnd, read_only_output)
        if read_only_output.stat().st_size < 20_000:
            raise RuntimeError(f"Read-only screenshot is suspiciously small: {read_only_output.stat().st_size} bytes")
        after = (tree_fingerprint(left), tree_fingerprint(right))
        if after != before:
            raise RuntimeError("Packaged FolderCompare changed a selected folder during verification")
        if (right / "left-only.txt").exists():
            raise RuntimeError("Packaged FolderCompare copied a missing file even though V1 is read-only")

        print(
            f"WINDOWS_VISUAL_PROOF_OK path={output} size={size[0]}x{size[1]} "
            f"bytes={output.stat().st_size} hwnd={hwnd} pid={window_pid}"
        )
        print(
            f"WINDOWS_READ_ONLY_PROOF_OK path={read_only_output} size={second_size[0]}x{second_size[1]} "
            f"bytes={read_only_output.stat().st_size} selected_trees_unchanged=pass"
        )
    finally:
        subprocess.run(["taskkill", "/IM", "FolderCompare.exe", "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            launcher.wait(timeout=5)
        except subprocess.TimeoutExpired:
            launcher.kill()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
