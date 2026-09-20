import unittest

from iram_tap.text_mode import MAX_TEXT_LENGTH, TextMode, TextPhase


class TextModeTests(unittest.TestCase):
    def test_enter_batch_accepts_final_ime_event_without_duplicate(self) -> None:
        mode = TextMode()
        mode.begin()
        mode.insert("한")
        mode.compose("글", 0, 1)
        mode.request_commit()
        mode.insert("글")
        mode.commit()
        self.assertEqual(mode.value, "한글")
        self.assertIs(mode.phase, TextPhase.PINNED)
        mode.insert("ignored")
        self.assertEqual(mode.value, "한글")
        mode.clear()
        mode.begin()
        self.assertEqual(mode.display_text, "")

    def test_ime_owns_backspace_and_input_is_bounded(self) -> None:
        mode = TextMode()
        mode.begin()
        mode.insert("한")
        mode.compose("ㄱ")
        mode.backspace()
        self.assertEqual(mode.value, "한")
        mode.compose("")
        mode.backspace()
        self.assertEqual(mode.value, "")
        mode.insert("a" * 10000)
        mode.compose("나" * 10)
        self.assertEqual(len(mode.display_text), MAX_TEXT_LENGTH)
