from __future__ import annotations

import math
import threading
import time
from contextlib import suppress
from dataclasses import dataclass
from typing import Any


DEFAULT_DEVICE_LABEL = "시스템 기본 입력 장치"


@dataclass(frozen=True)
class MicrophoneSettings:
    enabled: bool
    device: str
    threshold: float
    high_threshold: float
    release_delay: float

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> MicrophoneSettings:
        return cls(
            enabled=bool(config["microphone_enabled"]),
            device=str(config["microphone_device"]),
            threshold=float(config["microphone_threshold"]),
            high_threshold=float(config["microphone_high_threshold"]),
            release_delay=float(config["microphone_release_delay"]),
        )


def _input_device_entries(sounddevice: Any) -> list[tuple[int, str]]:
    host_apis = sounddevice.query_hostapis()
    entries: list[tuple[int, str]] = []
    for index, device in enumerate(sounddevice.query_devices()):
        if int(device["max_input_channels"]) <= 0:
            continue
        host_name = str(host_apis[int(device["hostapi"])]["name"])
        entries.append((index, f'{device["name"]} [{host_name}]'))
    return entries


def input_device_names() -> list[str]:
    try:
        import sounddevice

        entries = _input_device_entries(sounddevice)
    except Exception as error:
        print(f"[microphone] 입력 장치 목록을 불러올 수 없습니다: {error}")
        return []
    return list(dict.fromkeys(label for _index, label in entries))


class MicrophoneManager:
    def __init__(self, config: dict[str, Any]) -> None:
        self._lock = threading.Lock()
        self._stream: Any = None
        self._started = False
        self._active = False
        self._expression_level = 0
        self._last_detected_at: float | None = None
        self._settings = MicrophoneSettings.from_config(config)

    def reconfigure(self, config: dict[str, Any]) -> None:
        settings = MicrophoneSettings.from_config(config)
        with self._lock:
            previous = self._settings
        if settings == previous:
            return
        stream_changed = (
            settings.enabled != previous.enabled or settings.device != previous.device
        )
        if stream_changed:
            self._close_stream()
        # Threshold/timing changes take effect in the next callback without a gap.
        with self._lock:
            self._settings = settings
        if stream_changed and self._started:
            self._open_stream()

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._open_stream()

    def _open_stream(self) -> None:
        with self._lock:
            settings = self._settings
        if not settings.enabled:
            return

        stream: Any = None
        try:
            import sounddevice

            device = None
            if settings.device:
                device = next(
                    (
                        index
                        for index, label in _input_device_entries(sounddevice)
                        if label == settings.device
                    ),
                    None,
                )
                if device is None:
                    print(
                        f"[microphone] 선택한 입력 장치를 찾을 수 없어 기본 장치를 사용합니다: "
                        f"{settings.device}"
                    )
            information = sounddevice.query_devices(device, "input")
            stream = sounddevice.RawInputStream(
                samplerate=float(information["default_samplerate"]),
                blocksize=0,
                device=device,
                channels=1,
                dtype="int16",
                callback=self._audio_callback,
            )
            stream.start()
        except Exception as error:
            self._dispose_stream(stream, stop=False)
            print(f"[microphone] 입력 스트림을 시작할 수 없습니다: {error}")
            return
        self._stream = stream
        print(f'[microphone] 입력 감지 시작: {information["name"]}')

    def _audio_callback(
        self,
        input_data: Any,
        _frames: int,
        _time_info: Any,
        _status: Any,
    ) -> None:
        try:
            samples = memoryview(input_data).cast("h")
            if not samples:
                return
            square_sum = sum(sample * sample for sample in samples)
            level = math.sqrt(square_sum / len(samples)) / 32768.0
        except (TypeError, ValueError):
            return
        self.process_level(level)

    def process_level(self, level: float, now: float | None = None) -> None:
        measured_at = time.monotonic() if now is None else now
        with self._lock:
            settings = self._settings
            if not settings.enabled:
                self._active = False
                self._expression_level = 0
                return
            if level >= settings.high_threshold:
                self._active = True
                self._expression_level = 2
                self._last_detected_at = measured_at
            elif level >= settings.threshold:
                self._active = True
                self._expression_level = 1
                self._last_detected_at = measured_at
            elif (
                self._active
                and self._last_detected_at is not None
                and measured_at - self._last_detected_at >= settings.release_delay
            ):
                self._active = False
                self._expression_level = 0

    def is_active(self) -> bool:
        with self._lock:
            return self._settings.enabled and self._active

    def expression_level(self) -> int:
        with self._lock:
            return self._expression_level if self._settings.enabled else 0

    @staticmethod
    def _dispose_stream(stream: Any, *, stop: bool = True) -> None:
        if stream is None:
            return
        if stop:
            with suppress(Exception):
                stream.stop()
        # A failing stop must still release the device handle.
        with suppress(Exception):
            stream.close()

    def _close_stream(self) -> None:
        stream, self._stream = self._stream, None
        self._dispose_stream(stream)
        with self._lock:
            self._active = False
            self._expression_level = 0
            self._last_detected_at = None

    def stop(self) -> None:
        self._started = False
        self._close_stream()
