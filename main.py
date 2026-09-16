from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import math
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pygame

from config_manager import (
    WINDOW_SCALES,
    default_config_path,
    load_config,
    load_config_strict,
    resolve_asset_path,
    update_config,
)
from input_manager import InputManager
from image_modes import (
    KEYBOARD_MODE_NAME,
    ImageMode,
    discover_image_modes,
)
from microphone_manager import MicrophoneManager
from renderer import LayerRenderer
from tray_manager import TrayManager


WINDOW_TITLE = "iram_tap"
LOCKED_HOVER_ALPHA = 128

CONTEXT_SETTINGS = 1001
CONTEXT_HIDE = 1002
CONTEXT_SCALE_125 = 1125
CONTEXT_SCALE_150 = 1150
CONTEXT_TOPMOST = 1201
CONTEXT_POSITION_LOCK = 1202
CONTEXT_QUIT = 1299


class MonitorInfo(ctypes.Structure):
    _fields_ = (
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    )


class BlendFunction(ctypes.Structure):
    _fields_ = (
        ("BlendOp", wintypes.BYTE),
        ("BlendFlags", wintypes.BYTE),
        ("SourceConstantAlpha", wintypes.BYTE),
        ("AlphaFormat", wintypes.BYTE),
    )


class BitmapInfoHeader(ctypes.Structure):
    _fields_ = (
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    )


class RgbQuad(ctypes.Structure):
    _fields_ = (
        ("rgbBlue", wintypes.BYTE),
        ("rgbGreen", wintypes.BYTE),
        ("rgbRed", wintypes.BYTE),
        ("rgbReserved", wintypes.BYTE),
    )


class BitmapInfo(ctypes.Structure):
    _fields_ = (
        ("bmiHeader", BitmapInfoHeader),
        ("bmiColors", RgbQuad * 1),
    )


_USER32: Any | None = None
_GDI32: Any | None = None


def user32_api() -> Any:
    global _USER32
    if _USER32 is not None:
        return _USER32

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetWindowLongW.argtypes = (wintypes.HWND, ctypes.c_int)
    user32.GetWindowLongW.restype = ctypes.c_long
    user32.SetWindowLongW.argtypes = (wintypes.HWND, ctypes.c_int, ctypes.c_long)
    user32.SetWindowLongW.restype = ctypes.c_long
    user32.SetLayeredWindowAttributes.argtypes = (
        wintypes.HWND,
        wintypes.COLORREF,
        wintypes.BYTE,
        wintypes.DWORD,
    )
    user32.SetLayeredWindowAttributes.restype = wintypes.BOOL
    user32.SetWindowPos.argtypes = (
        wintypes.HWND,
        wintypes.HWND,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.UINT,
    )
    user32.SetWindowPos.restype = wintypes.BOOL
    user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
    user32.ShowWindow.restype = wintypes.BOOL
    user32.GetWindowRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
    user32.GetWindowRect.restype = wintypes.BOOL
    user32.ReleaseCapture.argtypes = ()
    user32.ReleaseCapture.restype = wintypes.BOOL
    user32.SendMessageW.argtypes = (
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    )
    user32.SendMessageW.restype = ctypes.c_ssize_t
    user32.MonitorFromRect.argtypes = (ctypes.POINTER(wintypes.RECT), wintypes.DWORD)
    user32.MonitorFromRect.restype = wintypes.HANDLE
    user32.MonitorFromPoint.argtypes = (wintypes.POINT, wintypes.DWORD)
    user32.MonitorFromPoint.restype = wintypes.HANDLE
    user32.GetMonitorInfoW.argtypes = (wintypes.HANDLE, ctypes.POINTER(MonitorInfo))
    user32.GetMonitorInfoW.restype = wintypes.BOOL
    user32.GetCursorPos.argtypes = (ctypes.POINTER(wintypes.POINT),)
    user32.GetCursorPos.restype = wintypes.BOOL
    user32.CreatePopupMenu.argtypes = ()
    user32.CreatePopupMenu.restype = wintypes.HMENU
    user32.AppendMenuW.argtypes = (
        wintypes.HMENU,
        wintypes.UINT,
        ctypes.c_size_t,
        wintypes.LPCWSTR,
    )
    user32.AppendMenuW.restype = wintypes.BOOL
    user32.TrackPopupMenu.argtypes = (
        wintypes.HMENU,
        wintypes.UINT,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.HWND,
        ctypes.c_void_p,
    )
    user32.TrackPopupMenu.restype = wintypes.UINT
    user32.DestroyMenu.argtypes = (wintypes.HMENU,)
    user32.DestroyMenu.restype = wintypes.BOOL
    user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
    user32.SetForegroundWindow.restype = wintypes.BOOL
    user32.PostMessageW.argtypes = (
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    )
    user32.PostMessageW.restype = wintypes.BOOL
    user32.UpdateLayeredWindow.argtypes = (
        wintypes.HWND,
        wintypes.HDC,
        ctypes.POINTER(wintypes.POINT),
        ctypes.POINTER(wintypes.SIZE),
        wintypes.HDC,
        ctypes.POINTER(wintypes.POINT),
        wintypes.COLORREF,
        ctypes.POINTER(BlendFunction),
        wintypes.DWORD,
    )
    user32.UpdateLayeredWindow.restype = wintypes.BOOL
    _USER32 = user32
    return _USER32


def gdi32_api() -> Any:
    global _GDI32
    if _GDI32 is not None:
        return _GDI32

    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    gdi32.CreateCompatibleDC.argtypes = (wintypes.HDC,)
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.CreateDIBSection.argtypes = (
        wintypes.HDC,
        ctypes.POINTER(BitmapInfo),
        wintypes.UINT,
        ctypes.POINTER(ctypes.c_void_p),
        wintypes.HANDLE,
        wintypes.DWORD,
    )
    gdi32.CreateDIBSection.restype = wintypes.HBITMAP
    gdi32.SelectObject.argtypes = (wintypes.HDC, wintypes.HGDIOBJ)
    gdi32.SelectObject.restype = wintypes.HGDIOBJ
    gdi32.DeleteObject.argtypes = (wintypes.HGDIOBJ,)
    gdi32.DeleteObject.restype = wintypes.BOOL
    gdi32.DeleteDC.argtypes = (wintypes.HDC,)
    gdi32.DeleteDC.restype = wintypes.BOOL
    _GDI32 = gdi32
    return _GDI32


class LayeredWindowPresenter:
    def __init__(self) -> None:
        self.memory_dc: int | None = None
        self.bitmap: int | None = None
        self.previous_bitmap: int | None = None
        self.bits: int | None = None
        self.size: tuple[int, int] | None = None

    @staticmethod
    def _raise_windows_error(operation: str, error_code: int | None = None) -> None:
        if error_code is None:
            error_code = ctypes.get_last_error()
        raise OSError(error_code, f"{operation} 실패")

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
        information.bmiHeader.biCompression = 0  # BI_RGB
        information.bmiHeader.biSizeImage = width * height * 4
        bits = ctypes.c_void_p()
        self.bitmap = gdi32.CreateDIBSection(
            self.memory_dc,
            ctypes.byref(information),
            0,  # DIB_RGB_COLORS
            ctypes.byref(bits),
            None,
            0,
        )
        if not self.bitmap or not bits.value:
            error_code = ctypes.get_last_error()
            self.close()
            self._raise_windows_error("CreateDIBSection", error_code)

        self.bits = bits.value
        self.previous_bitmap = gdi32.SelectObject(self.memory_dc, self.bitmap)
        invalid_handle = ctypes.c_void_p(-1).value
        if not self.previous_bitmap or self.previous_bitmap == invalid_handle:
            error_code = ctypes.get_last_error()
            self.previous_bitmap = None
            self.close()
            self._raise_windows_error("SelectObject", error_code)
        self.size = size

    def present(
        self, window_handle: int, frame: pygame.Surface, window_alpha: int = 255
    ) -> None:
        size = frame.get_size()
        if self.size != size:
            self._create_buffer(size)
        assert self.memory_dc is not None
        assert self.bits is not None

        pixels = pygame.image.tobytes(frame.premul_alpha(), "BGRA", False)
        ctypes.memmove(self.bits, pixels, len(pixels))

        rectangle = wintypes.RECT()
        user32 = user32_api()
        if not user32.GetWindowRect(window_handle, ctypes.byref(rectangle)):
            self._raise_windows_error("GetWindowRect")
        destination = wintypes.POINT(rectangle.left, rectangle.top)
        source = wintypes.POINT(0, 0)
        dimensions = wintypes.SIZE(*size)
        window_alpha = max(0, min(255, int(window_alpha)))
        blend = BlendFunction(0, 0, window_alpha, 1)  # AC_SRC_OVER / AC_SRC_ALPHA
        if not user32.UpdateLayeredWindow(
            window_handle,
            None,
            ctypes.byref(destination),
            ctypes.byref(dimensions),
            self.memory_dc,
            ctypes.byref(source),
            0,
            ctypes.byref(blend),
            2,  # ULW_ALPHA
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
        self.memory_dc = None
        self.bitmap = None
        self.previous_bitmap = None
        self.bits = None
        self.size = None


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


class OverlayApp:
    def __init__(self, config_path: str | Path) -> None:
        self.config_path = Path(config_path).resolve()
        self.config = load_config(self.config_path)
        self.image_modes = discover_image_modes(self.config_path)
        if not self.image_modes:
            self.image_modes = [
                ImageMode(KEYBOARD_MODE_NAME, "keyboard", KEYBOARD_MODE_NAME)
            ]
        self.active_mode_index = 0
        self.selected_character_number = 0
        self.running = True
        self.visible = True
        self.settings_process: subprocess.Popen[Any] | None = None
        self.selected_character_path: str | None = None
        self.selected_character_open_path: str | None = None
        self.last_file_check = 0.0
        self.config_mtime = self._config_mtime()
        self.window_scale = 1.0
        self.last_known_window_position: tuple[int, int] | None = None
        self.pending_position_save_at: float | None = None
        self.applied_window_alpha: int | None = None
        self.screen: pygame.Surface
        self.layered_presenter = LayeredWindowPresenter() if os.name == "nt" else None

        pygame.init()
        icon_path = resolve_asset_path(self.config["icon_path"], self.config_path)
        self._set_window_icon(icon_path)
        self.clock = pygame.time.Clock()
        self._create_display()
        self.renderer = LayerRenderer(self.config, self.config_path)
        self.input_manager = InputManager()
        self.microphone_manager = MicrophoneManager(self.config)
        self.tray_manager = TrayManager(icon_path)
        self._reload_active_mode()
        self.asset_state = self._asset_state()

    @staticmethod
    def _set_window_icon(icon_path: Path) -> None:
        if not icon_path.is_file():
            print(f"[images] 누락된 아이콘: {icon_path}")
            return
        try:
            pygame.display.set_icon(pygame.image.load(str(icon_path)))
        except (OSError, ValueError, pygame.error) as error:
            print(f"[images] 아이콘을 불러올 수 없습니다: {icon_path} ({error})")

    def _is_borderless(self) -> bool:
        return self.config["borderless"] or self.config["transparent_background"]

    def _display_flags(self) -> int:
        flags = pygame.DOUBLEBUF
        flags |= pygame.NOFRAME if self._is_borderless() else pygame.RESIZABLE
        return flags

    def _create_display(self, size: tuple[int, int] | None = None) -> None:
        if self.layered_presenter is not None:
            self.layered_presenter.close()
        self.applied_window_alpha = None
        display_size = size or (
            self.config["window_width"],
            self.config["window_height"],
        )
        self.screen = pygame.display.set_mode(display_size, self._display_flags())
        pygame.display.set_caption(WINDOW_TITLE)
        self._apply_windows_options()
        self._apply_saved_window_position()
        self._remember_window_position()

    def _window_handle(self) -> int | None:
        if os.name != "nt":
            return None
        return pygame.display.get_wm_info().get("window")

    def _apply_windows_options(self) -> None:
        window_handle = self._window_handle()
        if not window_handle:
            return

        user32 = user32_api()
        gwl_exstyle = -20
        ws_ex_layered = 0x00080000
        ws_ex_noactivate = 0x08000000
        ws_ex_transparent = 0x00000020
        lwa_alpha = 0x00000002
        style = user32.GetWindowLongW(window_handle, gwl_exstyle)
        borderless = self._is_borderless()

        if borderless and self.config["window_position_locked"]:
            style |= ws_ex_noactivate | ws_ex_transparent
        else:
            style &= ~(ws_ex_noactivate | ws_ex_transparent)

        if self.config["transparent_background"]:
            # UpdateLayeredWindow cannot follow SetLayeredWindowAttributes until
            # WS_EX_LAYERED has been cleared and enabled again.
            user32.SetWindowLongW(window_handle, gwl_exstyle, style & ~ws_ex_layered)
            style |= ws_ex_layered
            user32.SetWindowLongW(window_handle, gwl_exstyle, style)
        elif borderless or self.config["window_position_locked"]:
            style |= ws_ex_layered
            user32.SetWindowLongW(window_handle, gwl_exstyle, style)
            if user32.SetLayeredWindowAttributes(window_handle, 0, 255, lwa_alpha):
                self.applied_window_alpha = 255
        else:
            style &= ~ws_ex_layered
            user32.SetWindowLongW(window_handle, gwl_exstyle, style)
            self.applied_window_alpha = None

        self._set_topmost(self.config["always_on_top"])

    def _window_rect(self) -> wintypes.RECT | None:
        window_handle = self._window_handle()
        if not window_handle:
            return None
        rectangle = wintypes.RECT()
        if not user32_api().GetWindowRect(window_handle, ctypes.byref(rectangle)):
            return None
        return rectangle

    def _window_alpha(self) -> int:
        if os.name != "nt" or not self.config["window_position_locked"]:
            return 255
        rectangle = self._window_rect()
        if rectangle is None:
            return 255
        cursor = wintypes.POINT()
        if not user32_api().GetCursorPos(ctypes.byref(cursor)):
            return 255
        if (
            rectangle.left <= cursor.x < rectangle.right
            and rectangle.top <= cursor.y < rectangle.bottom
        ):
            return LOCKED_HOVER_ALPHA
        return 255

    def _apply_uniform_window_alpha(self, window_handle: int, alpha: int) -> None:
        if self.config["transparent_background"]:
            return
        if not (self._is_borderless() or self.config["window_position_locked"]):
            return
        alpha = max(0, min(255, int(alpha)))
        if self.applied_window_alpha == alpha:
            return
        if user32_api().SetLayeredWindowAttributes(
            window_handle, 0, alpha, 0x00000002
        ):
            self.applied_window_alpha = alpha

    def _move_window(self, x: int, y: int) -> None:
        window_handle = self._window_handle()
        if not window_handle:
            return
        flags = 0x0001 | 0x0004 | 0x0010  # NOSIZE | NOZORDER | NOACTIVATE
        user32_api().SetWindowPos(window_handle, wintypes.HWND(0), x, y, 0, 0, flags)

    def _remember_window_position(self) -> None:
        rectangle = self._window_rect()
        if rectangle is not None:
            self.last_known_window_position = (rectangle.left, rectangle.top)

    @staticmethod
    def _clamp(value: int, minimum: int, maximum: int) -> int:
        return minimum if maximum < minimum else max(minimum, min(maximum, value))

    def _visible_window_position(
        self, x: int, y: int, width: int, height: int
    ) -> tuple[int, int]:
        if os.name != "nt":
            return x, y
        proposed = wintypes.RECT(x, y, x + width, y + height)
        user32 = user32_api()
        monitor = user32.MonitorFromRect(ctypes.byref(proposed), 2)
        if not monitor:
            return x, y
        information = MonitorInfo()
        information.cbSize = ctypes.sizeof(MonitorInfo)
        if not user32.GetMonitorInfoW(monitor, ctypes.byref(information)):
            return x, y
        work = information.rcWork
        return (
            self._clamp(x, work.left, work.right - width),
            self._clamp(y, work.top, work.bottom - height),
        )

    def _apply_saved_window_position(self) -> None:
        configured_x = self.config.get("window_x")
        configured_y = self.config.get("window_y")
        if configured_x is None and configured_y is None:
            return
        rectangle = self._window_rect()
        if rectangle is None:
            return
        requested_x = rectangle.left if configured_x is None else configured_x
        requested_y = rectangle.top if configured_y is None else configured_y
        target_x, target_y = self._visible_window_position(
            requested_x,
            requested_y,
            rectangle.right - rectangle.left,
            rectangle.bottom - rectangle.top,
        )
        self.config["window_x"] = target_x
        self.config["window_y"] = target_y
        self.last_known_window_position = (target_x, target_y)
        self._move_window(target_x, target_y)

    def _save_runtime_config(self, fields: tuple[str, ...]) -> None:
        runtime_state = {name: self.config[name] for name in fields}

        def merge_runtime_state(latest_config: dict[str, Any]) -> dict[str, Any]:
            latest_config.update(runtime_state)
            return latest_config

        try:
            update_config(merge_runtime_state, self.config_path)
        except (OSError, ValueError) as error:
            print(f"[config] 창 상태를 저장할 수 없습니다: {error}")

    def _start_window_drag(self) -> None:
        if self.config["window_position_locked"]:
            return
        window_handle = self._window_handle()
        if not window_handle:
            return
        user32 = user32_api()
        user32.ReleaseCapture()
        user32.SendMessageW(window_handle, 0x00A1, 0x0002, 0)  # WM_NCLBUTTONDOWN, HTCAPTION
        rectangle = self._window_rect()
        if rectangle is not None:
            self.config["window_x"] = rectangle.left
            self.config["window_y"] = rectangle.top
            self.last_known_window_position = (rectangle.left, rectangle.top)
            self.pending_position_save_at = None
            self._save_runtime_config(("window_x", "window_y"))
            print(f"[window] 위치 저장: {rectangle.left}, {rectangle.top}")

    def _set_topmost(self, enabled: bool) -> None:
        window_handle = self._window_handle()
        if not window_handle:
            return
        hwnd_insert_after = wintypes.HWND(-1 if enabled else -2)
        flags = 0x0001 | 0x0002 | 0x0010  # NOSIZE | NOMOVE | NOACTIVATE
        user32_api().SetWindowPos(
            window_handle, hwnd_insert_after, 0, 0, 0, 0, flags
        )

    def _toggle_visibility(self) -> None:
        self.visible = not self.visible
        window_handle = self._window_handle()
        if window_handle:
            show_command = 8 if self.visible else 0  # SW_SHOWNA / SW_HIDE
            user32_api().ShowWindow(window_handle, show_command)
            if self.visible:
                self._set_topmost(self.config["always_on_top"])
        elif not self.visible:
            pygame.display.iconify()
        self._sync_tray_state()

    def _toggle_topmost(self) -> None:
        self.config["always_on_top"] = not self.config["always_on_top"]
        self._set_topmost(self.config["always_on_top"])
        self._save_runtime_config(("always_on_top",))
        state = "ON" if self.config["always_on_top"] else "OFF"
        print(f"[window] Always On Top: {state}")
        self._sync_tray_state()

    def _toggle_position_lock(self) -> None:
        self.config["window_position_locked"] = not self.config["window_position_locked"]
        self._remember_window_position()
        self._apply_windows_options()
        self._save_runtime_config(("window_position_locked",))
        state = "ON" if self.config["window_position_locked"] else "OFF"
        print(f"[window] 위치 잠금: {state}")
        self._sync_tray_state()

    def _active_mode(self) -> ImageMode:
        return self.image_modes[self.active_mode_index]

    def _keyboard_mode(self) -> ImageMode | None:
        return next(
            (mode for mode in self.image_modes if mode.kind == "keyboard"),
            None,
        )

    def _character_paths(self, number: int) -> tuple[str, str]:
        if number == 0:
            return (
                self.config["images"]["character"]["path"],
                self.config["microphone_open_image"],
            )
        keyboard_mode = self._keyboard_mode()
        directory = (
            keyboard_mode.directory_name
            if keyboard_mode is not None
            else KEYBOARD_MODE_NAME
        )
        prefix = (Path("image") / directory).as_posix()
        return (
            f"{prefix}/character{number}.png",
            f"{prefix}/character{number}_open.png",
        )

    def _reload_active_mode(self) -> None:
        mode = self._active_mode()
        avatar_paths = mode.expression_paths
        if mode.kind == "keyboard":
            path_value, open_path_value = self._character_paths(
                self.selected_character_number
            )
            self.selected_character_path = (
                None if self.selected_character_number == 0 else path_value
            )
            self.selected_character_open_path = (
                None if self.selected_character_number == 0 else open_path_value
            )
        else:
            self.selected_character_path = None
            self.selected_character_open_path = None
        self.renderer.reload_config(
            self.config,
            selected_character_path=self.selected_character_path,
            selected_character_open_path=self.selected_character_open_path,
            avatar_expression_paths=avatar_paths,
        )
        self._sync_microphone_character()

    def _switch_mode(self, offset: int) -> None:
        if len(self.image_modes) < 2:
            return
        self.active_mode_index = (self.active_mode_index + offset) % len(
            self.image_modes
        )
        self._reload_active_mode()
        self.asset_state = self._asset_state()
        print(f"[images] 모드 변경: {self._active_mode().name}")

    def _select_character(self, number: int) -> None:
        if self._active_mode().kind != "keyboard" or number not in range(10):
            return
        path_value, open_path_value = self._character_paths(number)
        if not self.renderer.select_character(path_value, open_path_value):
            print(f"[images] 캐릭터를 변경할 수 없습니다: {path_value}")
            return
        self.selected_character_path = None if number == 0 else path_value
        self.selected_character_open_path = (
            None if number == 0 else open_path_value
        )
        self.selected_character_number = number
        self.asset_state = self._asset_state()
        self._sync_microphone_character()
        label = "기본" if number == 0 else str(number)
        print(f"[images] 캐릭터 변경: {label}")

    def _sync_microphone_character(self) -> None:
        # The app decides expression priority; the renderer only swaps cached images.
        self.renderer.set_microphone_level(
            self.microphone_manager.expression_level()
        )

    def _resize_window(self, scale: float) -> None:
        self.window_scale = scale
        size = (
            max(160, math.floor(self.config["window_width"] * scale + 0.5)),
            max(120, math.floor(self.config["window_height"] * scale + 0.5)),
        )
        self._create_display(size)
        self._sync_tray_state()

    def _show_context_menu(self) -> None:
        if self.config["window_position_locked"]:
            return
        window_handle = self._window_handle()
        if not window_handle:
            return
        user32 = user32_api()
        menu = user32.CreatePopupMenu()
        size_menu = user32.CreatePopupMenu()
        if not menu or not size_menu:
            if menu:
                user32.DestroyMenu(menu)
            if size_menu:
                user32.DestroyMenu(size_menu)
            return

        mf_string = 0x0000
        mf_checked = 0x0008
        mf_popup = 0x0010
        mf_separator = 0x0800
        mf_radiocheck = 0x0200
        scale_commands = (
            (CONTEXT_SCALE_125, WINDOW_SCALES[0], "125%"),
            (CONTEXT_SCALE_150, WINDOW_SCALES[1], "150%"),
        )
        size_menu_attached = False

        try:
            user32.AppendMenuW(menu, mf_string, CONTEXT_SETTINGS, "설정 열기")
            user32.AppendMenuW(menu, mf_string, CONTEXT_HIDE, "오버레이 숨기기")
            for command, scale, label in scale_commands:
                flags = mf_string | mf_radiocheck
                if abs(self.window_scale - scale) < 0.01:
                    flags |= mf_checked
                user32.AppendMenuW(size_menu, flags, command, label)
            size_menu_handle = ctypes.cast(size_menu, ctypes.c_void_p).value
            if size_menu_handle is None or not user32.AppendMenuW(
                menu, mf_popup, size_menu_handle, "크기"
            ):
                return
            size_menu_attached = True
            user32.AppendMenuW(menu, mf_separator, 0, None)
            topmost_flags = mf_string | (mf_checked if self.config["always_on_top"] else 0)
            user32.AppendMenuW(menu, topmost_flags, CONTEXT_TOPMOST, "Always On Top")
            lock_flags = mf_string | (
                mf_checked if self.config["window_position_locked"] else 0
            )
            user32.AppendMenuW(menu, lock_flags, CONTEXT_POSITION_LOCK, "위치 잠금")
            user32.AppendMenuW(menu, mf_separator, 0, None)
            user32.AppendMenuW(menu, mf_string, CONTEXT_QUIT, "프로그램 종료")

            cursor = wintypes.POINT()
            if not user32.GetCursorPos(ctypes.byref(cursor)):
                return
            user32.SetForegroundWindow(window_handle)
            command = user32.TrackPopupMenu(
                menu,
                0x0100 | 0x0002,  # TPM_RETURNCMD | TPM_RIGHTBUTTON
                cursor.x,
                cursor.y,
                0,
                window_handle,
                None,
            )
            user32.PostMessageW(window_handle, 0, 0, 0)
        finally:
            user32.DestroyMenu(menu)
            if not size_menu_attached:
                user32.DestroyMenu(size_menu)

        actions = {
            CONTEXT_SETTINGS: "open_settings",
            CONTEXT_HIDE: "toggle_visibility",
            CONTEXT_SCALE_125: f"resize:{WINDOW_SCALES[0]}",
            CONTEXT_SCALE_150: f"resize:{WINDOW_SCALES[1]}",
            CONTEXT_TOPMOST: "toggle_topmost",
            CONTEXT_POSITION_LOCK: "toggle_position_lock",
            CONTEXT_QUIT: "quit",
        }
        action = actions.get(command)
        if action is not None:
            self._handle_action(action)

    def _sync_tray_state(self) -> None:
        if not hasattr(self, "tray_manager"):
            return
        self.tray_manager.update_state(
            visible=self.visible,
            topmost=self.config["always_on_top"],
            position_locked=self.config["window_position_locked"],
            window_scale=self.window_scale,
        )

    def _launch_settings(self) -> None:
        if self.settings_process is not None and self.settings_process.poll() is None:
            return
        if getattr(sys, "frozen", False):
            command = [sys.executable, "--settings", "--config", str(self.config_path)]
        else:
            command = [
                sys.executable,
                str(Path(__file__).resolve()),
                "--settings",
                "--config",
                str(self.config_path),
            ]
        try:
            environment = os.environ.copy()
            if getattr(sys, "frozen", False):
                environment["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
            self.settings_process = subprocess.Popen(command, env=environment)
        except OSError as error:
            print(f"[settings] 설정 창을 열 수 없습니다: {error}")

    def _config_mtime(self) -> int | None:
        try:
            return self.config_path.stat().st_mtime_ns
        except OSError:
            return None

    def _asset_state(self) -> dict[str, tuple[int, int, int] | None]:
        path_values = [self.config.get("icon_path", "")]
        path_values.extend(
            spec.get("path", "") for spec in self.config["images"].values()
        )
        if self.selected_character_path is not None:
            path_values.append(self.selected_character_path)
        if self.selected_character_open_path is not None:
            path_values.append(self.selected_character_open_path)
        path_values.append(self.config["microphone_open_image"])
        expression_paths = self._active_mode().expression_paths
        if expression_paths is not None:
            path_values.extend(expression_paths)
        state: dict[str, tuple[int, int, int] | None] = {}
        for path_value in path_values:
            if not path_value:
                continue
            path = resolve_asset_path(path_value, self.config_path)
            try:
                information = path.stat()
                state[str(path)] = (
                    information.st_mtime_ns,
                    information.st_ctime_ns,
                    information.st_size,
                )
            except OSError:
                state[str(path)] = None
        return state

    def _reload_config_if_changed(self) -> None:
        now = time.monotonic()
        if now - self.last_file_check < 0.5:
            return
        self.last_file_check = now
        config_reloaded = False
        modified = self._config_mtime()
        if modified is not None and modified != self.config_mtime:
            try:
                reloaded_config = load_config_strict(self.config_path)
            except (OSError, ValueError) as error:
                print(f"[config] 변경된 설정을 아직 읽을 수 없습니다. 다시 시도합니다: {error}")
            else:
                old_config = self.config
                self.config = reloaded_config
                self.config_mtime = modified
                config_reloaded = True
                recreate_window = any(
                    old_config[name] != self.config[name]
                    for name in (
                        "window_width",
                        "window_height",
                        "borderless",
                        "transparent_background",
                    )
                )
                if recreate_window:
                    self.window_scale = 1.0
                    self._create_display()
                else:
                    self._apply_windows_options()
                    if any(
                        old_config[name] != self.config[name]
                        for name in ("window_x", "window_y")
                    ):
                        self._apply_saved_window_position()

        asset_state = self._asset_state()
        assets_changed = asset_state != self.asset_state
        if not config_reloaded and not assets_changed:
            return

        if config_reloaded:
            self.microphone_manager.reconfigure(self.config)
        self._reload_active_mode()
        icon_path = resolve_asset_path(self.config["icon_path"], self.config_path)
        self._set_window_icon(icon_path)
        self.tray_manager.update_icon(icon_path)
        self.asset_state = asset_state
        self._sync_tray_state()
        if config_reloaded:
            print("[config] 변경된 설정을 적용했습니다.")
        elif assets_changed:
            print("[images] 변경된 이미지 파일을 적용했습니다.")

    def _handle_window_events(self) -> None:
        window_moved_event = getattr(pygame, "WINDOWMOVED", -1)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._start_window_drag()
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
                self._show_context_menu()
            elif event.type == window_moved_event:
                rectangle = self._window_rect()
                moved_position = (
                    (rectangle.left, rectangle.top)
                    if rectangle is not None
                    else (int(event.x), int(event.y))
                )
                if self.config["window_position_locked"]:
                    if (
                        self.last_known_window_position is not None
                        and moved_position != self.last_known_window_position
                    ):
                        self._move_window(*self.last_known_window_position)
                else:
                    self.last_known_window_position = moved_position
                    self.config["window_x"], self.config["window_y"] = moved_position
                    self.pending_position_save_at = time.monotonic() + 0.3
            elif event.type == pygame.VIDEORESIZE and not self._is_borderless():
                width = max(160, event.w)
                height = max(120, event.h)
                self.window_scale = min(
                    width / self.config["window_width"],
                    height / self.config["window_height"],
                )
                self._create_display((width, height))
                self._sync_tray_state()

    def _save_pending_window_position(self) -> None:
        if (
            self.pending_position_save_at is not None
            and time.monotonic() >= self.pending_position_save_at
        ):
            self.pending_position_save_at = None
            self._save_runtime_config(("window_x", "window_y"))

    def _handle_shortcuts(self) -> None:
        actions = self.input_manager.consume_actions()
        actions.extend(self.tray_manager.consume_actions())
        for action in actions:
            self._handle_action(action)

    def _handle_action(self, action: str) -> None:
        if action == "toggle_visibility":
            self._toggle_visibility()
        elif action == "toggle_topmost":
            self._toggle_topmost()
        elif action == "open_settings":
            self._launch_settings()
        elif action == "toggle_position_lock":
            self._toggle_position_lock()
        elif action.startswith("select_character:"):
            self._select_character(int(action.partition(":")[2]))
        elif action == "next_mode":
            self._switch_mode(1)
        elif action == "previous_mode":
            self._switch_mode(-1)
        elif action.startswith("resize:"):
            self._resize_window(float(action.partition(":")[2]))
        elif action == "quit":
            self.running = False

    def _present(self, canvas: pygame.Surface) -> None:
        screen_width, screen_height = self.screen.get_size()
        canvas_width, canvas_height = canvas.get_size()
        scale = min(screen_width / canvas_width, screen_height / canvas_height)
        output_size = (
            max(1, round(canvas_width * scale)),
            max(1, round(canvas_height * scale)),
        )
        if self.config.get("transparent_background"):
            output_size = (screen_width, screen_height)
        if output_size == canvas.get_size():
            output = canvas
        else:
            output = pygame.transform.smoothscale(canvas, output_size)
        destination = (
            (screen_width - output_size[0]) // 2,
            (screen_height - output_size[1]) // 2,
        )
        window_handle = self._window_handle()
        window_alpha = self._window_alpha()
        if (
            self.config["transparent_background"]
            and window_handle is not None
            and self.layered_presenter is not None
        ):
            frame = pygame.Surface(
                (screen_width, screen_height), pygame.SRCALPHA, 32
            )
            frame.blit(output, destination)
            self.layered_presenter.present(window_handle, frame, window_alpha)
            return

        if window_handle is not None:
            self._apply_uniform_window_alpha(window_handle, window_alpha)
        self.screen.fill(self.config["background_color"])
        self.screen.blit(output, destination)
        pygame.display.flip()

    @staticmethod
    def _cursor_ratio(
        mouse_position: tuple[float, float] | None,
    ) -> tuple[float, float] | None:
        if mouse_position is None:
            return None
        mouse_x, mouse_y = mouse_position

        if os.name == "nt":
            point = wintypes.POINT(round(mouse_x), round(mouse_y))
            user32 = user32_api()
            monitor = user32.MonitorFromPoint(point, 2)
            if monitor:
                information = MonitorInfo()
                information.cbSize = ctypes.sizeof(MonitorInfo)
                if user32.GetMonitorInfoW(monitor, ctypes.byref(information)):
                    bounds = information.rcMonitor
                    width = max(1, bounds.right - bounds.left - 1)
                    height = max(1, bounds.bottom - bounds.top - 1)
                    return (
                        max(0.0, min(1.0, (mouse_x - bounds.left) / width)),
                        max(0.0, min(1.0, (mouse_y - bounds.top) / height)),
                    )

        desktop_sizes = pygame.display.get_desktop_sizes()
        if not desktop_sizes:
            return None
        width, height = desktop_sizes[0]
        return (
            max(0.0, min(1.0, mouse_x / max(1, width - 1))),
            max(0.0, min(1.0, mouse_y / max(1, height - 1))),
        )

    def run(self) -> int:
        try:
            self.input_manager.start()
        except Exception as error:
            print(f"[input] 전역 입력 리스너를 시작할 수 없습니다: {error}")
        self.microphone_manager.start()
        self._sync_tray_state()
        self.tray_manager.start()

        try:
            while self.running:
                delta_time = min(self.clock.tick(self.config["fps"]) / 1000.0, 0.1)
                self._handle_window_events()
                self._handle_shortcuts()
                self._save_pending_window_position()
                self._reload_config_if_changed()
                self._sync_microphone_character()
                snapshot = self.input_manager.snapshot()
                if self.visible:
                    canvas = self.renderer.render(
                        snapshot,
                        delta_time,
                        self._cursor_ratio(snapshot.mouse_position),
                    )
                    self._present(canvas)
        finally:
            self.tray_manager.stop()
            self.microphone_manager.stop()
            self.input_manager.stop()
            if self.layered_presenter is not None:
                self.layered_presenter.close()
            pygame.quit()
        return 0


def parse_arguments(arguments: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=WINDOW_TITLE)
    parser.add_argument("--settings", action="store_true", help="설정 창 열기")
    parser.add_argument("--config", type=Path, default=default_config_path())
    return parser.parse_args(arguments)


def main(arguments: list[str] | None = None) -> int:
    options = parse_arguments(arguments)
    enable_dpi_awareness()
    if options.settings:
        from settings import run_settings

        run_settings(options.config)
        return 0
    return OverlayApp(options.config).run()


if __name__ == "__main__":
    raise SystemExit(main())
