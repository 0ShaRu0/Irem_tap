"""Interactive Windows check of a copied, standalone EXE and real keyboard focus.

Run on an unlocked desktop with other iram_tap instances closed. Uses temporary
user data and exits its own windows. Korean Unicode text is injected; native IME
composition should additionally be checked with the user's selected IME.
"""
from __future__ import annotations

import argparse
from contextlib import nullcontext
import ctypes
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import tkinter as tk
from ctypes import wintypes
from pathlib import Path

from PIL import ImageGrab
from pynput.keyboard import Controller, Key


def smoke(executable: Path) -> None:
    if os.name != "nt":
        raise RuntimeError("This check needs an interactive Windows desktop")
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = (callback_type, wintypes.LPARAM)
    user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    user32.GetWindowLongW.argtypes = (wintypes.HWND, ctypes.c_int)
    user32.GetWindowLongW.restype = ctypes.c_long
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetAncestor.argtypes = (wintypes.HWND, wintypes.UINT)
    user32.GetAncestor.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.AttachThreadInput.argtypes = (wintypes.DWORD, wintypes.DWORD, wintypes.BOOL)
    user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
    user32.GetWindowRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
    user32.PostMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

    def windows(title: str) -> list[int]:
        found = []
        @callback_type
        def collect(handle: int, _parameter: int) -> bool:
            text = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(handle, text, len(text))
            if text.value == title:
                found.append(handle)
            return True
        user32.EnumWindows(collect, 0)
        return found

    if windows("iram_tap"):
        raise RuntimeError("Close existing iram_tap instances before the isolated keyboard test")

    root = tk.Tk()
    root.title("iram_tap smoke focus target")
    root.geometry("650x650+20+20")
    root.configure(background="#404040")
    keys = Controller()

    def wait(seconds: float = 0.6) -> None:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            root.update()
            time.sleep(0.02)

    def tap(key: Key) -> None:
        keys.press(key)
        wait(0.1)
        keys.release(key)
        wait()

    def top_image(handle: int):
        bounds = wintypes.RECT()
        assert user32.GetWindowRect(handle, ctypes.byref(bounds))
        return ImageGrab.grab((bounds.left, bounds.top, bounds.right, bounds.top + 140))

    def blue_count(image) -> int:
        rgb = image.convert("RGB")
        return sum(
            (pixel := rgb.getpixel((x, y)))[0] < 100 and 50 < pixel[1] < 170 and pixel[2] > 170
            for y in range(rgb.height) for x in range(rgb.width)
        )

    def bubble_content(image):
        rgb = image.convert("RGB")
        border = [
            (x, y) for y in range(rgb.height) for x in range(rgb.width)
            if (pixel := rgb.getpixel((x, y)))[0] < 100
            and 50 < pixel[1] < 170 and pixel[2] > 170
        ]
        assert border, "Bubble has no visible border"
        left, right = min(x for x, _y in border), max(x for x, _y in border)
        top, bottom = min(y for _x, y in border), max(y for _x, y in border)
        # Transparent pixels contain a live desktop, so compare the opaque body only.
        body = image.crop((left + 12, top + 5, right - 11, bottom - 11))
        return body.size, body.tobytes()

    process = None
    handle = None
    settings_process = None
    workspace = tempfile.TemporaryDirectory(prefix="iram-tap-smoke-", ignore_cleanup_errors=True)
    try:
        with nullcontext(workspace.name) as temporary:
            root_path = Path(temporary)
            install = root_path / "단일 실행 폴더"
            install.mkdir()
            copied = install / "iram_tap.exe"
            shutil.copy2(executable, copied)
            local = root_path / "local"
            config = local / "iram_tap/config.json"
            config.parent.mkdir(parents=True)
            config.write_text(json.dumps({
                "window_x": 120, "window_y": 120,
                "window_position_locked": True, "microphone_enabled": False,
            }), encoding="utf-8")
            environment = {**os.environ, "LOCALAPPDATA": str(local)}
            environment.pop("SDL_VIDEODRIVER", None)
            process = subprocess.Popen([str(copied)], cwd=install, env=environment)
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                wait(0.2)
                handles = windows("iram_tap")
                if handles:
                    handle = handles[0]
                    break
                if process.poll() is not None:
                    raise AssertionError("Standalone overlay exited before opening a window")
            assert handle, "Overlay window did not appear"
            wait(3)
            root.lift()
            root.focus_force()
            wait()
            target = user32.GetAncestor(root.winfo_id(), 2)
            thread = ctypes.windll.kernel32.GetCurrentThreadId()
            foreground_thread = user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), None)
            attached = thread != foreground_thread and user32.AttachThreadInput(thread, foreground_thread, True)
            try:
                user32.SetForegroundWindow(target)
            finally:
                if attached:
                    user32.AttachThreadInput(thread, foreground_thread, False)
            wait(0.08)
            previous = user32.GetForegroundWindow()
            assert previous == target, "Interactive desktop did not grant focus to the test window"
            assert user32.GetWindowLongW(handle, -20) & 0x20, "Locked window is not click-through"
            before = blue_count(top_image(handle))
            tap(Key.f10)
            assert user32.GetForegroundWindow() == handle, (
                f"F10 did not focus the overlay: expected {handle}, actual "
                f"{user32.GetForegroundWindow()}, overlay windows={windows('iram_tap')}"
            )
            assert not user32.GetWindowLongW(handle, -20) & 0x20
            placeholder = top_image(handle)
            assert blue_count(placeholder) > before + 20, "Bubble border was not drawn"
            keys.type("한글 TEST")
            wait()
            tap(Key.enter)
            assert user32.GetForegroundWindow() == previous, "Enter did not restore focus"
            assert user32.GetWindowLongW(handle, -20) & 0x20
            pinned = top_image(handle)
            assert blue_count(pinned) > before + 20, "Pinned bubble disappeared"
            assert pinned.tobytes() != placeholder.tobytes(), "Input did not change the bubble"
            tap(Key.f10)
            assert blue_count(top_image(handle)) <= before + 20, "F10 did not clear the bubble"
            tap(Key.f10)
            reopened = top_image(handle)
            if bubble_content(reopened) != bubble_content(placeholder):
                captures = Path(__file__).resolve().parents[1] / "artifacts/smoke"
                captures.mkdir(parents=True, exist_ok=True)
                placeholder.save(captures / "placeholder.png")
                reopened.save(captures / "reopened.png")
                pinned.save(captures / "pinned.png")
                raise AssertionError("Reopened input was not reset; diagnostic crops in artifacts/smoke")
            tap(Key.f10)
            for key in (Key.f11, Key.f12):
                tap(key)
            assert not windows("iram_tap 설정"), "F12 still opens settings"
            user32.PostMessageW(handle, 0x0010, 0, 0)
            process.wait(timeout=10)
            assert process.returncode == 0
            handle = None

            settings_process = subprocess.Popen([str(copied), "--settings"], cwd=install, env=environment)
            deadline = time.monotonic() + 20
            settings_handle = None
            while time.monotonic() < deadline:
                wait(0.2)
                found = windows("iram_tap 설정")
                if found:
                    settings_handle = found[0]
                    break
            assert settings_handle, "Standalone settings window did not appear"
            user32.PostMessageW(settings_handle, 0x0010, 0, 0)
            settings_process.wait(timeout=10)
            assert settings_process.returncode == 0
            assert list(install.iterdir()) == [copied], "EXE created external runtime resources"
            print("PASS: standalone EXE, text pixels, F10 reset, focus, click-through and settings")
    finally:
        if sys.exc_info()[0] is not None:
            for logfile in Path(workspace.name).glob("local/iram_tap/logs/*.log"):
                print(logfile.read_text(encoding="utf-8"))
        if handle:
            user32.PostMessageW(handle, 0x0010, 0, 0)
        for child in (settings_process, process):
            if child is not None and child.poll() is None:
                subprocess.run(["taskkill", "/PID", str(child.pid), "/T", "/F"], check=False,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                child.wait(timeout=10)
        root.destroy()
        workspace.cleanup()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    smoke(parser.parse_args().executable.resolve())
