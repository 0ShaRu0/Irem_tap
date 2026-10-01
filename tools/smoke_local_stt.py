"""Download the local Whisper model and verify decoder/VAD on synthetic silence."""
from __future__ import annotations

import sys
from pathlib import Path
from queue import SimpleQueue
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from iram_tap.config.validation import normalise_config  # noqa: E402
from iram_tap.platform.audio import MicrophoneManager  # noqa: E402
from iram_tap.voice import VoiceController  # noqa: E402


if __name__ == "__main__":
    config = normalise_config({})
    voice = VoiceController(config, MicrophoneManager(config))
    result = voice._transcribe(bytes(16000 * 2), 16000, threading.Event(), SimpleQueue())
    assert result == "", "Silence should not be transcribed as speech"
    print("Local Whisper model loading, WAV decoding and Silero VAD: OK")
