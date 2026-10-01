from __future__ import annotations

from array import array
import io
import json
import threading
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from iram_tap.config.validation import normalise_config
from iram_tap.platform.audio import MicrophoneManager
from iram_tap.platform.input import InputManager
from iram_tap.models import Action, Command
from iram_tap.playback_activity import PlaybackActivity
from iram_tap.voice import VoiceController, play_pcm, resolve_output, synthesize


class OutputTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = normalise_config({"fish_local_device": "Headset [MME]",
                                        "fish_virtual_device": "CABLE Input [MME]"})
        self.audio = Mock()
        self.audio.query_hostapis.return_value = [{"name": "MME"}]
        self.devices = [
            {"name": "Microphone", "hostapi": 0, "max_output_channels": 0},
            {"name": "Headset", "hostapi": 0, "max_output_channels": 2, "default_samplerate": 48000},
            {"name": "CABLE Input", "hostapi": 0, "max_output_channels": 2, "default_samplerate": 48000},
        ]
        self.audio.query_devices.side_effect = lambda *args: self.devices[args[0] or 1] if args else self.devices

    def test_modes_resolve_to_separate_remembered_devices(self) -> None:
        self.assertEqual(resolve_output(self.config, self.audio), 1)
        self.config["fish_output_mode"] = "virtual"
        self.assertEqual(resolve_output(self.config, self.audio), 2)
        self.config["fish_output_mode"] = "local"
        self.assertEqual(resolve_output(self.config, self.audio), 1)

    def test_missing_virtual_never_falls_back_to_speakers(self) -> None:
        self.config["fish_output_mode"] = "virtual"
        for name in ("", "Disconnected cable"):
            self.config["fish_virtual_device"] = name
            with self.assertRaises(ValueError):
                resolve_output(self.config, self.audio)

    def test_missing_selected_local_device_does_not_fall_back(self) -> None:
        self.config["fish_local_device"] = "Missing headset"
        with self.assertRaises(ValueError):
            resolve_output(self.config, self.audio)
        self.config["fish_local_device"] = ""
        self.assertIsNone(resolve_output(self.config, self.audio))

    def test_playback_uses_only_selected_device_resamples_and_applies_volume(self) -> None:
        stream = Mock()
        context = Mock()
        context.__enter__ = Mock(return_value=stream)
        context.__exit__ = Mock(return_value=False)
        self.audio.OutputStream.return_value = context
        self.config.update(fish_output_mode="virtual", fish_volume=0.5)
        with patch.dict("sys.modules", sounddevice=self.audio):
            play_pcm(array("h", [16384] * 4410).tobytes(), self.config, threading.Event())
        self.assertEqual(self.audio.OutputStream.call_args.kwargs["device"], 2)
        self.assertEqual(sum(len(call.args[0]) for call in stream.write.call_args_list), 4800)
        self.assertEqual(stream.write.call_args.args[0].shape[1], 2)
        self.assertAlmostEqual(float(stream.write.call_args.args[0][0, 0]), 0.25)

    def test_lip_level_tracks_audio_chunks_and_closes_at_end(self) -> None:
        stream = Mock()
        context = Mock()
        context.__enter__ = Mock(return_value=stream)
        context.__exit__ = Mock(return_value=False)
        self.audio.OutputStream.return_value = context
        levels = []
        # Two exact chunks, one voiced then one silent, at the output rate.
        self.devices[1]["default_samplerate"] = 44100
        pcm = array("h", [16384] * 882 + [0] * 882).tobytes()
        with patch.dict("sys.modules", sounddevice=self.audio):
            play_pcm(pcm, self.config, threading.Event(), levels.append)
        self.assertEqual(levels, [0.5, 0.0, 0.0])

    def test_output_error_clears_lip_level(self) -> None:
        levels = []
        self.audio.OutputStream.side_effect = RuntimeError("device lost")
        with patch.dict("sys.modules", sounddevice=self.audio):
            with self.assertRaises(RuntimeError):
                play_pcm(b"\0\0", self.config, threading.Event(), levels.append)
        self.assertEqual(levels, [0.0])

    def test_cancelled_audio_does_not_open_output(self) -> None:
        cancel = threading.Event()
        cancel.set()
        with patch.dict("sys.modules", sounddevice=self.audio):
            play_pcm(b"\0\0", self.config, cancel)
        self.audio.OutputStream.assert_not_called()


class PipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = normalise_config({"fish_api_key_protected": "encrypted",
                                        "fish_reference_id": "voice-id"})
        self.mic = Mock()
        self.controller = VoiceController(self.config, self.mic)
        self.addCleanup(self.controller.close)

    def test_headset_test_speaks_exact_requested_text_without_recording(self) -> None:
        with patch.object(self.controller, "_validate"), patch.object(self.controller, "_launch") as launch:
            self.controller.test_voice()
        launch.assert_called_once_with(b"", 16000, "fish audio 테스트")
        self.mic.begin_recording.assert_not_called()

    def test_recording_and_generation_do_not_animate_from_microphone(self) -> None:
        self.assertIsNone(self.controller.expression_level())
        for state in ("recording", "working", "playing", "cancelling"):
            self.controller.state = state
            self.assertEqual(self.controller.expression_level(), 0)
        self.mic.expression_level.assert_not_called()

    def test_overlay_prefers_fish_playback_over_live_microphone(self) -> None:
        from iram_tap.app import OverlayApp
        app = OverlayApp.__new__(OverlayApp)
        app.voice = self.controller
        app.microphone_manager = self.mic
        app.renderer = Mock()
        self.mic.expression_level.return_value = 2
        self.controller.state = "recording"
        app._sync_microphone_character()
        app.renderer.set_microphone_level.assert_called_with(0)
        self.controller.state = "playing"
        self.controller.activity.publish(0.03)
        app._sync_microphone_character()
        app.renderer.set_microphone_level.assert_called_with(1)
        self.controller.activity.publish(0.0)
        app._sync_microphone_character()
        app.renderer.set_microphone_level.assert_called_with(0)
        self.mic.expression_level.assert_not_called()

    def test_playback_amplitude_controls_mouth_even_with_microphone_disabled(self) -> None:
        self.controller.config["microphone_enabled"] = False
        self.controller.state = "playing"
        for amplitude, expected in ((0.0, 0), (0.03, 1), (0.2, 2), (0.0, 0)):
            self.controller.activity.publish(amplitude)
            self.assertEqual(self.controller.expression_level(), expected)

    def test_stale_activity_expires_if_settings_process_dies(self) -> None:
        meter = PlaybackActivity()
        with patch("iram_tap.playback_activity.time.monotonic", return_value=10):
            meter.publish(0.2)
            self.assertEqual(meter.read(), 0.2)
        with patch("iram_tap.playback_activity.time.monotonic", return_value=11):
            self.assertIsNone(meter.read())
        meter.close()
        meter.publish(0.3)
        self.assertIsNone(meter.read())

    def test_cancel_during_request_drops_late_result(self) -> None:
        entered, release = threading.Event(), threading.Event()

        def slow_request(*args: object) -> bytes:
            entered.set()
            release.wait(3)
            return b"\0\0"

        with patch("iram_tap.voice.unprotect_key", return_value="test-key"), \
                patch("iram_tap.voice.synthesize", side_effect=slow_request), \
                patch("iram_tap.voice.play_pcm") as playback:
            self.controller._launch(b"", 16000, "테스트")
            try:
                self.assertTrue(entered.wait(2))
                self.controller.toggle()
            finally:
                release.set()
                self.controller._thread.join(3)
            self.controller.poll()
            playback.assert_not_called()
            self.assertEqual(self.controller.state, "idle")

    def test_registered_f11_does_not_double_dispatch(self) -> None:
        manager = InputManager()
        manager._voice_hotkey = Mock(registered=True)
        manager.process_native_key(0x7A, 0x57, True)
        manager.process_native_key(0x7A, 0x57, False)
        self.assertEqual(manager.consume_actions(), [])
        manager._emit_voice()
        self.assertEqual(manager.consume_actions(), [Command(Action.TOGGLE_VOICE)])

    def test_output_switch_cancels_current_job_but_window_change_does_not(self) -> None:
        self.controller.reconfigure({**self.config, "window_x": 100})
        self.assertFalse(self.controller._cancel.is_set())
        self.controller.reconfigure({**self.config, "fish_output_mode": "virtual"})
        self.assertTrue(self.controller._cancel.is_set())

    def test_silence_does_not_call_api(self) -> None:
        self.mic.end_recording.return_value = (bytes(16000), 16000)
        with patch.object(self.controller, "_launch") as launch:
            self.controller._finish_recording()
        launch.assert_not_called()
        self.assertIn("감지되지", self.controller.status)

    def test_recording_auto_finishes_at_limit(self) -> None:
        self.controller.state = "recording"
        self.controller._started_at = 0
        with patch("iram_tap.voice.time.monotonic", return_value=31), \
                patch.object(self.controller, "_finish_recording") as finish:
            self.controller.poll()
        finish.assert_called_once()

    def test_authentication_error_is_actionable_without_secret(self) -> None:
        error = HTTPError("https://api.fish.audio/v1/tts", 401, "test-key", {}, None)
        with patch("iram_tap.voice.urlopen", side_effect=error):
            with self.assertRaisesRegex(ValueError, "인증 실패") as raised:
                synthesize("테스트", "test-key", self.config, threading.Event())
        self.assertNotIn("test-key", str(raised.exception))

    def test_tts_request_and_pcm_response(self) -> None:
        with patch("iram_tap.voice.urlopen", return_value=io.BytesIO(b"\1\0" * 100)) as request:
            result = synthesize("테스트", "test-key", self.config, threading.Event())
        sent = request.call_args.args[0]
        self.assertEqual(sent.get_header("Authorization"), "Bearer test-key")
        self.assertEqual(json.loads(sent.data)["reference_id"], "voice-id")
        self.assertEqual(json.loads(sent.data)["format"], "pcm")
        self.assertEqual(len(result), 200)


class CaptureTests(unittest.TestCase):
    def test_recording_shares_existing_stream_and_is_bounded(self) -> None:
        mic = MicrophoneManager(normalise_config({}))
        mic._stream = Mock()
        mic._sample_rate = 10
        stream = mic._stream
        mic.begin_recording(seconds=1)
        mic._audio_callback(array("h", [1000] * 20).tobytes(), 20, None, None)
        pcm, rate = mic.end_recording()
        self.assertEqual(rate, 10)
        self.assertEqual(len(pcm), 20)
        self.assertIs(mic._stream, stream)
        stream.close.assert_not_called()

    def test_capture_works_when_expression_detection_disabled(self) -> None:
        mic = MicrophoneManager(normalise_config({"microphone_enabled": False}))
        mic._stream = Mock()
        stream = mic._stream
        mic.begin_recording()
        mic._audio_callback(array("h", [1000] * 20).tobytes(), 20, None, None)
        pcm, _ = mic.end_recording()
        self.assertEqual(len(pcm), 40)
        self.assertEqual(mic.expression_level(), 0)
        stream.close.assert_called_once()

    def test_input_overflow_does_not_send_corrupt_recording(self) -> None:
        mic = MicrophoneManager(normalise_config({}))
        mic._stream = Mock()
        mic.begin_recording()
        mic._audio_callback(array("h", [1000] * 20).tobytes(), 20, None, True)
        with self.assertRaisesRegex(ValueError, "끊겼습니다"):
            mic.end_recording()


if __name__ == "__main__":
    unittest.main()
