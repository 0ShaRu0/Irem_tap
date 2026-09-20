from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from typing import Any

import pygame

from iram_tap.models import Command, WindowState
from iram_tap.ui.menu_model import menu_entries


class MonitorInfo(ctypes.Structure):
    _fields_ = (
        ("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD),
    )


class BlendFunction(ctypes.Structure):
    _fields_ = tuple((name, wintypes.BYTE) for name in (
        "BlendOp", "BlendFlags", "SourceConstantAlpha", "AlphaFormat"
    ))


class BitmapInfoHeader(ctypes.Structure):
    _fields_ = (
        ("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD), ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD),
    )


class RgbQuad(ctypes.Structure):
    _fields_ = tuple((name, wintypes.BYTE) for name in (
        "rgbBlue", "rgbGreen", "rgbRed", "rgbReserved"
    ))


class BitmapInfo(ctypes.Structure):
    _fields_ = (("bmiHeader", BitmapInfoHeader), ("bmiColors", RgbQuad * 1))


_USER32: Any = None
_GDI32: Any = None


def user32_api() -> Any:
    global _USER32
    if _USER32 is not None:
        return _USER32
    dll = ctypes.WinDLL("user32", use_last_error=True)
    pointer = ctypes.POINTER
    h, i, u, b = wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.BOOL
    signatures = {
        "GetWindowLongW": ((h, i), ctypes.c_long),
        "SetWindowLongW": ((h, i, ctypes.c_long), ctypes.c_long),
        "SetLayeredWindowAttributes": ((h, wintypes.COLORREF, wintypes.BYTE, wintypes.DWORD), b),
        "SetWindowPos": ((h, h, i, i, i, i, u), b),
        "ShowWindow": ((h, i), b),
        "GetWindowRect": ((h, pointer(wintypes.RECT)), b),
        "ReleaseCapture": ((), b),
        "SendMessageW": ((h, u, wintypes.WPARAM, wintypes.LPARAM), ctypes.c_ssize_t),
        "MonitorFromRect": ((pointer(wintypes.RECT), wintypes.DWORD), wintypes.HANDLE),
        "MonitorFromPoint": ((wintypes.POINT, wintypes.DWORD), wintypes.HANDLE),
        "GetMonitorInfoW": ((wintypes.HANDLE, pointer(MonitorInfo)), b),
        "GetCursorPos": ((pointer(wintypes.POINT),), b),
        "CreatePopupMenu": ((), wintypes.HMENU),
        "AppendMenuW": ((wintypes.HMENU, u, ctypes.c_size_t, wintypes.LPCWSTR), b),
        "TrackPopupMenu": ((wintypes.HMENU, u, i, i, i, h, ctypes.c_void_p), u),
        "DestroyMenu": ((wintypes.HMENU,), b),
        "SetForegroundWindow": ((h,), b),
        "GetForegroundWindow": ((), h),
        "IsWindow": ((h,), b),
        "PostMessageW": ((h, u, wintypes.WPARAM, wintypes.LPARAM), b),
        "UpdateLayeredWindow": ((h, wintypes.HDC, pointer(wintypes.POINT),
            pointer(wintypes.SIZE), wintypes.HDC, pointer(wintypes.POINT),
            wintypes.COLORREF, pointer(BlendFunction), wintypes.DWORD), b),
    }
    for name, (arguments, result) in signatures.items():
        function = getattr(dll, name)
        function.argtypes, function.restype = arguments, result
    _USER32 = dll
    return dll


def gdi32_api() -> Any:
    global _GDI32
    if _GDI32 is not None:
        return _GDI32
    dll = ctypes.WinDLL("gdi32", use_last_error=True)
    signatures = {
        "CreateCompatibleDC": ((wintypes.HDC,), wintypes.HDC),
        "CreateDIBSection": ((wintypes.HDC, ctypes.POINTER(BitmapInfo), wintypes.UINT,
            ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD), wintypes.HBITMAP),
        "SelectObject": ((wintypes.HDC, wintypes.HGDIOBJ), wintypes.HGDIOBJ),
        "DeleteObject": ((wintypes.HGDIOBJ,), wintypes.BOOL),
        "DeleteDC": ((wintypes.HDC,), wintypes.BOOL),
    }
    for name, (arguments, result) in signatures.items():
        function = getattr(dll, name)
        function.argtypes, function.restype = arguments, result
    _GDI32 = dll
    return dll


class LayeredWindowPresenter:
    def __init__(self) -> None:
        self.memory_dc: int | None = None
        self.bitmap: int | None = None
        self.previous_bitmap: int | None = None
        self.bits: int | None = None
        self.size: tuple[int, int] | None = None

    @staticmethod
    def _raise_windows_error(operation: str, error_code: int | None = None) -> None:
        code = ctypes.get_last_error() if error_code is None else error_code
        raise OSError(code, f"{operation} 실패")

    def _create_buffer(self, size: tuple[int, int]) -> None:
        self.close()
        width, height = size
        gdi32 = gdi32_api()
        self.memory_dc = gdi32.CreateCompatibleDC(None)
        if not self.memory_dc:
            self._raise_windows_error("CreateCompatibleDC")
        information = BitmapInfo()
        information.bmiHeader.biSize = ctypes.sizeof(BitmapInfoHeader)
        information.bmiHeader.biWidth = width
        information.bmiHeader.biHeight = -height
        information.bmiHeader.biPlanes = 1
        information.bmiHeader.biBitCount = 32
        information.bmiHeader.biSizeImage = width * height * 4
        bits = ctypes.c_void_p()
        self.bitmap = gdi32.CreateDIBSection(
            self.memory_dc, ctypes.byref(information), 0, ctypes.byref(bits), None, 0
        )
        if not self.bitmap or not bits.value:
            error_code = ctypes.get_last_error()
            self.close()
            self._raise_windows_error("CreateDIBSection", error_code)
        self.bits = bits.value
        self.previous_bitmap = gdi32.SelectObject(self.memory_dc, self.bitmap)
        if not self.previous_bitmap or self.previous_bitmap == ctypes.c_void_p(-1).value:
            error_code = ctypes.get_last_error()
            self.previous_bitmap = None
            self.close()
            self._raise_windows_error("SelectObject", error_code)
        self.size = size

    def present(self, window_handle: int, frame: pygame.Surface, window_alpha: int = 255) -> None:
        size = frame.get_size()
        if self.size != size:
            self._create_buffer(size)
        assert self.memory_dc is not None and self.bits is not None
        pixels = pygame.image.tobytes(frame.premul_alpha(), "BGRA", False)
        ctypes.memmove(self.bits, pixels, len(pixels))
        rectangle = wintypes.RECT()
        user32 = user32_api()
        if not user32.GetWindowRect(window_handle, ctypes.byref(rectangle)):
            self._raise_windows_error("GetWindowRect")
        destination = wintypes.POINT(rectangle.left, rectangle.top)
        source = wintypes.POINT(0, 0)
        dimensions = wintypes.SIZE(*size)
        blend = BlendFunction(0, 0, max(0, min(255, int(window_alpha))), 1)
        if not user32.UpdateLayeredWindow(
            window_handle, None, ctypes.byref(destination), ctypes.byref(dimensions),
            self.memory_dc, ctypes.byref(source), 0, ctypes.byref(blend), 2
        ):
            self._raise_windows_error("UpdateLayeredWindow")

    def close(self) -> None:
        if self.memory_dc is None:
            return
        gdi32 = gdi32_api()
        if self.previous_bitmap is not None:
            gdi32.SelectObject(self.memory_dc, self.previous_bitmap)
        if self.bitmap is not None:
            gdi32.DeleteObject(self.bitmap)
        gdi32.DeleteDC(self.memory_dc)
        self.memory_dc = self.bitmap = self.previous_bitmap = self.bits = self.size = None


def enable_dpi_awareness() -> None:
    if os.name != "nt":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


class WindowController:
    """Window operations. HWNDs are supplied by the SDL adapter, never cached."""

    def rectangle(self, handle: int | None) -> Any:
        if not handle:
            return None
        rectangle = wintypes.RECT()
        return rectangle if user32_api().GetWindowRect(handle, ctypes.byref(rectangle)) else None

    def move(self, handle: int | None, x: int, y: int) -> None:
        if handle:
            user32_api().SetWindowPos(handle, wintypes.HWND(0), x, y, 0, 0, 0x0015)

    def topmost(self, handle: int | None, enabled: bool) -> None:
        if handle:
            user32_api().SetWindowPos(handle, wintypes.HWND(-1 if enabled else -2), 0, 0, 0, 0, 0x0013)

    def apply(self, handle: int | None, *, borderless: bool, transparent: bool,
              locked: bool, editing: bool, topmost: bool) -> None:
        if not handle:
            return
        user32 = user32_api()
        style = user32.GetWindowLongW(handle, -20)
        noactivate, passthrough, layered = 0x08000000, 0x00000020, 0x00080000
        if borderless and locked and not editing:
            style |= noactivate | passthrough
        else:
            style &= ~(noactivate | passthrough)
        if transparent:
            # Reset the alpha mode before using UpdateLayeredWindow.
            user32.SetWindowLongW(handle, -20, style & ~layered)
            user32.SetWindowLongW(handle, -20, style | layered)
        elif borderless or locked:
            user32.SetWindowLongW(handle, -20, style | layered)
            user32.SetLayeredWindowAttributes(handle, 0, 255, 2)
        else:
            user32.SetWindowLongW(handle, -20, style & ~layered)
        self.topmost(handle, topmost)

    @staticmethod
    def visible_position(x: int, y: int, width: int, height: int) -> tuple[int, int]:
        if os.name != "nt":
            return x, y
        user32 = user32_api()
        rectangle = wintypes.RECT(x, y, x + width, y + height)
        monitor = user32.MonitorFromRect(ctypes.byref(rectangle), 2)
        information = MonitorInfo()
        information.cbSize = ctypes.sizeof(MonitorInfo)
        if not monitor or not user32.GetMonitorInfoW(monitor, ctypes.byref(information)):
            return x, y
        work = information.rcWork
        return (
            max(work.left, min(x, work.right - width)),
            max(work.top, min(y, work.bottom - height)),
        )

    @staticmethod
    def cursor_ratio(position: tuple[float, float] | None) -> tuple[float, float] | None:
        if position is None:
            return None
        mouse_x, mouse_y = position
        left = top = 0
        sizes = pygame.display.get_desktop_sizes()
        width, height = sizes[0] if sizes else (1, 1)
        if os.name == "nt":
            user32 = user32_api()
            monitor = user32.MonitorFromPoint(wintypes.POINT(round(mouse_x), round(mouse_y)), 2)
            information = MonitorInfo()
            information.cbSize = ctypes.sizeof(MonitorInfo)
            if monitor and user32.GetMonitorInfoW(monitor, ctypes.byref(information)):
                bounds = information.rcMonitor
                left, top = bounds.left, bounds.top
                width, height = bounds.right - left, bounds.bottom - top
        return (
            max(0.0, min(1.0, (mouse_x - left) / max(1, width - 1))),
            max(0.0, min(1.0, (mouse_y - top) / max(1, height - 1))),
        )

    @staticmethod
    def show_menu(handle: int, state: WindowState) -> Command | None:
        user32 = user32_api()
        handles = []
        commands: dict[int, Command] = {}

        def build(entries: Any) -> int:
            menu = user32.CreatePopupMenu()
            if not menu:
                raise OSError("CreatePopupMenu failed")
            handles.append(menu)
            for entry in entries:
                flags = 0x0008 if entry.checked else 0
                if entry.children:
                    submenu = build(entry.children)
                    identifier = ctypes.cast(submenu, ctypes.c_void_p).value
                    flags |= 0x0010
                else:
                    identifier = len(commands) + 1
                    commands[identifier] = entry.command
                if not user32.AppendMenuW(menu, flags, identifier, entry.label):
                    raise OSError("AppendMenuW failed")
                if entry.children:
                    handles.remove(submenu)  # Parent owns this child now.
            return menu

        try:
            menu = build(menu_entries(state))
            cursor = wintypes.POINT()
            if not user32.GetCursorPos(ctypes.byref(cursor)):
                return None
            user32.SetForegroundWindow(handle)
            selected = user32.TrackPopupMenu(menu, 0x0102, cursor.x, cursor.y, 0, handle, None)
            user32.PostMessageW(handle, 0, 0, 0)
            return commands.get(selected)
        finally:
            for menu in reversed(handles):
                user32.DestroyMenu(menu)
