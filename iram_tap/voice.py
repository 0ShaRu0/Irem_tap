"""F11 record -> local transcription -> Fish Audio -> selected PortAudio output.

Only the main thread changes controller state. Workers publish status through a
queue; a per-job cancellation event prevents stale results from being played.
"""
from __future__ import annotations

import io
import json
from collections.abc import Callable
from pathlib import Path
from queue import Empty, SimpleQueue
import threading
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import wave

from iram_tap.assets import user_data_directory
from iram_tap.config.secrets import unprotect_key
from iram_tap.platform.audio import MicrophoneManager
from iram_tap.playback_activity import PlaybackActivity


DEFAULT_OUTPUT = "시스템 기본 출력 장치"
OUTPUT_MODES = {"local": "스피커·헤드셋", "virtual": "가상 오디오"}
FISH_FIELDS = ("fish_api_key_protected", "fish_reference_id", "fish_model",
               "fish_output_mode", "fish_local_device", "fish_virtual_device", "fish_volume",
               "microphone_device", "microphone_enabled")


def output_devices(audio: Any = None) -> list[tuple[int, str]]:
    if audio is None:
        import sounddevice
        audio = sounddevice
    hosts = audio.query_hostapis()
    return [(index, f'{device["name"]} [{hosts[int(device["hostapi"])]["name"]}]')
            for index, device in enumerate(audio.query_devices())
            if int(device["max_output_channels"]) > 0]


def resolve_output(config: dict[str, Any], audio: Any) -> int | None:
    mode = config["fish_output_mode"]
    name = config[f"fish_{mode}_device"]
    if not name:
        if mode == "virtual":
            raise ValueError("설정에서 가상 오디오 출력 장치를 선택하세요.")
        return None
    for index, label in output_devices(audio):
        if label == name:
            return index
    raise ValueError("선택한 출력 장치가 없습니다. 설정에서 장치를 다시 선택하세요.")


def synthesize(text: str, key: str, config: dict[str, Any], cancel: threading.Event) -> bytes:
    request = Request("https://api.fish.audio/v1/tts", method="POST", headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json",
        "model": config["fish_model"],
    }, data=json.dumps({"text": text, "reference_id": config["fish_reference_id"],
                       "format": "pcm", "sample_rate": 44100}).encode("utf-8"))
    try:
        with urlopen(request, timeout=45) as response:
            chunks = []
            size = 0
            deadline = time.monotonic() + 90
            while not cancel.is_set():
                chunk = response.read(8192)
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
                if size > 44100 * 2 * 120 or time.monotonic() > deadline:
                    raise ValueError("음성 응답이 너무 길거나 지연되었습니다. 짧게 다시 녹음하세요.")
            result = b"".join(chunks)
            if not cancel.is_set() and (not result or len(result) % 2):
                raise ValueError("Fish Audio에서 올바른 음성 데이터를 받지 못했습니다.")
            return result
    except HTTPError as error:
        messages = {401: "API 키 인증 실패", 403: "API 사용 권한이 없습니다",
                    402: "Fish Audio 잔액이 부족합니다", 429: "요청 한도를 초과했습니다",
                    400: "목소리 ID와 모델 설정을 확인하세요", 404: "목소리 ID를 확인하세요",
                    422: "목소리 ID와 모델 설정을 확인하세요"}
        raise ValueError(messages.get(error.code, f"Fish Audio 서버 오류 ({error.code})")) from None
    except (URLError, TimeoutError, OSError):
        raise ValueError("Fish Audio 연결 실패 또는 시간 초과. 인터넷 연결을 확인하세요.") from None


def play_pcm(pcm: bytes, config: dict[str, Any], cancel: threading.Event,
             on_level: Callable[[float], None] | None = None) -> None:
    import numpy as np
    import sounddevice as audio

    if cancel.is_set():
        return
    device = resolve_output(config, audio)
    info = audio.query_devices(device, "output")
    rate = int(info["default_samplerate"])
    channels = min(2, int(info["max_output_channels"]))
    samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768
    if rate != 44100 and len(samples):
        count = max(1, round(len(samples) * rate / 44100))
        samples = np.interp(np.arange(count) * 44100 / rate,
                            np.arange(len(samples)), samples).astype(np.float32)
    samples *= config["fish_volume"]
    samples = np.repeat(samples[:, None], channels, axis=1)
    if cancel.is_set():
        return
    # Small blocking writes bound cancellation latency without global sd.stop().
    try:
        with audio.OutputStream(device=device, samplerate=rate, channels=channels,
                                dtype="float32", blocksize=0, latency="low") as stream:
            chunk_size = max(1, rate // 50)
            for offset in range(0, len(samples), chunk_size):
                if cancel.is_set():
                    stream.abort()
                    return
                chunk = samples[offset:offset + chunk_size]
                stream.write(chunk)
                if on_level is not None:
                    on_level(float(np.sqrt(np.mean(chunk ** 2))))
    finally:
        if on_level is not None:
            on_level(0.0)


class VoiceController:
    def __init__(self, config: dict[str, Any], microphone: MicrophoneManager,
                 config_path: Path | None = None) -> None:
        self.config = dict(config)
        self.microphone = microphone
        self.state = "idle"
        self.status = ""
        self._until = 0.0
        self._started_at = 0.0
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None
        self._messages: SimpleQueue[tuple[str, str]] = SimpleQueue()
        self._model: Any = None
        self.activity = PlaybackActivity(config_path)
        self._success_message = "재생 완료"

    def expression_level(self) -> int | None:
        """None means idle microphone animation; busy speech never uses the mic."""
        amplitude = self.activity.read()
        if amplitude is not None:
            if amplitude >= self.config["microphone_high_threshold"]:
                return 2
            if amplitude >= self.config["microphone_threshold"]:
                return 1
            return 0
        if self.state != "idle":
            return 0
        return None

    def _set(self, state: str, message: str) -> None:
        self.state, self.status = state, message
        self._until = time.monotonic() + 8

    def reconfigure(self, config: dict[str, Any]) -> None:
        if any(self.config.get(key) != config.get(key) for key in FISH_FIELDS):
            self.stop()
        self.config = dict(config)

    def toggle(self) -> None:
        self.poll()
        if self.state == "recording":
            self._finish_recording()
        elif self._thread is not None and self._thread.is_alive():
            self._cancel.set()
            self._set("cancelling", "음성 작업 취소 중…")
        else:
            try:
                self._validate()
                self.microphone.begin_recording()
                self._started_at = time.monotonic()
                self._set("recording", "녹음 중 · F11 종료 (최대 30초)")
            except (ValueError, OSError) as error:
                self._set("idle", str(error))

    def _validate(self) -> None:
        unprotect_key(self.config["fish_api_key_protected"])
        if not self.config["fish_reference_id"].strip():
            raise ValueError("설정에서 Fish Audio 목소리 ID를 입력하세요.")
        import sounddevice
        try:
            device = resolve_output(self.config, sounddevice)
            sounddevice.query_devices(device, "output")
        except sounddevice.PortAudioError:
            raise ValueError("출력 장치를 열 수 없습니다. 연결과 설정을 확인하세요.") from None

    def _finish_recording(self) -> None:
        try:
            pcm, rate = self.microphone.end_recording()
            import numpy as np
            samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32)
            if len(samples) < rate // 5 or float(np.sqrt(np.mean(samples ** 2))) < 100:
                self._set("idle", "음성이 감지되지 않았습니다. 다시 녹음하세요.")
                return
            self._launch(pcm, rate, None)
        except (ValueError, OSError) as error:
            self._set("idle", str(error))

    def test_voice(self) -> None:
        self.poll()
        if self.state == "recording" or (self._thread and self._thread.is_alive()):
            self.stop()
            return
        try:
            self._validate()
            if self.config["fish_volume"] <= 0:
                raise ValueError("음량을 올린 뒤 연결 테스트를 실행하세요.")
            self._launch(b"", 16000, "fish audio 테스트")
        except (ValueError, OSError) as error:
            self._set("idle", str(error))

    def _launch(self, pcm: bytes, rate: int, text: str | None) -> None:
        self._cancel = threading.Event()
        self._messages = SimpleQueue()
        self._success_message = "API 키·목소리 ID 연결 및 테스트 재생 완료" if text is not None else "재생 완료"
        self._set("working", "음성 변환 중 · F11 취소")
        self._thread = threading.Thread(target=self._work,
            args=(pcm, rate, text, dict(self.config), self._cancel, self._messages),
            name="iram_voice", daemon=True)
        self._thread.start()

    def _transcribe(self, pcm: bytes, rate: int, cancel: threading.Event,
                    messages: SimpleQueue[tuple[str, str]]) -> str:
        if self._model is None:
            messages.put(("working", "음성 인식 모델 준비 중 (최초 다운로드)…"))
            from faster_whisper import WhisperModel
            self._model = WhisperModel("base", device="cpu", compute_type="int8",
                                      download_root=str(user_data_directory() / "speech-models"))
        if cancel.is_set():
            return ""
        messages.put(("working", "한국어 음성 인식 중…"))
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(rate)
            wav.writeframes(pcm)
        buffer.seek(0)
        segments, _ = self._model.transcribe(buffer, language="ko", beam_size=3,
                                             vad_filter=True, condition_on_previous_text=False)
        words = []
        for segment in segments:
            if cancel.is_set():
                return ""
            words.append(segment.text)
        return "".join(words).strip()

    def _work(self, pcm: bytes, rate: int, text: str | None, config: dict[str, Any],
              cancel: threading.Event, messages: SimpleQueue[tuple[str, str]]) -> None:
        try:
            if text is None:
                text = self._transcribe(pcm, rate, cancel, messages)
            if cancel.is_set():
                return
            if not text:
                raise ValueError("인식된 말이 없습니다. 다시 녹음하세요.")
            messages.put(("working", "Fish Audio 음성 생성 중…"))
            result = synthesize(text, unprotect_key(config["fish_api_key_protected"]), config, cancel)
            if cancel.is_set():
                return
            messages.put(("playing", f'{OUTPUT_MODES[config["fish_output_mode"]]} 재생 중 · F11 취소'))
            play_pcm(result, config, cancel, self.activity.publish)
        except ValueError as error:
            messages.put(("error", str(error)))
        except Exception:
            # Never log credentials, request bodies, or transcribed speech.
            messages.put(("error", "음성 처리 실패. 인식 모델 다운로드/인터넷/오디오 장치를 확인하세요."))
        finally:
            self.activity.publish(0.0)
            messages.put(("done", ""))

    def poll(self) -> None:
        if self.state == "recording" and time.monotonic() - self._started_at >= 30:
            self._finish_recording()
        while True:
            try:
                state, message = self._messages.get_nowait()
            except Empty:
                break
            if self._cancel.is_set():
                if state == "done":
                    self._set("idle", "음성 작업을 취소했습니다.")
                continue
            if state == "done":
                if self.state != "error":
                    self._set("idle", self._success_message)
                else:
                    self.state = "idle"
            else:
                self._set(state, message)
        if self.state == "idle" and time.monotonic() > self._until:
            self.status = ""

    def stop(self) -> None:
        self._cancel.set()
        self.microphone.discard_recording()
        busy = self._thread is not None and self._thread.is_alive()
        self._set("cancelling" if busy else "idle", "음성 작업을 취소했습니다.")

    def close(self) -> None:
        self.stop()
        self.activity.close()
