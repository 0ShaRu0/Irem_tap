from __future__ import annotations

import ctypes
from ctypes import wintypes
import math
import os
from pathlib import Path
import tempfile
from typing import Any
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
from PIL import Image

from config_manager import DEFAULT_CONFIG, KEYS, WINDOW_SCALES, normalise_config
from input_manager import InputManager, InputSnapshot
from image_geometry import ImageTransform, scaled_image_size
from main import LOCKED_HOVER_ALPHA, LayeredWindowPresenter, OverlayApp
from microphone_manager import DEFAULT_DEVICE_LABEL
from renderer import LayerRenderer
from settings import SettingsEditor
from tray_manager import TrayManager


PROJECT_DIR = Path(__file__).resolve().parents[1]


class ConfigTests(unittest.TestCase):
    def test_motion_and_glow_values_are_clamped(self) -> None:
        config = normalise_config(
            {
                "right_hand_speed": 99,
                "right_hand_range": [-5, 18],
                "key_glow_alpha": 999,
                "key_glows": {"Q": {"position": [2, 3], "size": [0, -1]}},
                "mouse_glow_color": [-1, 999, "bad"],
                "mouse_glow_alpha": -5,
                "mouse_glows": {
                    "left": {"position": [4, 5], "size": [0, -1]}
                },
                "microphone_threshold": 99,
                "microphone_release_delay": -5,
            }
        )

        self.assertEqual(config["right_hand_speed"], 1.0)
        self.assertEqual(config["right_hand_range"], [0, 18.0])
        self.assertEqual(config["key_glow_alpha"], 255)
        self.assertEqual(config["key_glows"]["Q"]["size"], [1, 1])
        self.assertEqual(config["mouse_glow_color"], [0, 255, 0])
        self.assertEqual(config["mouse_glow_alpha"], 0)
        self.assertEqual(config["mouse_glows"]["left"]["size"], [1, 1])
        self.assertEqual(config["microphone_threshold"], 1.0)
        self.assertEqual(config["microphone_release_delay"], 0.0)

    def test_default_layout_uses_current_image_schema(self) -> None:
        config = normalise_config({})

        self.assertEqual((config["window_width"], config["window_height"]), (300, 300))
        self.assertEqual(config["icon_path"], "image/icon.png")
        self.assertEqual(config["images"]["character"]["size"], [300, 300])
        self.assertEqual(config["images"]["desk_keyboard"]["size"], [300, 300])
        self.assertEqual(config["images"]["right_hand_mouse"]["position"], [0, 0])
        self.assertEqual(config["images"]["right_hand_mouse"]["size"], [300, 300])
        self.assertEqual(config["images"]["left_hand_idle"]["position"], [0, 0])
        self.assertEqual(config["key_glows"]["SPACE"]["position"], [183, 215])
        self.assertEqual(config["mouse_glows"]["left"]["position"], [42.0, 180.0])
        self.assertEqual(
            config["mouse_glows"]["right"]["position"], [48.9, 182.1]
        )
        self.assertTrue(config["microphone_enabled"])
        self.assertEqual(config["microphone_device"], "")
        self.assertEqual(config["microphone_threshold"], 0.02)
        self.assertEqual(config["microphone_release_delay"], 0.18)
        self.assertEqual(
            config["microphone_open_image"], "image/character_open.png"
        )
        self.assertEqual(tuple(config["images"]), tuple(DEFAULT_CONFIG["images"]))

    def test_only_larger_scale_options_are_available(self) -> None:
        self.assertEqual(WINDOW_SCALES, (1.25, 1.5))
        self.assertEqual(DEFAULT_CONFIG["window_width"], 300)

    def test_unknown_fields_are_ignored(self) -> None:
        config = normalise_config(
            {"unused": True, "images": {"unused": {"path": "unused.png"}}}
        )

        self.assertNotIn("unused", config)
        self.assertNotIn("unused", config["images"])

    def test_glow_positions_match_keyboard_label_order(self) -> None:
        glows = normalise_config({})["key_glows"]

        self.assertLess(glows["R"]["position"][0], glows["E"]["position"][0])
        self.assertLess(glows["E"]["position"][0], glows["W"]["position"][0])
        self.assertLess(glows["W"]["position"][0], glows["Q"]["position"][0])
        self.assertLess(glows["F"]["position"][0], glows["D"]["position"][0])
        self.assertLess(glows["D"]["position"][0], glows["S"]["position"][0])
        self.assertLess(glows["S"]["position"][0], glows["A"]["position"][0])
        self.assertLess(glows["SPACE"]["position"][1], glows["F"]["position"][1])
        self.assertGreater(
            glows["SPACE"]["size"][0],
            max(glows[key]["size"][0] for key in KEYS if key != "SPACE"),
        )


class SettingsEditorTests(unittest.TestCase):
    def test_glow_drag_uses_image_offset_and_nonuniform_scale(self) -> None:
        for mode, image_name, expected_position in (
            ("glow", "desk_keyboard", [229.0, 262.0]),
            ("mouse_glow", "right_hand_mouse", [66.0, 160.0]),
        ):
            with self.subTest(mode=mode):
                editor = object.__new__(SettingsEditor)
                editor.config = normalise_config({
                    "images": {image_name: {"position": [10, 20]}}
                })
                editor.selected_key = "Q"
                editor.selected_mouse_button = "left"
                for prefix in ("glow", "mouse_glow"):
                    for field in ("x", "y", "width", "height"):
                        setattr(editor, f"{prefix}_{field}", Mock())
                editor._preview_image_size = Mock(return_value=(150, 75))
                editor._preview_mode = Mock(return_value=mode)
                editor._redraw_preview = Mock()
                center_x, center_y, *_ = editor._glow_transform(mode).glow_geometry(
                    editor._selected_glow(mode)
                )
                editor._canvas_to_logical = Mock(side_effect=[
                    (center_x + 2, center_y + 3),
                    (center_x + 14, center_y - 2),
                ])

                editor._start_drag(Mock(x=0, y=0))
                editor._drag_preview(Mock(x=0, y=0))

                self.assertEqual(editor._selected_glow(mode)["position"], expected_position)
                self.assertEqual(editor.config["images"][image_name]["position"], [10, 20])
                self.assertEqual(
                    editor.config["mouse_glows"]["right"],
                    DEFAULT_CONFIG["mouse_glows"]["right"],
                )

    def test_glow_preview_tracks_resized_keyboard(self) -> None:
        editor = object.__new__(SettingsEditor)
        editor.config = normalise_config(
            {
                "images": {
                    "desk_keyboard": {
                        "position": [10, 20],
                        "size": [150, 150],
                    }
                }
            }
        )
        editor._preview_image_size = Mock(return_value=(150, 150))

        geometry = editor._scaled_glow_geometry(editor.config["key_glows"]["F"])

        self.assertEqual(geometry, (76.0, 128.0, 14.0, 8.0))

    def test_mouse_glow_preview_tracks_resized_right_hand(self) -> None:
        editor = object.__new__(SettingsEditor)
        editor.config = normalise_config(
            {
                "images": {
                    "right_hand_mouse": {
                        "position": [10, 20],
                        "size": [150, 150],
                    }
                }
            }
        )
        editor._preview_image_size = Mock(return_value=(150, 150))

        geometry = editor._scaled_mouse_glow_geometry(
            editor.config["mouse_glows"]["left"]
        )

        self.assertEqual(geometry, (31.0, 110.0, 3.3, 2.7))

    def test_clicking_selected_hand_starts_image_drag(self) -> None:
        editor = object.__new__(SettingsEditor)
        editor.config = normalise_config({})
        editor.active_image_name = "right_hand_mouse"
        editor.drag_offset = None
        editor.drag_target = None
        editor._canvas_to_logical = Mock(return_value=(20.0, 30.0))
        editor._preview_mode = Mock(return_value="image")
        editor._preview_image_size = Mock(return_value=(55, 73))

        editor._start_drag(Mock(x=0, y=0))

        self.assertEqual(editor.drag_target, "right_hand_mouse")
        self.assertEqual(editor.drag_offset, (20.0, 30.0))

    def test_dragging_idle_hand_does_not_move_pressed_hand(self) -> None:
        editor = object.__new__(SettingsEditor)
        editor.config = normalise_config({})
        editor.drag_offset = (5.0, 7.0)
        editor.drag_target = "left_hand_idle"
        editor.image_x = Mock()
        editor.image_y = Mock()
        editor._canvas_to_logical = Mock(return_value=(212.3, 90.7))
        editor._redraw_preview = Mock()
        pressed_position = editor.config["images"]["left_hand_pressed"][
            "position"
        ].copy()

        editor._drag_preview(Mock(x=0, y=0))

        self.assertEqual(
            editor.config["images"]["left_hand_idle"]["position"],
            [207.3, 83.7],
        )
        self.assertEqual(
            editor.config["images"]["left_hand_pressed"]["position"],
            pressed_position,
        )
        editor.image_x.set.assert_called_once_with("207.3")
        editor.image_y.set.assert_called_once_with("83.7")
        editor._redraw_preview.assert_called_once_with()

    def test_dragging_mouse_glow_updates_selected_button_only(self) -> None:
        editor = object.__new__(SettingsEditor)
        editor.config = normalise_config({})
        editor.selected_mouse_button = "left"
        editor.drag_offset = (5.0, 7.0)
        editor.drag_target = "mouse_glow"
        editor.mouse_glow_x = Mock()
        editor.mouse_glow_y = Mock()
        editor.mouse_glow_width = Mock()
        editor.mouse_glow_height = Mock()
        editor._canvas_to_logical = Mock(return_value=(60.0, 80.0))
        editor._preview_image_size = Mock(return_value=(150, 150))
        editor._redraw_preview = Mock()
        right_position = editor.config["mouse_glows"]["right"]["position"].copy()

        editor._drag_preview(Mock(x=0, y=0))

        self.assertEqual(
            editor.config["mouse_glows"]["left"]["position"], [110.0, 146.0]
        )
        self.assertEqual(
            editor.config["mouse_glows"]["right"]["position"], right_position
        )
        editor.mouse_glow_x.set.assert_called_once_with("110")
        editor.mouse_glow_y.set.assert_called_once_with("146")
        editor._redraw_preview.assert_called_once_with()

    def test_collects_microphone_settings_in_runtime_units(self) -> None:
        editor = object.__new__(SettingsEditor)
        editor.config = normalise_config({})
        editor.microphone_enabled = Mock()
        editor.microphone_enabled.get.return_value = True
        editor.microphone_device = Mock()
        editor.microphone_device.get.return_value = DEFAULT_DEVICE_LABEL
        editor.microphone_threshold = Mock()
        editor.microphone_threshold.get.return_value = "3.5"
        editor.microphone_release_delay = Mock()
        editor.microphone_release_delay.get.return_value = "240"
        editor.microphone_open_image = Mock()
        editor.microphone_open_image.get.return_value = " image/custom-open.png "

        editor._collect_microphone_fields()

        self.assertTrue(editor.config["microphone_enabled"])
        self.assertEqual(editor.config["microphone_device"], "")
        self.assertEqual(editor.config["microphone_threshold"], 0.035)
        self.assertEqual(editor.config["microphone_release_delay"], 0.24)
        self.assertEqual(
            editor.config["microphone_open_image"], "image/custom-open.png"
        )


class ImageGeometryTests(unittest.TestCase):
    def test_reference_coordinates_round_trip_with_offset_and_nonuniform_scale(self) -> None:
        transform = ImageTransform((-15, 20), (150, 600), (300, 300))
        self.assertEqual(transform.to_canvas(42, 180), (6, 380))
        self.assertEqual(transform.to_image(6, 380), (42, 180))
        self.assertEqual(
            transform.glow_geometry({"position": [42, 180], "size": [10, 6]}),
            (6, 380, 5, 12),
        )

    def test_image_sizing_handles_aspect_ratio_and_automatic_dimensions(self) -> None:
        for size, keep_aspect, expected in (
            ([0, 0], True, (400, 200)),
            ([150, 150], True, (150, 75)),
            ([0, 100], True, (200, 100)),
            ([100, 0], True, (100, 50)),
            ([150, 150], False, (150, 150)),
            ([0, 100], False, (400, 100)),
        ):
            with self.subTest(size=size, keep_aspect=keep_aspect):
                self.assertEqual(
                    scaled_image_size((400, 200), {"size": size, "keep_aspect": keep_aspect}),
                    expected,
                )


class InputTests(unittest.TestCase):
    def test_tracks_supported_keys_and_space_together(self) -> None:
        manager = InputManager()
        manager.process_native_key(ord("Q"), 0x10, True)
        manager.process_native_key(0x20, 0x39, True)
        manager.process_native_key(ord("Z"), 0x2C, True)

        self.assertEqual(manager.snapshot().pressed_keys, frozenset({"Q", "SPACE"}))

        manager.process_native_key(ord("Q"), 0x10, False)
        self.assertEqual(manager.snapshot().pressed_keys, frozenset({"SPACE"}))
        manager.process_character_key(" ", False)
        self.assertFalse(manager.snapshot().pressed_keys)

    def test_shortcuts_are_actions_not_glowing_keys(self) -> None:
        manager = InputManager()
        manager.process_native_key(0x7B, 0x58, True)
        manager.process_native_key(0x7B, 0x58, True)

        self.assertEqual(manager.consume_actions(), ["open_settings"])
        self.assertFalse(manager.snapshot().pressed_keys)

    def test_numpad_zero_to_nine_select_characters_once_per_press(self) -> None:
        manager = InputManager()
        numpad_keys = (
            (0x60, 0x52, 0),
            (0x61, 0x4F, 1),
            (0x62, 0x50, 2),
            (0x63, 0x51, 3),
            (0x64, 0x4B, 4),
            (0x65, 0x4C, 5),
            (0x66, 0x4D, 6),
            (0x67, 0x47, 7),
            (0x68, 0x48, 8),
            (0x69, 0x49, 9),
        )

        for vk_code, scan_code, _number in numpad_keys:
            manager.process_native_key(vk_code, scan_code, True)
            manager.process_native_key(vk_code, scan_code, True)
            manager.process_native_key(vk_code, scan_code, False)

        self.assertEqual(
            manager.consume_actions(),
            [f"select_character:{number}" for _vk, _scan, number in numpad_keys],
        )
        self.assertFalse(manager.snapshot().pressed_keys)

    def test_top_row_numbers_and_extended_navigation_do_not_select_characters(
        self,
    ) -> None:
        manager = InputManager()

        manager.process_native_key(ord("1"), 0x02, True)
        manager.process_native_key(0x23, 0x4F, True, is_extended=True)

        self.assertFalse(manager.consume_actions())

    def test_tracks_latest_mouse_position(self) -> None:
        manager = InputManager()
        manager.process_mouse_move(-120.5, 840.25)
        self.assertEqual(manager.snapshot().mouse_position, (-120.5, 840.25))

    def test_tracks_left_and_right_mouse_buttons_independently(self) -> None:
        manager = InputManager()
        manager.process_mouse_click(10, 20, "left", True)
        manager.process_mouse_click(30, 40, "right", True)

        snapshot = manager.snapshot()
        self.assertEqual(snapshot.mouse_position, (30.0, 40.0))
        self.assertEqual(snapshot.pressed_mouse_buttons, frozenset({"left", "right"}))

        manager.process_mouse_click(30, 40, "left", False)
        self.assertEqual(manager.snapshot().pressed_mouse_buttons, frozenset({"right"}))
        manager.process_mouse_click(30, 40, "right", False)
        self.assertFalse(manager.snapshot().pressed_mouse_buttons)


class InputStartupTests(unittest.TestCase):
    def test_run_fails_fast_when_global_input_listener_cannot_start(self) -> None:
        app = object.__new__(OverlayApp)
        app.input_manager = Mock()
        app.input_manager.start.side_effect = ModuleNotFoundError("pynput")
        app.microphone_manager = Mock()
        app.tray_manager = Mock()
        app.layered_presenter = Mock()

        with self.assertRaises(RuntimeError):
            app.run()

        app.microphone_manager.start.assert_not_called()
        app.tray_manager.start.assert_not_called()
        app.tray_manager.stop.assert_called_once_with()
        app.microphone_manager.stop.assert_called_once_with()
        app.input_manager.stop.assert_called_once_with()
        app.layered_presenter.close.assert_called_once_with()


class BuildScriptTests(unittest.TestCase):
    def test_build_installs_requirements_with_py_before_pyinstaller(self) -> None:
        lines = (PROJECT_DIR / "build.bat").read_text(encoding="utf-8").splitlines()
        install_index = next(
            index
            for index, line in enumerate(lines)
            if line.strip() == "py -m pip install -r requirements.txt"
        )
        pyinstaller_index = next(
            index
            for index, line in enumerate(lines)
            if "py -m PyInstaller" in line
        )

        self.assertLess(install_index, pyinstaller_index)
        self.assertEqual(lines[install_index + 1].strip(), "if errorlevel 1 goto :error")


class WindowTests(unittest.TestCase):
    def test_transparent_window_is_always_borderless(self) -> None:
        app = object.__new__(OverlayApp)
        app.config = normalise_config(
            {"borderless": False, "transparent_background": True}
        )

        self.assertTrue(app._is_borderless())
        self.assertTrue(app._display_flags() & pygame.NOFRAME)

    def test_resize_uses_current_canvas_dimensions(self) -> None:
        app = object.__new__(OverlayApp)
        app.config = normalise_config({})
        app._create_display = Mock()
        app._sync_tray_state = Mock()

        app._resize_window(1.25)

        self.assertEqual(app.window_scale, 1.25)
        app._create_display.assert_called_once_with((375, 375))

    def test_locked_window_becomes_translucent_only_while_hovered(self) -> None:
        app = object.__new__(OverlayApp)
        app.config = normalise_config({"window_position_locked": True})
        app._window_rect = Mock(return_value=wintypes.RECT(-100, 20, 200, 320))
        user32 = Mock()

        def move_cursor(x: int, y: int) -> None:
            def get_cursor_position(pointer: Any) -> bool:
                pointer._obj.x = x
                pointer._obj.y = y
                return True

            user32.GetCursorPos.side_effect = get_cursor_position

        with patch("main.os.name", "nt"), patch(
            "main.user32_api", return_value=user32
        ):
            move_cursor(-100, 20)
            self.assertEqual(app._window_alpha(), LOCKED_HOVER_ALPHA)

            move_cursor(200, 320)
            self.assertEqual(app._window_alpha(), 255)

            app.config["window_position_locked"] = False
            move_cursor(0, 100)
            self.assertEqual(app._window_alpha(), 255)

    def test_layered_presenter_uses_requested_window_alpha(self) -> None:
        presenter = LayeredWindowPresenter()
        pixels = (ctypes.c_ubyte * 4)()
        presenter.memory_dc = 1
        presenter.bits = ctypes.addressof(pixels)
        presenter.size = (1, 1)
        frame = pygame.Surface((1, 1), pygame.SRCALPHA, 32)
        user32 = Mock()
        user32.GetWindowRect.return_value = True
        captured_alpha: list[int] = []

        def update_layered_window(*arguments: Any) -> bool:
            captured_alpha.append(arguments[7]._obj.SourceConstantAlpha)
            return True

        user32.UpdateLayeredWindow.side_effect = update_layered_window
        with patch("main.user32_api", return_value=user32):
            presenter.present(1, frame, LOCKED_HOVER_ALPHA)

        self.assertEqual(captured_alpha, [LOCKED_HOVER_ALPHA])
        presenter.memory_dc = None


class CharacterSelectionTests(unittest.TestCase):
    def test_character_actions_switch_variants_and_return_to_default(self) -> None:
        app = object.__new__(OverlayApp)
        app.config = normalise_config({})
        app.renderer = Mock()
        app.renderer.select_character.return_value = True
        app.selected_character_path = None
        app.selected_character_open_path = None
        app.microphone_manager = Mock()
        app.microphone_manager.is_active.return_value = False
        app._asset_state = Mock(return_value={"selected": None})

        expected_paths = {
            1: ("image/character1.png", "image/character1_open.png"),
            2: ("image/character2.png", "image/character2_open.png"),
            3: ("image/character3.png", "image/character3_open.png"),
            4: ("image/character4.png", "image/character4_open.png"),
            5: ("image/character5.png", "image/character5_open.png"),
            6: ("image/character6.png", "image/character6_open.png"),
            7: ("image/character7.png", "image/character7_open.png"),
            8: ("image/character8.png", "image/character8_open.png"),
            9: ("image/character9.png", "image/character9_open.png"),
        }
        for number, (path, open_path) in expected_paths.items():
            app.renderer.select_character.reset_mock()
            app._handle_action(f"select_character:{number}")
            app.renderer.select_character.assert_called_once_with(path, open_path)
            self.assertEqual(app.selected_character_path, path)
            self.assertEqual(app.selected_character_open_path, open_path)
            self.assertEqual(app.asset_state, {"selected": None})

        app.renderer.select_character.reset_mock()
        app._handle_action("select_character:0")

        app.renderer.select_character.assert_called_once_with(
            "image/character.png", "image/character_open.png"
        )
        self.assertIsNone(app.selected_character_path)
        self.assertIsNone(app.selected_character_open_path)

    def test_failed_character_switch_keeps_current_selection(self) -> None:
        app = object.__new__(OverlayApp)
        app.config = normalise_config({})
        app.renderer = Mock()
        app.renderer.select_character.return_value = False
        app.selected_character_path = "image/character3.png"
        app.selected_character_open_path = "image/character3_open.png"
        app._asset_state = Mock()

        app._select_character(4)

        self.assertEqual(app.selected_character_path, "image/character3.png")
        self.assertEqual(
            app.selected_character_open_path, "image/character3_open.png"
        )
        app.renderer.select_character.assert_called_once_with(
            "image/character4.png", "image/character4_open.png"
        )
        app._asset_state.assert_not_called()

    def test_microphone_expression_applies_to_selected_character(self) -> None:
        app = object.__new__(OverlayApp)
        app.renderer = Mock()
        app.microphone_manager = Mock()
        app.microphone_manager.is_active.return_value = True
        app.selected_character_path = None

        app._sync_microphone_character()
        app.renderer.set_microphone_active.assert_called_once_with(True)

        app.renderer.set_microphone_active.reset_mock()
        app.selected_character_path = "image/character2.png"
        app._sync_microphone_character()
        app.renderer.set_microphone_active.assert_called_once_with(True)


class RendererTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.init()
        pygame.display.set_mode((1, 1))

    @classmethod
    def tearDownClass(cls) -> None:
        pygame.quit()

    def test_transparent_background_has_clear_pixels(self) -> None:
        config = normalise_config({"transparent_background": True})
        renderer = LayerRenderer(config, PROJECT_DIR / "config.json")

        frame = renderer.render(
            InputSnapshot(frozenset(), (0, 0)), 1 / 60, (0.5, 0.5)
        )

        self.assertEqual(frame.get_at((299, 0)).a, 0)
        self.assertEqual(
            frame.premul_alpha().get_at((299, 0)), pygame.Color(0, 0, 0, 0)
        )

    def test_opaque_background_uses_configured_color(self) -> None:
        config = normalise_config(
            {
                "transparent_background": False,
                "background_color": [12, 34, 56],
            }
        )
        renderer = LayerRenderer(config, PROJECT_DIR / "config.json")

        frame = renderer.render(
            InputSnapshot(frozenset(), (0, 0)), 1 / 60, (0.5, 0.5)
        )

        self.assertEqual(frame.get_at((299, 0)), pygame.Color(12, 34, 56, 255))

    def test_cursor_ratio_moves_right_hand_from_character_perspective(self) -> None:
        config = normalise_config({"smooth_movement": False})
        renderer = LayerRenderer(config, PROJECT_DIR / "config.json")
        snapshot = InputSnapshot(frozenset(), (0, 0))
        base_x, base_y = config["images"]["right_hand_mouse"]["position"]
        range_x, range_y = config["right_hand_range"]
        angle = math.radians(26.0)
        horizontal_x = range_x * math.cos(angle)
        horizontal_y = range_x * math.sin(angle)
        vertical_x = range_y * math.sin(angle)
        vertical_y = range_y * math.cos(angle)

        directions = {
            "mouse left moves hand down-right": (
                (0.0, 0.5),
                (base_x + horizontal_x, base_y + horizontal_y),
            ),
            "mouse right moves hand up-left": (
                (1.0, 0.5),
                (base_x - horizontal_x, base_y - horizontal_y),
            ),
            "mouse up moves hand down-left": (
                (0.5, 0.0),
                (base_x - vertical_x, base_y + vertical_y),
            ),
            "mouse down moves hand up-right": (
                (0.5, 1.0),
                (base_x + vertical_x, base_y - vertical_y),
            ),
        }
        for direction, (cursor_ratio, expected_position) in directions.items():
            with self.subTest(direction):
                renderer.render(snapshot, 1 / 60, cursor_ratio)
                assert renderer._right_position is not None
                self.assertAlmostEqual(
                    renderer._right_position[0], expected_position[0]
                )
                self.assertAlmostEqual(
                    renderer._right_position[1], expected_position[1]
                )

    def test_each_pressed_key_adds_its_own_glow(self) -> None:
        config = normalise_config({"smooth_movement": False})
        renderer = LayerRenderer(config, PROJECT_DIR / "config.json")
        q_only = renderer.render(
            InputSnapshot(frozenset({"Q"}), (0, 0)), 1 / 60, (0.5, 0.5)
        ).copy()
        q_and_a = renderer.render(
            InputSnapshot(frozenset({"Q", "A"}), (0, 0)), 1 / 60, (0.5, 0.5)
        ).copy()
        keyboard_x, keyboard_y = config["images"]["desk_keyboard"]["position"]
        a_x, a_y = config["key_glows"]["A"]["position"]

        self.assertNotEqual(
            q_only.get_at((round(keyboard_x + a_x), round(keyboard_y + a_y))),
            q_and_a.get_at((round(keyboard_x + a_x), round(keyboard_y + a_y))),
        )

    def test_key_glow_tracks_resized_keyboard(self) -> None:
        config = normalise_config(
            {
                "images": {
                    "desk_keyboard": {
                        "position": [10, 20],
                        "size": [150, 150],
                    }
                }
            }
        )
        renderer = LayerRenderer(config, PROJECT_DIR / "config.json")
        renderer.canvas.fill((0, 0, 0, 0))

        renderer._draw_key_glows(
            frozenset({"F"}), renderer.images["desk_keyboard"]
        )

        self.assertGreater(renderer.canvas.get_at((76, 128)).a, 0)
        self.assertEqual(renderer.canvas.get_at((142, 236)).a, 0)

    def test_mouse_button_lights_follow_the_moving_hand(self) -> None:
        config = normalise_config({"smooth_movement": False})
        renderer = LayerRenderer(config, PROJECT_DIR / "config.json")
        cursor_ratio = (0.0, 0.0)
        idle = renderer.render(
            InputSnapshot(frozenset(), (0, 0)), 1 / 60, cursor_ratio
        ).copy()
        left_clicked = renderer.render(
            InputSnapshot(frozenset(), (0, 0), frozenset({"left"})),
            1 / 60,
            cursor_ratio,
        ).copy()
        right_clicked = renderer.render(
            InputSnapshot(frozenset(), (0, 0), frozenset({"right"})),
            1 / 60,
            cursor_ratio,
        ).copy()
        both_clicked = renderer.render(
            InputSnapshot(frozenset(), (0, 0), frozenset({"left", "right"})),
            1 / 60,
            cursor_ratio,
        ).copy()
        right = renderer.images["right_hand_mouse"]
        self.assertIsNotNone(right.surface)
        assert right.surface is not None
        image_width, image_height = right.surface.get_size()
        range_x, range_y = config["right_hand_range"]
        angle = math.radians(26.0)
        hand_position = (
            right.position[0]
            + range_x * math.cos(angle)
            - range_y * math.sin(angle),
            right.position[1]
            + range_x * math.sin(angle)
            + range_y * math.cos(angle),
        )
        centers = {
            button: (
                round(
                    hand_position[0]
                    + spec["position"][0] * image_width / 300
                ),
                round(
                    hand_position[1]
                    + spec["position"][1] * image_height / 300
                ),
            )
            for button, spec in config["mouse_glows"].items()
        }
        left_center = centers["left"]
        right_center = centers["right"]

        self.assertNotEqual(left_clicked.get_at(left_center), idle.get_at(left_center))
        self.assertEqual(right_clicked.get_at(left_center), idle.get_at(left_center))
        self.assertNotEqual(
            right_clicked.get_at(right_center), idle.get_at(right_center)
        )
        self.assertEqual(left_clicked.get_at(right_center), idle.get_at(right_center))
        self.assertNotEqual(
            both_clicked.get_at(left_center), idle.get_at(left_center)
        )
        self.assertNotEqual(
            both_clicked.get_at(right_center), idle.get_at(right_center)
        )

    def test_character_variant_replaces_only_the_character_layer(self) -> None:
        config = normalise_config({})
        renderer = LayerRenderer(config, PROJECT_DIR / "config.json")
        original_character = renderer.images["character"]
        original_right_hand = renderer.images["right_hand_mouse"]

        self.assertTrue(
            renderer.select_character(
                "image/character1.png", "image/character1_open.png"
            )
        )
        selected_character = renderer.images["character"]

        self.assertIsNot(selected_character.surface, original_character.surface)
        self.assertIs(renderer.images["right_hand_mouse"], original_right_hand)
        self.assertFalse(renderer.select_character("image/missing-character.png"))
        self.assertIs(renderer.images["character"], selected_character)

    def test_microphone_expression_restores_selected_character(self) -> None:
        config = normalise_config({})
        renderer = LayerRenderer(config, PROJECT_DIR / "config.json")
        default_character = renderer.images["character"]

        renderer.set_microphone_active(True)
        default_open_character = renderer.images["character"]
        self.assertIsNot(default_open_character, default_character)

        self.assertTrue(
            renderer.select_character(
                "image/character3.png", "image/character3_open.png"
            )
        )
        self.assertIs(renderer.images["character"], renderer._open_character)
        self.assertIsNot(renderer.images["character"], default_open_character)
        selected_character = renderer._selected_character

        renderer.set_microphone_active(False)
        self.assertIs(renderer.images["character"], selected_character)

    def test_missing_open_variant_keeps_selected_character(self) -> None:
        config = normalise_config({})
        renderer = LayerRenderer(config, PROJECT_DIR / "config.json")

        with tempfile.TemporaryDirectory() as temporary_directory:
            missing_open_path = Path(temporary_directory) / "character9_open.png"
            renderer.set_microphone_active(True)
            self.assertTrue(
                renderer.select_character(
                    "image/character9.png", str(missing_open_path)
                )
            )

        self.assertIs(renderer.images["character"], renderer._selected_character)

    def test_keypad_microphone_and_reload_preserve_character_and_hand_state(self) -> None:
        app = object.__new__(OverlayApp)
        app.config = normalise_config({})
        app.renderer = LayerRenderer(app.config, PROJECT_DIR / "config.json")
        app.microphone_manager = Mock()
        app.microphone_manager.is_active.return_value = True
        app.selected_character_path = None
        app.selected_character_open_path = None
        app._asset_state = Mock(return_value={})
        renderer = app.renderer
        renderer._right_position = [9.0, 7.0]
        app._sync_microphone_character()
        self.assertIs(renderer.images["character"], renderer._open_character)

        app._select_character(3)
        self.assertIs(renderer.images["character"], renderer._open_character)
        self.assertEqual(renderer._right_position, [9.0, 7.0])
        selected_pixels = pygame.image.tobytes(renderer.images["character"].surface, "RGBA")

        renderer.reload_config(
            app.config,
            selected_character_path=app.selected_character_path,
            selected_character_open_path=app.selected_character_open_path,
        )
        app._sync_microphone_character()
        self.assertEqual(
            pygame.image.tobytes(renderer.images["character"].surface, "RGBA"), selected_pixels
        )
        app._select_character(0)
        self.assertIs(renderer.images["character"], renderer._open_character)
        with patch.object(renderer, "_load_image", side_effect=AssertionError("unexpected disk read")):
            app.microphone_manager.is_active.return_value = False
            app._sync_microphone_character()
            self.assertIs(renderer.images["character"], renderer._selected_character)
            app.microphone_manager.is_active.return_value = True
            app._sync_microphone_character()
            self.assertIs(renderer.images["character"], renderer._open_character)

    def test_asset_directory_contains_five_layers_and_icon(self) -> None:
        required = {
            "character.png",
            "character_open.png",
            "character1.png",
            "character2.png",
            "character3.png",
            "character4.png",
            "character5.png",
            "character6.png",
            "character7.png",
            "character8.png",
            "character9.png",
            "character1_open.png",
            "character2_open.png",
            "character3_open.png",
            "character4_open.png",
            "character5_open.png",
            "character6_open.png",
            "character7_open.png",
            "character8_open.png",
            "desk_keyboard.png",
            "right_hand_mouse.png",
            "left_hand_idle.png",
            "left_hand_pressed.png",
            "icon.png",
        }
        available = {path.name for path in (PROJECT_DIR / "image").glob("*.png")}
        self.assertTrue(required.issubset(available))

    def test_icon_is_a_valid_png(self) -> None:
        with Image.open(PROJECT_DIR / "image" / "icon.png") as opened:
            self.assertEqual(opened.format, "PNG")
            icon = opened.convert("RGBA")
        self.assertGreater(icon.width, 0)
        self.assertGreater(icon.height, 0)
        self.assertIsNotNone(icon.getchannel("A").getbbox())

    def test_every_supported_key_produces_visible_light(self) -> None:
        config = normalise_config({"smooth_movement": False})
        renderer = LayerRenderer(config, PROJECT_DIR / "config.json")
        keyboard_x, keyboard_y = config["images"]["desk_keyboard"]["position"]

        for key in KEYS:
            frame = renderer.render(
                InputSnapshot(frozenset({key}), (0, 0)),
                1 / 60,
                (0.5, 0.5),
            ).copy()
            center_x, center_y = config["key_glows"][key]["position"]
            width, height = config["key_glows"][key]["size"]
            bounds = pygame.Rect(
                round(keyboard_x + center_x - width / 2),
                round(keyboard_y + center_y - height / 2),
                round(width),
                round(height),
            )
            visible_light = sum(
                1
                for x in range(bounds.left, bounds.right)
                for y in range(bounds.top, bounds.bottom)
                if (pixel := frame.get_at((x, y))).r > 220
                and pixel.g > 170
                and pixel.b < 220
            )
            self.assertGreater(visible_light, 0, key)


class ReloadTests(unittest.TestCase):
    def test_changed_image_file_is_reloaded_without_config_change(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            character_path = directory / "character.png"
            character_path.write_bytes(b"first")

            app = object.__new__(OverlayApp)
            app.config_path = directory / "config.json"
            app.config = normalise_config(
                {"images": {"character": {"path": str(character_path)}}}
            )
            app.selected_character_path = "image/character3.png"
            app.selected_character_open_path = "image/character3_open.png"
            app.config_mtime = None
            app.last_file_check = 0.0
            app.asset_state = app._asset_state()
            app.renderer = Mock()
            app.microphone_manager = Mock()
            app.tray_manager = Mock()
            app._set_window_icon = Mock()
            app._sync_tray_state = Mock()

            character_path.write_bytes(b"second version")
            app._reload_config_if_changed()

            app.renderer.reload_config.assert_called_once_with(
                app.config,
                selected_character_path="image/character3.png",
                selected_character_open_path="image/character3_open.png",
            )
            app.tray_manager.update_icon.assert_called_once()

    def test_new_selected_open_image_is_reloaded(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            character_path = directory / "character9.png"
            open_path = directory / "character9_open.png"
            character_path.write_bytes(b"character")

            app = object.__new__(OverlayApp)
            app.config_path = directory / "config.json"
            app.config = normalise_config({})
            app.selected_character_path = str(character_path)
            app.selected_character_open_path = str(open_path)
            app.config_mtime = None
            app.last_file_check = 0.0
            app.asset_state = app._asset_state()
            app.renderer = Mock()
            app.microphone_manager = Mock()
            app.tray_manager = Mock()
            app._set_window_icon = Mock()
            app._sync_tray_state = Mock()

            open_path.write_bytes(b"open character")
            app._reload_config_if_changed()

            app.renderer.reload_config.assert_called_once_with(
                app.config,
                selected_character_path=str(character_path),
                selected_character_open_path=str(open_path),
            )

    def test_tray_icon_can_be_replaced_while_running(self) -> None:
        icon_path = PROJECT_DIR / "image" / "icon.png"
        tray = TrayManager(icon_path)
        tray._icon = Mock()

        tray.update_icon(icon_path)

        self.assertEqual(tray.icon_path, icon_path)
        self.assertEqual(tray._icon.icon.size, (64, 64))


if __name__ == "__main__":
    unittest.main()
