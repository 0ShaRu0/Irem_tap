from __future__ import annotations

import copy
from collections.abc import Sequence
from contextlib import contextmanager
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Iterator


KEYS = ("Q", "W", "E", "R", "A", "S", "D", "F", "SPACE")
MOUSE_BUTTONS = ("left", "right")
LAYER_NAMES = ("character", "desk_keyboard", "left_hand", "right_hand")
WINDOW_SCALES = (1.25, 1.5)
KEY_GLOW_REFERENCE_SIZE = (300, 300)
MOUSE_GLOW_REFERENCE_SIZE = (300, 300)
KEYBOARD_IMAGE_DIRECTORY = "image/keybord_Iram"
APPLICATION_NAME = "iram_tap"


def _image(path: str, position: list[int], size: list[int] | None = None) -> dict[str, Any]:
    return {
        "path": path,
        "position": position,
        "size": size or [0, 0],
        "keep_aspect": True,
    }


_KEY_GLOWS = {
    "Q": {"position": [205, 282], "size": [25, 20]},
    "W": {"position": [177, 268], "size": [27, 20]},
    "E": {"position": [148, 253], "size": [27, 19]},
    "R": {"position": [118, 237], "size": [29, 20]},
    "A": {"position": [215, 258], "size": [24, 18]},
    "S": {"position": [189, 243], "size": [24, 17]},
    "D": {"position": [161, 230], "size": [24, 16]},
    "F": {"position": [132, 216], "size": [28, 16]},
    "SPACE": {"position": [183, 215], "size": [56, 18]},
}

_MOUSE_GLOWS = {
    "left": {"position": [42.0, 180.0], "size": [6.6, 5.4]},
    "right": {"position": [48.9, 182.1], "size": [6.6, 5.4]},
}


DEFAULT_CONFIG: dict[str, Any] = {
    "window_width": 300,
    "window_height": 300,
    "window_x": None,
    "window_y": None,
    "window_position_locked": False,
    "fps": 60,
    "always_on_top": True,
    "borderless": True,
    "transparent_background": True,
    "background_color": [0, 0, 0],
    "icon_path": f"{KEYBOARD_IMAGE_DIRECTORY}/icon.png",
    "layer_order": list(LAYER_NAMES),
    "smooth_movement": True,
    "right_hand_speed": 0.32,
    "right_hand_range": [17, 10],
    "microphone_enabled": True,
    "microphone_device": "",
    "microphone_threshold": 0.02,
    "microphone_high_threshold": 0.05,
    "microphone_release_delay": 0.18,
    "microphone_open_image": f"{KEYBOARD_IMAGE_DIRECTORY}/character_open.png",
    "key_glow_color": [255, 220, 72],
    "key_glow_alpha": 210,
    "key_glows": copy.deepcopy(_KEY_GLOWS),
    "mouse_glow_color": [255, 220, 72],
    "mouse_glow_alpha": 210,
    "mouse_glows": copy.deepcopy(_MOUSE_GLOWS),
    "images": {
        "character": _image(
            f"{KEYBOARD_IMAGE_DIRECTORY}/character.png", [0, 0], [300, 300]
        ),
        "desk_keyboard": _image(
            f"{KEYBOARD_IMAGE_DIRECTORY}/desk_keyboard.png", [0, 0], [300, 300]
        ),
        "right_hand_mouse": _image(
            f"{KEYBOARD_IMAGE_DIRECTORY}/right_hand_mouse.png", [0, 0], [300, 300]
        ),
        "left_hand_idle": _image(
            f"{KEYBOARD_IMAGE_DIRECTORY}/left_hand_idle.png", [0, 0], [300, 300]
        ),
        "left_hand_pressed": _image(
            f"{KEYBOARD_IMAGE_DIRECTORY}/left_hand_pressed.png", [0, 0], [300, 300]
        ),
    },
}

_LEGACY_KEYBOARD_ASSETS = {
    f"image/{filename}": f"{KEYBOARD_IMAGE_DIRECTORY}/{filename}"
    for filename in (
        "character.png",
        "character_open.png",
        "desk_keyboard.png",
        "right_hand_mouse.png",
        "left_hand_idle.png",
        "left_hand_pressed.png",
        "icon.png",
    )
}


def _migrate_keyboard_asset_path(path: str) -> str:
    return _LEGACY_KEYBOARD_ASSETS.get(path.replace("\\", "/"), path)


def application_directory() -> Path:
    """Return the directory beside the script or bundled executable."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def resource_directory() -> Path:
    """Return the source or PyInstaller directory containing bundled assets."""
    bundle_directory = getattr(sys, "_MEIPASS", None)
    if bundle_directory:
        return Path(bundle_directory).resolve()
    return Path(__file__).resolve().parent


def user_data_directory() -> Path:
    if not getattr(sys, "frozen", False):
        return application_directory()
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = (
        Path(local_app_data)
        if local_app_data
        else Path.home() / "AppData" / "Local"
    )
    return base / APPLICATION_NAME


def default_config_path() -> Path:
    return user_data_directory() / "config.json"


def _deep_merge(default: Any, loaded: Any) -> Any:
    if isinstance(default, dict):
        source = loaded if isinstance(loaded, dict) else {}
        return {
            key: _deep_merge(value, source.get(key))
            for key, value in default.items()
        }
    return copy.deepcopy(default if loaded is None else loaded)


def _number(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def _integer(value: Any, default: int, minimum: int, maximum: int) -> int:
    return int(round(_number(value, default, minimum, maximum)))


def _optional_integer(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return max(-100000, min(100000, int(round(float(value)))))
    except (TypeError, ValueError):
        return None


def _pair(value: Any, default: Sequence[float], minimum: float = -100000) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        value = default
    return [
        _number(value[0], default[0], minimum, 100000),
        _number(value[1], default[1], minimum, 100000),
    ]


def _normalise_image(spec: Any, default: dict[str, Any]) -> dict[str, Any]:
    merged = _deep_merge(default, spec)
    merged["path"] = str(merged.get("path", default["path"]))
    merged["position"] = _pair(merged.get("position"), default["position"])
    merged["size"] = _pair(merged.get("size"), default["size"], minimum=0)
    merged["keep_aspect"] = bool(merged.get("keep_aspect", True))
    return merged


def _normalise_glow(spec: Any, default: dict[str, Any]) -> dict[str, Any]:
    merged = _deep_merge(default, spec)
    merged["position"] = _pair(merged.get("position"), default["position"])
    merged["size"] = _pair(merged.get("size"), default["size"], minimum=1)
    return merged


def _normalise_color(value: Any, default: list[int]) -> list[int]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        value = default
    return [_integer(channel, 0, 0, 255) for channel in value]


def _normalise_glow_group(config: dict[str, Any], prefix: str) -> None:
    color_key = f"{prefix}_glow_color"
    alpha_key = f"{prefix}_glow_alpha"
    glows_key = f"{prefix}_glows"
    config[color_key] = _normalise_color(config[color_key], DEFAULT_CONFIG[color_key])
    config[alpha_key] = _integer(config[alpha_key], DEFAULT_CONFIG[alpha_key], 0, 255)
    config[glows_key] = {
        name: _normalise_glow(config[glows_key].get(name), default)
        for name, default in DEFAULT_CONFIG[glows_key].items()
    }


def normalise_config(config: Any) -> dict[str, Any]:
    merged = _deep_merge(DEFAULT_CONFIG, config)
    for name, minimum, maximum in (
        ("window_width", 160, 7680),
        ("window_height", 120, 4320),
        ("fps", 10, 240),
    ):
        merged[name] = _integer(merged[name], DEFAULT_CONFIG[name], minimum, maximum)
    merged["window_x"] = _optional_integer(merged.get("window_x"))
    merged["window_y"] = _optional_integer(merged.get("window_y"))
    for name in (
        "window_position_locked",
        "always_on_top",
        "borderless",
        "transparent_background",
        "smooth_movement",
        "microphone_enabled",
    ):
        merged[name] = bool(merged[name])

    merged["background_color"] = _normalise_color(
        merged["background_color"], DEFAULT_CONFIG["background_color"]
    )
    for name in ("icon_path", "microphone_device", "microphone_open_image"):
        merged[name] = str(merged[name])
    for name in ("icon_path", "microphone_open_image"):
        merged[name] = _migrate_keyboard_asset_path(merged[name])

    requested_layers = merged.get("layer_order", [])
    layers: list[str] = []
    if isinstance(requested_layers, list):
        for layer in requested_layers:
            if layer in LAYER_NAMES and layer not in layers:
                layers.append(layer)
    if set(layers) != set(LAYER_NAMES):
        layers = list(LAYER_NAMES)
    merged["layer_order"] = layers

    for name, minimum, maximum in (
        ("right_hand_speed", 0.01, 1.0),
        ("microphone_threshold", 0.0001, 1.0),
        ("microphone_high_threshold", 0.0001, 1.0),
        ("microphone_release_delay", 0.0, 5.0),
    ):
        merged[name] = _number(merged[name], DEFAULT_CONFIG[name], minimum, maximum)
    merged["microphone_high_threshold"] = max(
        merged["microphone_threshold"], merged["microphone_high_threshold"]
    )
    merged["right_hand_range"] = _pair(
        merged.get("right_hand_range"), DEFAULT_CONFIG["right_hand_range"], minimum=0
    )
    for prefix in ("key", "mouse"):
        _normalise_glow_group(merged, prefix)
    images = merged.get("images", {})
    merged["images"] = {
        name: _normalise_image(images.get(name), default)
        for name, default in DEFAULT_CONFIG["images"].items()
    }
    for spec in merged["images"].values():
        spec["path"] = _migrate_keyboard_asset_path(spec["path"])
    return merged


def _migrate_legacy_config(config_path: Path) -> None:
    if not getattr(sys, "frozen", False) or config_path.exists():
        return
    if config_path.resolve() != default_config_path().resolve():
        return

    legacy_path = application_directory() / "config.json"
    if not legacy_path.is_file() or legacy_path.resolve() == config_path.resolve():
        return
    try:
        legacy_config = load_config_strict(legacy_path)
        with _config_write_lock(config_path):
            if config_path.exists():
                return
            _save_config_unlocked(legacy_config, config_path)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"[config] 기존 설정을 이전할 수 없습니다: {error}")
        return
    print(f"[config] 기존 설정을 이전했습니다: {config_path}")


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    config_path = Path(path) if path else default_config_path()
    _migrate_legacy_config(config_path)
    try:
        return load_config_strict(config_path)
    except FileNotFoundError:
        print(f"[config] 설정 파일이 없습니다. 기본값 사용: {config_path}")
    except (OSError, json.JSONDecodeError) as error:
        print(f"[config] 설정 파일을 읽을 수 없습니다. 기본값 사용: {error}")
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
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"설정 파일 잠금 시간 초과: {config_path}")
                time.sleep(0.025)

        try:
            yield
        finally:
            lock_file.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _save_config_unlocked(config: dict[str, Any], config_path: Path) -> dict[str, Any]:
    normalised = normalise_config(config)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=config_path.parent,
        prefix=f".{config_path.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as file:
            json.dump(normalised, file, ensure_ascii=False, indent=2)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_path, config_path)
    finally:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass
    return normalised


def update_config(
    updater: Callable[[dict[str, Any]], dict[str, Any] | None],
    path: str | Path | None = None,
    *,
    repair_invalid: bool = False,
) -> dict[str, Any]:
    """Atomically read, update, and replace a config across app processes."""
    config_path = Path(path) if path else default_config_path()
    with _config_write_lock(config_path):
        try:
            current = load_config_strict(config_path)
        except FileNotFoundError:
            current = normalise_config({})
        except (OSError, json.JSONDecodeError):
            if not repair_invalid:
                raise
            current = normalise_config({})
        updated = updater(current)
        return _save_config_unlocked(updated if updated is not None else current, config_path)


def resolve_asset_path(path_value: str, config_path: str | Path | None = None) -> Path:
    path = Path(path_value).expanduser()
    if path.is_absolute():
        return path.resolve()

    config_candidate: Path | None = None
    if config_path is not None:
        config_candidate = (Path(config_path).resolve().parent / path).resolve()
        if config_candidate.exists():
            return config_candidate

    bundled_candidate = (resource_directory() / path).resolve()
    if bundled_candidate.exists() or config_candidate is None:
        return bundled_candidate
    return config_candidate
