from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

from iram_tap.assets import (
    application_directory, default_config_path, resource_directory, resolve_asset_path,
    user_data_directory,
)
from iram_tap.config.defaults import (
    DEFAULT_CONFIG, KEYS, MOUSE_BUTTONS, WINDOW_SCALES, KEY_GLOW_REFERENCE_SIZE,
    MOUSE_GLOW_REFERENCE_SIZE,
)
from iram_tap.config.migrations import rebase_external_paths
from iram_tap.config.validation import normalise_config

logger = logging.getLogger(__name__)


def _migrate_legacy_config(config_path: Path) -> None:
    if not getattr(sys, "frozen", False) or config_path.exists():
        return
    if config_path.resolve() != default_config_path().resolve():
        return
    legacy_path = application_directory() / "config.json"
    if not legacy_path.is_file() or legacy_path.resolve() == config_path.resolve():
        return
    try:
        legacy_config = rebase_external_paths(
            load_config_strict(legacy_path), legacy_path.parent, resource_directory()
        )
        with _config_write_lock(config_path):
            if not config_path.exists():
                _save_config_unlocked(legacy_config, config_path)
    except (OSError, ValueError):
        logger.exception("기존 설정 이전 실패: %s", legacy_path)
    else:
        logger.info("기존 설정 이전 완료: %s", config_path)


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    config_path = Path(path) if path else default_config_path()
    _migrate_legacy_config(config_path)
    try:
        return load_config_strict(config_path)
    except FileNotFoundError:
        logger.info("기본 설정 사용: %s", config_path)
    except (OSError, ValueError):
        logger.exception("설정을 읽을 수 없어 기본값 사용: %s", config_path)
    return normalise_config({})


def load_config_strict(path: str | Path | None = None) -> dict[str, Any]:
    config_path = Path(path) if path else default_config_path()
    with config_path.open("r", encoding="utf-8") as file:
        return normalise_config(json.load(file))


@contextmanager
def _config_write_lock(config_path: Path, timeout: float = 3.0) -> Iterator[None]:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = config_path.with_name(f".{config_path.name}.lock")
    with lock_path.open("a+b") as lock_file:
        lock_file.seek(0, os.SEEK_END)
        if lock_file.tell() == 0:
            lock_file.write(b"0")
            lock_file.flush()
        deadline = time.monotonic() + timeout
        while True:
            try:
                lock_file.seek(0)
                if sys.platform == "win32":
                    import msvcrt
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"설정 파일 잠금 시간 초과: {config_path}") from None
                time.sleep(0.025)
        try:
            yield
        finally:
            lock_file.seek(0)
            if sys.platform == "win32":
                import msvcrt
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _save_config_unlocked(config: dict[str, Any], config_path: Path) -> dict[str, Any]:
    normalised = normalise_config(config)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=config_path.parent, prefix=f".{config_path.name}.", suffix=".tmp"
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as file:
            json.dump(normalised, file, ensure_ascii=False, indent=2, allow_nan=False)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_path, config_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return normalised


def update_config(
    updater: Callable[[dict[str, Any]], dict[str, Any] | None],
    path: str | Path | None = None,
    *,
    repair_invalid: bool = False,
) -> dict[str, Any]:
    config_path = Path(path) if path else default_config_path()
    with _config_write_lock(config_path):
        try:
            current = load_config_strict(config_path)
        except FileNotFoundError:
            current = normalise_config({})
        except (OSError, ValueError):
            if not repair_invalid:
                raise
            # Keep the original bytes before an explicit repair overwrites them.
            if config_path.is_file():
                backup = config_path.with_name(f"{config_path.name}.{time.time_ns()}.bak")
                backup.write_bytes(config_path.read_bytes())
            current = normalise_config({})
        updated = updater(current)
        return _save_config_unlocked(updated if updated is not None else current, config_path)


class ConfigRepository:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else default_config_path()

    def load(self) -> dict[str, Any]:
        return load_config(self.path)

    def update(self, updater: Callable[[dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
        return update_config(updater, self.path)


__all__ = [
    "ConfigRepository", "load_config", "load_config_strict", "update_config", "normalise_config",
    "DEFAULT_CONFIG", "KEYS", "MOUSE_BUTTONS", "WINDOW_SCALES", "KEY_GLOW_REFERENCE_SIZE",
    "MOUSE_GLOW_REFERENCE_SIZE", "default_config_path", "resolve_asset_path", "application_directory",
    "resource_directory", "user_data_directory",
]
