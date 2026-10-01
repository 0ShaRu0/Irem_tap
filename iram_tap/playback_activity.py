"""Share only playback amplitude between the settings process and overlay."""
from __future__ import annotations

import hashlib
import math
import mmap
import os
from pathlib import Path
import struct
import threading
import time


class PlaybackActivity:
    _record = struct.Struct("dd")
    MAX_AGE = 0.3

    def __init__(self, config_path: Path | None = None) -> None:
        self._lock = threading.Lock()
        self._data = bytes(self._record.size)
        self._mapping: mmap.mmap | None = None
        self._closed = False
        if config_path is not None and os.name == "nt":
            identity = os.path.normcase(str(config_path.resolve())).encode("utf-8")
            name = "Local\\iram_tap_playback_" + hashlib.sha256(identity).hexdigest()
            self._mapping = mmap.mmap(-1, self._record.size, tagname=name)

    def publish(self, amplitude: float) -> None:
        with self._lock:
            if self._closed:
                return
            self._data = self._record.pack(time.monotonic(), amplitude)
            if self._mapping is not None:
                self._mapping[:] = self._data

    def read(self) -> float | None:
        with self._lock:
            if self._closed:
                return None
            data = self._mapping[:] if self._mapping is not None else self._data
        timestamp, amplitude = self._record.unpack(data)
        if (timestamp <= 0 or not math.isfinite(amplitude) or not 0 <= amplitude <= 1
                or not 0 <= time.monotonic() - timestamp <= self.MAX_AGE):
            return None
        return amplitude

    def close(self) -> None:
        with self._lock:
            self._closed = True
            if self._mapping is not None:
                self._mapping.close()
                self._mapping = None
