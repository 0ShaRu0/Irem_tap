import unittest
from unittest.mock import Mock

from iram_tap.models import Action, Command
from iram_tap.platform.input import InputManager


class InputCommandTests(unittest.TestCase):
    def test_registered_hotkey_does_not_double_dispatch_from_keyboard_hook(self) -> None:
        manager = InputManager()
        manager._text_hotkey = Mock(registered=True)
        manager.process_native_key(0x79, 0x44, True)
        manager.process_native_key(0x79, 0x44, False)
        self.assertEqual(manager.consume_actions(), [])
        manager._emit_text_mode()
        self.assertEqual(manager.consume_actions(), [Command(Action.TOGGLE_TEXT)])

    def test_stop_clears_pressed_state_despite_a_listener_failure(self) -> None:
        manager = InputManager()
        manager.process_native_key(ord("Q"), 0x10, True)
        manager._keyboard_listener = Mock()
        manager._mouse_listener = Mock()
        manager._keyboard_listener.stop.side_effect = RuntimeError("stop failure")
        mouse = manager._mouse_listener
        with self.assertLogs("iram_tap.platform.input", level="ERROR"):
            manager.stop()
        mouse.stop.assert_called_once()
        self.assertFalse(manager.snapshot().pressed_keys)
