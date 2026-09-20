from __future__ import annotations

import ctypes
import logging
import threading
from collections.abc import Callable
from ctypes import wintypes
from typing import Any

logger = logging.getLogger(__name__)


class TextHotkey:
    """WM_HOTKEY gives this process the right to foreground its input window."""

    def __init__(self, callback: Callable[[], None]) -> None:
        self.callback = callback
        self.registered = False
        self._ready = threading.Event()
        self._thread: threading.Thread | None = None
        self._thread_id: int | None = None
        self._user32: Any = None

    def start(self) -> bool:
        self._thread = threading.Thread(target=self._run, name="iram_tap_f10", daemon=True)
        self._thread.start()
        if not self._ready.wait(3):
            logger.error("F10 전역 단축키 등록 시간 초과")
        return self.registered

    def _run(self) -> None:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.RegisterHotKey.argtypes = (wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT)
        user32.RegisterHotKey.restype = wintypes.BOOL
        user32.UnregisterHotKey.argtypes = (wintypes.HWND, ctypes.c_int)
        user32.GetMessageW.argtypes = (ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT)
        user32.GetMessageW.restype = ctypes.c_int
        user32.PostThreadMessageW.argtypes = (wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
        self._user32 = user32
        self._thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
        try:
            self.registered = bool(user32.RegisterHotKey(None, 1, 0x4000, 0x79))
            self._ready.set()
            if not self.registered:
                logger.warning("F10 전역 단축키 등록 실패: %s", ctypes.get_last_error())
                return
            logger.info("F10 전역 단축키 등록 완료")
            message = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                if message.message == 0x0312 and message.wParam == 1:  # WM_HOTKEY
                    self.callback()
        finally:
            if self.registered:
                user32.UnregisterHotKey(None, 1)
            self.registered = False
            self._ready.set()

    def stop(self) -> None:
        if self._thread_id and self._user32 is not None:
            self._user32.PostThreadMessageW(self._thread_id, 0x0012, 0, 0)  # WM_QUIT
        if self._thread is not None:
            self._thread.join(timeout=3)
        self._thread = None
