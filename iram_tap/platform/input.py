from __future__ import annotations

import os
import logging
import threading
from collections import deque
from typing import Any

from iram_tap.models import KEYS, MOUSE_BUTTONS, InputSnapshot, Action, Command
from iram_tap.platform.hotkeys import TextHotkey

logger = logging.getLogger(__name__)

# IBM PC set-1 scan codes. These identify physical QWERTY positions independently
# of the active Windows IME or keyboard text layout.
SCAN_CODE_TO_KEY = {
    0x10: "Q",
    0x11: "W",
    0x12: "E",
    0x13: "R",
    0x1E: "A",
    0x1F: "S",
    0x20: "D",
    0x21: "F",
    0x39: "SPACE",
}
VK_CODE_TO_KEY = {ord(key): key for key in KEYS if len(key) == 1}
VK_CODE_TO_KEY[0x20] = "SPACE"
SHORTCUT_VK = {
    0x78: Command(Action.TOGGLE_LOCK),  # F9
    0x79: Command(Action.TOGGLE_TEXT),  # F10
}
NUMPAD_SCAN_CODE_TO_CHARACTER = {
    0x52: 0,
    0x4F: 1,
    0x50: 2,
    0x51: 3,
    0x4B: 4,
    0x4C: 5,
    0x4D: 6,
    0x47: 7,
    0x48: 8,
    0x49: 9,
}
NUMPAD_SCAN_CODE_TO_ACTION = {
    0x4E: Command(Action.NEXT_MODE),  # Numpad +
    0x4A: Command(Action.PREVIOUS_MODE),  # Numpad -
}

WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105


class InputManager:
    """Thread-safe state shared by short pynput callbacks and the render loop."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pressed_keys: set[str] = set()
        self._pressed_shortcuts: set[tuple[str, int]] = set()
        self._actions: deque[Command] = deque()
        self._mouse_position: tuple[float, float] | None = None
        self._pressed_mouse_buttons: set[str] = set()

        self._keyboard_listener: Any = None
        self._mouse_listener: Any = None
        self._text_hotkey: TextHotkey | None = None

    def process_native_key(
        self,
        vk_code: int | None,
        scan_code: int | None,
        pressed: bool,
        is_extended: bool = False,
    ) -> None:
        key_name = SCAN_CODE_TO_KEY.get(scan_code) if scan_code is not None else None
        if key_name is None and vk_code is not None:
            key_name = VK_CODE_TO_KEY.get(vk_code)

        shortcut_token: tuple[str, int] | None = None
        shortcut_action: Command | None = None
        if not is_extended and scan_code in NUMPAD_SCAN_CODE_TO_ACTION:
            shortcut_token = ("scan", scan_code)
            shortcut_action = NUMPAD_SCAN_CODE_TO_ACTION[scan_code]
        elif not is_extended and scan_code in NUMPAD_SCAN_CODE_TO_CHARACTER:
            character = NUMPAD_SCAN_CODE_TO_CHARACTER[scan_code]
            shortcut_token = ("scan", scan_code)
            shortcut_action = Command(Action.SELECT_CHARACTER, character)
        elif vk_code in SHORTCUT_VK:
            shortcut_token = ("vk", vk_code)
            shortcut_action = SHORTCUT_VK[vk_code]
            if vk_code == 0x79 and self._text_hotkey is not None and self._text_hotkey.registered:
                shortcut_action = None

        with self._lock:
            if key_name is not None:
                if pressed:
                    self._pressed_keys.add(key_name)
                else:
                    self._pressed_keys.discard(key_name)

            if shortcut_token is not None and shortcut_action is not None:
                if pressed and shortcut_token not in self._pressed_shortcuts:
                    self._pressed_shortcuts.add(shortcut_token)
                    self._actions.append(shortcut_action)
                elif not pressed:
                    self._pressed_shortcuts.discard(shortcut_token)

    def process_character_key(self, character: str | None, pressed: bool) -> None:
        if not character or len(character) != 1 or not character.isascii():
            return
        if character == " ":
            self.process_native_key(0x20, None, pressed)
            return
        upper = character.upper()
        if upper in KEYS:
            self.process_native_key(ord(upper), None, pressed)

    def process_mouse_move(self, x: float, y: float) -> None:
        with self._lock:
            self._mouse_position = (float(x), float(y))

    def process_mouse_click(
        self, x: float, y: float, button: Any, pressed: bool
    ) -> None:
        button_name = str(getattr(button, "name", button)).lower().rsplit(".", 1)[-1]
        with self._lock:
            self._mouse_position = (float(x), float(y))
            if button_name not in MOUSE_BUTTONS:
                return
            if pressed:
                self._pressed_mouse_buttons.add(button_name)
            else:
                self._pressed_mouse_buttons.discard(button_name)

    def snapshot(self) -> InputSnapshot:
        with self._lock:
            snapshot = InputSnapshot(
                pressed_keys=frozenset(self._pressed_keys),
                mouse_position=self._mouse_position,
                pressed_mouse_buttons=frozenset(self._pressed_mouse_buttons),
            )
            return snapshot

    def consume_actions(self) -> list[Command]:
        with self._lock:
            actions = list(self._actions)
            self._actions.clear()
            return actions

    def _win32_event_filter(self, message: int, data: Any) -> bool:
        if message in (WM_KEYDOWN, WM_SYSKEYDOWN, WM_KEYUP, WM_SYSKEYUP):
            self.process_native_key(
                int(data.vkCode),
                int(data.scanCode),
                message in (WM_KEYDOWN, WM_SYSKEYDOWN),
                bool(int(getattr(data, "flags", 0)) & 0x01),
            )
            # Skip pynput's translated character callback without suppressing the
            # event system-wide. The native scan/VK data above is authoritative.
            return False
        return True

    @staticmethod
    def _key_vk(key: Any) -> int | None:
        vk_code = getattr(key, "vk", None)
        if vk_code is not None:
            return int(vk_code)
        value = getattr(key, "value", None)
        vk_code = getattr(value, "vk", None)
        return int(vk_code) if vk_code is not None else None

    def _fallback_key_event(self, key: Any, pressed: bool) -> None:
        vk_code = self._key_vk(key)
        if vk_code is not None:
            self.process_native_key(vk_code, None, pressed)
            return
        self.process_character_key(getattr(key, "char", None), pressed)

    def start(self) -> None:
        if self._keyboard_listener or self._mouse_listener:
            return

        # Lazy imports keep configuration and renderer diagnostics usable on
        # machines without a desktop session.
        from pynput import keyboard, mouse

        keyboard_options: dict[str, Any] = {
            "on_press": lambda key: self._fallback_key_event(key, True),
            "on_release": lambda key: self._fallback_key_event(key, False),
            "suppress": False,
        }
        if os.name == "nt":
            keyboard_options["win32_event_filter"] = self._win32_event_filter

        self._keyboard_listener = keyboard.Listener(**keyboard_options)
        self._mouse_listener = mouse.Listener(
            on_move=self.process_mouse_move,
            on_click=self.process_mouse_click,
            suppress=False,
        )
        try:
            if os.name == "nt":
                self._text_hotkey = TextHotkey(self._emit_text_mode)
                self._text_hotkey.start()
            self._keyboard_listener.start()
            self._mouse_listener.start()
            self._keyboard_listener.wait()
            self._mouse_listener.wait()
        except Exception:
            self.stop()
            raise

    def stop(self) -> None:
        if self._text_hotkey is not None:
            self._text_hotkey.stop()
            self._text_hotkey = None
        for listener in (self._keyboard_listener, self._mouse_listener):
            if listener is not None:
                try:
                    listener.stop()
                except Exception:
                    logger.exception("입력 리스너 정지 실패")
        for listener in (self._keyboard_listener, self._mouse_listener):
            if listener is not None and listener.is_alive():
                try:
                    listener.join(timeout=1.0)
                except Exception:
                    logger.exception("입력 리스너 종료 대기 실패")
        self._keyboard_listener = None
        self._mouse_listener = None
        with self._lock:
            self._pressed_keys.clear()
            self._pressed_shortcuts.clear()
            self._pressed_mouse_buttons.clear()
            self._actions.clear()

    def _emit_text_mode(self) -> None:
        with self._lock:
            self._actions.append(Command(Action.TOGGLE_TEXT))
