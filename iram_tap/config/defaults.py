from __future__ import annotations

from typing import Any

from iram_tap.models import KEYS, MOUSE_BUTTONS, WINDOW_SCALES

APPLICATION_NAME = "iram_tap"
SCHEMA_VERSION = 1
LAYER_NAMES = ("character", "desk_keyboard", "left_hand", "right_hand")
KEY_GLOW_REFERENCE_SIZE = (300, 300)
MOUSE_GLOW_REFERENCE_SIZE = (300, 300)
KEYBOARD_IMAGE_DIRECTORY = "image/keybord_Iram"

DEFAULT_CONFIG: dict[str, Any] = {
    "schema_version": SCHEMA_VERSION,
    "window_width": 300,
    "window_height": 300,
    "window_x": None,
    "window_y": None,
    "window_position_locked": False,
    "fps": 60,
    "always_on_top": True,
    "borderless": True,
    "transparent_background": True,
    "background_color": [0, 0, 0],
    "icon_path": f"{KEYBOARD_IMAGE_DIRECTORY}/icon.png",
    "layer_order": list(LAYER_NAMES),
    "smooth_movement": True,
    "right_hand_speed": 0.32,
    "right_hand_range": [17, 10],
    "microphone_enabled": True,
    "microphone_device": "",
    "microphone_threshold": 0.02,
    "microphone_high_threshold": 0.05,
    "microphone_release_delay": 0.18,
    "microphone_open_image": f"{KEYBOARD_IMAGE_DIRECTORY}/character_open.png",
    "key_glow_color": [255, 220, 72],
    "key_glow_alpha": 210,
    "key_glows": {
        "Q": {"position": [205, 282], "size": [25, 20]},
        "W": {"position": [177, 268], "size": [27, 20]},
        "E": {"position": [148, 253], "size": [27, 19]},
        "R": {"position": [118, 237], "size": [29, 20]},
        "A": {"position": [215, 258], "size": [24, 18]},
        "S": {"position": [189, 243], "size": [24, 17]},
        "D": {"position": [161, 230], "size": [24, 16]},
        "F": {"position": [132, 216], "size": [28, 16]},
        "SPACE": {"position": [183, 215], "size": [56, 18]},
    },
    "mouse_glow_color": [255, 220, 72],
    "mouse_glow_alpha": 210,
    "mouse_glows": {
        "left": {"position": [42.0, 180.0], "size": [6.6, 5.4]},
        "right": {"position": [48.9, 182.1], "size": [6.6, 5.4]},
    },
    "images": {
        name: {
            "path": f"{KEYBOARD_IMAGE_DIRECTORY}/{name}.png",
            "position": [0, 0],
            "size": [300, 300],
            "keep_aspect": True,
        }
        for name in (
            "character", "desk_keyboard", "right_hand_mouse",
            "left_hand_idle", "left_hand_pressed",
        )
    },
}

__all__ = [
    "DEFAULT_CONFIG", "APPLICATION_NAME", "SCHEMA_VERSION", "LAYER_NAMES",
    "KEY_GLOW_REFERENCE_SIZE", "MOUSE_GLOW_REFERENCE_SIZE", "KEYBOARD_IMAGE_DIRECTORY",
    "KEYS", "MOUSE_BUTTONS", "WINDOW_SCALES",
]
