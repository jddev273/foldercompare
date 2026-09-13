from __future__ import annotations

import argparse
import ctypes
import os
import shutil
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


def capture_window(hwnd: int, output: Path) -> tuple[int, int]:
    from PIL import ImageGrab, ImageStat

    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    user32 = ctypes.windll.user32
    rect = RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        raise RuntimeError("GetWindowRect failed")
    width = rect.right - rect.left
    height = rect.bottom - rect.top
    if width < 800 or height < 500:
        raise RuntimeError(f"Unexpected app window size: {width}x{height}")

    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.8)

    image = ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom), all_screens=True)
    stat = ImageStat.Stat(image.convert("L"))
    if not stat.stddev or stat.stddev[0] < 8:
        raise RuntimeError(f"Captured image appears blank/flat (stddev={stat.stddev})")
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, "PNG")
    return image.size


def main() -> int:
    if os.name != "nt":
        raise SystemExit("windows_visual_proof.py must run on Windows")

    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    exe = Path(args.exe).resolve()
    output = Path(args.output).resolve()
    if not exe.is_file():
        raise FileNotFoundError(exe)

    ctypes.windll.user32.SetProcessDPIAware()
    subprocess.run(["taskkill", "/IM", "FolderCompare.exe", "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    fixture_root = Path(os.environ.get("RUNNER_TEMP", os.environ.get("TEMP", "."))) / "FolderCompareProof"
    left, right = build_fixture(fixture_root)
    launcher = subprocess.Popen([str(exe), "--left", str(left), "--right", str(right), "--verify"])
    try:
        hwnd, window_pid = find_window("FolderCompare")
        # The fixture is intentionally tiny; this gives the asynchronous scan time to finish and paint the final counts/tree.
        time.sleep(3.0)
        size = capture_window(hwnd, output)
        if output.stat().st_size < 20_000:
            raise RuntimeError(f"Screenshot is suspiciously small: {output.stat().st_size} bytes")
        print(f"WINDOWS_VISUAL_PROOF_OK path={output} size={size[0]}x{size[1]} bytes={output.stat().st_size} hwnd={hwnd} pid={window_pid}")
    finally:
        subprocess.run(["taskkill", "/IM", "FolderCompare.exe", "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            launcher.wait(timeout=5)
        except subprocess.TimeoutExpired:
            launcher.kill()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
