from __future__ import annotations

from array import array
import unittest
from unittest.mock import Mock, patch

from config_manager import normalise_config
from microphone_manager import MicrophoneManager


class MicrophoneTests(unittest.TestCase):
    def setUp(self) -> None:
        self.audio = Mock()
        self.audio.query_devices.return_value = {
            "default_samplerate": 48000,
            "name": "Test microphone",
        }
        self.audio.RawInputStream.side_effect = lambda **_kwargs: Mock()
        audio_patch = patch.dict("sys.modules", sounddevice=self.audio)
        audio_patch.start()
        self.addCleanup(audio_patch.stop)
        self.config = normalise_config(
            {"microphone_threshold": 0.1, "microphone_release_delay": 0.2}
        )
        self.manager = MicrophoneManager(self.config)
        self.addCleanup(self.manager.stop)

    def test_threshold_activates_and_release_delay_prevents_flicker(self) -> None:
        self.manager.process_level(0.11, now=1.0)
        self.assertTrue(self.manager.is_active())
        self.manager.process_level(0.01, now=1.19)
        self.assertTrue(self.manager.is_active())
        self.manager.process_level(0.01, now=1.21)
        self.assertFalse(self.manager.is_active())

    def test_disabled_microphone_never_activates(self) -> None:
        self.manager.reconfigure({**self.config, "microphone_enabled": False})
        self.manager.start()
        self.manager.process_level(1.0, now=1.0)
        self.assertFalse(self.manager.is_active())
        self.audio.RawInputStream.assert_not_called()

    def test_unrelated_config_changes_preserve_stream_and_activity(self) -> None:
        self.manager.start()
        stream = self.manager._stream
        self.manager.process_level(0.11, now=1.0)

        self.manager.reconfigure({
            **self.config,
            "window_x": 40,
            "key_glow_color": [0, 255, 0],
            "microphone_open_image": "image/another.png",
        })

        self.assertIs(self.manager._stream, stream)
        stream.stop.assert_not_called()
        self.audio.RawInputStream.assert_called_once()
        self.assertTrue(self.manager.is_active())

    def test_sensitivity_changes_apply_without_reopening_stream(self) -> None:
        self.manager.start()
        stream = self.manager._stream
        self.manager.process_level(0.11, now=1.0)

        self.manager.reconfigure({
            **self.config,
            "microphone_threshold": 0.2,
            "microphone_release_delay": 0.3,
        })
        self.assertTrue(self.manager.is_active())
        self.manager.process_level(0.11, now=1.21)
        self.assertTrue(self.manager.is_active())
        self.manager.process_level(0.11, now=1.31)
        self.assertFalse(self.manager.is_active())
        self.manager.process_level(0.25, now=1.4)
        self.assertTrue(self.manager.is_active())
        self.assertIs(self.manager._stream, stream)
        self.audio.RawInputStream.assert_called_once()

    def test_device_change_restarts_and_disabling_closes_stream(self) -> None:
        self.manager.start()
        old_stream = self.manager._stream
        self.manager.process_level(1.0, now=1.0)
        changed = {**self.config, "microphone_device": "Other [MME]"}

        with patch("microphone_manager._input_device_entries", return_value=[(7, "Other [MME]")]):
            self.manager.reconfigure(changed)

        old_stream.stop.assert_called_once()
        old_stream.close.assert_called_once()
        self.assertEqual(self.audio.RawInputStream.call_args.kwargs["device"], 7)
        self.assertFalse(self.manager.is_active())
        new_stream = self.manager._stream
        self.assertIsNot(new_stream, old_stream)

        self.manager.reconfigure({**changed, "microphone_enabled": False})
        new_stream.close.assert_called_once()
        self.assertIsNone(self.manager._stream)
        self.assertEqual(self.audio.RawInputStream.call_count, 2)

        self.manager.reconfigure(self.config)
        self.assertIsNotNone(self.manager._stream)
        self.assertEqual(self.audio.RawInputStream.call_count, 3)

    def test_failed_start_and_failed_stop_release_device(self) -> None:
        stream = Mock()
        stream.start.side_effect = RuntimeError("start failed")
        self.audio.RawInputStream.side_effect = None
        self.audio.RawInputStream.return_value = stream
        self.manager.start()
        stream.close.assert_called_once()
        self.assertIsNone(self.manager._stream)

        self.manager.stop()
        stream.reset_mock()
        stream.start.side_effect = None
        stream.stop.side_effect = RuntimeError("stop failed")
        self.manager.start()
        self.manager.stop()
        self.manager.stop()
        stream.stop.assert_called_once()
        stream.close.assert_called_once()

    def test_pcm_callback_uses_rms_rather_than_signed_average(self) -> None:
        self.manager._audio_callback(array("h", [8192, -8192]).tobytes(), 2, None, None)
        self.assertTrue(self.manager.is_active())


if __name__ == "__main__":
    unittest.main()
