from __future__ import annotations

from ctypes import wintypes
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from iram_tap.app import OverlayApp
from iram_tap.config.repository import normalise_config
from iram_tap.platform.windows import WindowController


class WindowDragTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = OverlayApp(Path(__file__).resolve().parents[2] / "config.json",
                              config=normalise_config({}))
        self.app._window_handle = Mock(return_value=123)
        self.app._window_rect = Mock(return_value=wintypes.RECT(100, 20, 400, 460))
        self.app._move_window = Mock()
        self.app._save_runtime_config = Mock()
        self.api = Mock()
        self.api.GetCapture.return_value = 123
        self.api.GetAsyncKeyState.return_value = 0x8000
        self.cursor = (150, 200)

        def cursor_position(pointer):
            pointer._obj.x, pointer._obj.y = self.cursor
            return True

        self.api.GetCursorPos.side_effect = cursor_position
        patcher = patch("iram_tap.app.user32_api", return_value=self.api)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_drag_crosses_top_and_left_without_native_move_loop(self) -> None:
        self.app._start_window_drag()
        self.cursor = (-50, 20)
        self.app._update_window_drag()
        self.app._move_window.assert_called_once_with(-100, -160)
        self.api.SendMessageW.assert_not_called()
        self.api.SetCapture.assert_called_once_with(123)

    def test_mouse_release_saves_negative_position_once(self) -> None:
        self.app._start_window_drag()
        self.app._window_rect.return_value = wintypes.RECT(100, -140, 400, 300)
        self.api.GetAsyncKeyState.return_value = 0
        self.app._update_window_drag()
        self.app._update_window_drag()
        self.assertIsNone(self.app.drag_origin)
        self.assertEqual(self.app.config["window_y"], -140)
        self.api.ReleaseCapture.assert_called_once()
        self.app._save_runtime_config.assert_called_once_with(("window_x", "window_y"))

    def test_capture_loss_does_not_release_another_windows_capture(self) -> None:
        self.app._start_window_drag()
        self.api.GetCapture.return_value = 456
        self.app._update_window_drag()
        self.assertIsNone(self.app.drag_origin)
        self.app._move_window.assert_not_called()
        self.api.ReleaseCapture.assert_not_called()

    def test_focus_loss_stops_drag(self) -> None:
        self.app._start_window_drag()
        with patch("pygame.event.get", return_value=[
            pygame.event.Event(pygame.WINDOWFOCUSLOST)
        ]):
            self.app._handle_window_events()
        self.assertIsNone(self.app.drag_origin)
        self.app._move_window.assert_not_called()

    def test_lock_prevents_start_and_stops_existing_drag(self) -> None:
        self.app.config["window_position_locked"] = True
        self.app._start_window_drag()
        self.api.SetCapture.assert_not_called()
        self.app.config["window_position_locked"] = False
        self.app._start_window_drag()
        self.app.config["window_position_locked"] = True
        self.app._update_window_drag()
        self.assertIsNone(self.app.drag_origin)
        self.app._move_window.assert_not_called()

    def test_framed_window_retains_native_drag(self) -> None:
        self.app.config.update(borderless=False, transparent_background=False)
        self.app._start_window_drag()
        self.api.SendMessageW.assert_called_once_with(123, 0x00A1, 0x0002, 0)
        self.assertIsNone(self.app.drag_origin)


class SavedWindowPositionTests(unittest.TestCase):
    def test_partial_positions_survive_and_disconnected_monitor_recovers(self) -> None:
        api = Mock()

        def monitor_info(handle, pointer):
            pointer._obj.rcWork = wintypes.RECT(0, 0, 1920, 1040)
            return True

        api.GetMonitorInfoW.side_effect = monitor_info
        with patch("iram_tap.platform.windows.os.name", "nt"), patch(
            "iram_tap.platform.windows.user32_api", return_value=api
        ):
            for original, expected in [
                ((100, -140), (100, -140)),
                ((-100, 20), (-100, 20)),
                ((1800, 900), (1800, 900)),
                ((3000, 20), (1620, 20)),
                ((100, -500), (100, 0)),
            ]:
                with self.subTest(original=original):
                    self.assertEqual(WindowController.visible_position(
                        *original, 300, 440
                    ), expected)

    def test_restore_uses_character_area_at_each_scale(self) -> None:
        app = OverlayApp(Path(__file__).resolve().parents[2] / "config.json",
                         config=normalise_config({}))
        for scale in (1, 2):
            with self.subTest(scale=scale):
                app.window.visible_position = Mock(return_value=(100, 0))
                self.assertEqual(app._visible_window_position(
                    100, -140 * scale, 300 * scale, 440 * scale
                ), (100, -140 * scale))
                app.window.visible_position.assert_called_once_with(
                    100, 0, 300 * scale, 300 * scale
                )


if __name__ == "__main__":
    unittest.main()
