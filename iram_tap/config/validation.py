from __future__ import annotations

import copy
import math
from collections.abc import Sequence
from typing import Any

from iram_tap.config.defaults import DEFAULT_CONFIG, LAYER_NAMES
from iram_tap.config.migrations import migrate_schema

MAX_IMAGE_DIMENSION = 4096
MAX_IMAGE_PIXELS = 16_777_216
MAX_GLOW_DIMENSION = 1024


def finite_number(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"{field}: 올바른 숫자를 입력하세요.") from error
    if not math.isfinite(number):
        raise ValueError(f"{field}: NaN이나 무한대는 사용할 수 없습니다.")
    return number


def _number(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        number = finite_number(value, "설정")
    except ValueError:
        # Old configs with non-numeric strings still recover to defaults.
        try:
            parsed = float(value)
        except (TypeError, ValueError, OverflowError):
            return default
        if not math.isfinite(parsed):
            raise
        return default
    return max(minimum, min(maximum, number))


def _integer(value: Any, default: int, minimum: int, maximum: int) -> int:
    return int(round(_number(value, default, minimum, maximum)))


def _boolean(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        if value.casefold() in ("true", "1"):
            return True
        if value.casefold() in ("false", "0"):
            return False
    return default


def _pair(value: Any, default: Sequence[float], minimum: float = -100000) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        value = default
    return [_number(v, d, minimum, 100000) for v, d in zip(value, default, strict=True)]


def validate_image_size(width: float, height: float) -> None:
    if max(width, height) > MAX_IMAGE_DIMENSION or width * height > MAX_IMAGE_PIXELS:
        raise ValueError(f"이미지는 한 변 {MAX_IMAGE_DIMENSION}px 이하로 지정하세요.")


def _merge(default: Any, loaded: Any) -> Any:
    if isinstance(default, dict):
        source = loaded if isinstance(loaded, dict) else {}
        return {key: _merge(value, source.get(key)) for key, value in default.items()}
    return copy.deepcopy(default if loaded is None else loaded)


def _color(value: Any, default: list[int]) -> list[int]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        value = default
    return [_integer(v, 0, 0, 255) for v in value]


def normalise_config(config: Any) -> dict[str, Any]:
    merged = _merge(DEFAULT_CONFIG, migrate_schema(config))
    for name, minimum, maximum in (
        ("window_width", 160, 7680), ("window_height", 120, 4320), ("fps", 10, 240)
    ):
        merged[name] = _integer(merged[name], DEFAULT_CONFIG[name], minimum, maximum)
    for name in ("window_x", "window_y"):
        value = merged[name]
        merged[name] = (
            None if value is None or value == ""
            else int(round(max(-100000, min(100000, finite_number(value, name)))))
        )
    for name in (
        "window_position_locked", "always_on_top", "borderless", "transparent_background",
        "smooth_movement", "microphone_enabled",
    ):
        merged[name] = _boolean(merged[name], DEFAULT_CONFIG[name])
    merged["background_color"] = _color(merged["background_color"], DEFAULT_CONFIG["background_color"])
    for name in ("icon_path", "microphone_device", "microphone_open_image"):
        merged[name] = str(merged[name])
    requested = merged["layer_order"]
    layers = list(dict.fromkeys(x for x in requested if isinstance(x, str) and x in LAYER_NAMES)) if isinstance(requested, list) else []
    merged["layer_order"] = layers if set(layers) == set(LAYER_NAMES) else list(LAYER_NAMES)
    for name, lower, upper in (
        ("right_hand_speed", 0.01, 1.0), ("microphone_threshold", 0.0001, 1.0),
        ("microphone_high_threshold", 0.0001, 1.0), ("microphone_release_delay", 0.0, 5.0),
    ):
        merged[name] = _number(merged[name], DEFAULT_CONFIG[name], lower, upper)
    merged["microphone_high_threshold"] = max(merged["microphone_threshold"], merged["microphone_high_threshold"])
    merged["right_hand_range"] = _pair(merged["right_hand_range"], DEFAULT_CONFIG["right_hand_range"], 0)
    for prefix in ("key", "mouse"):
        color_key, alpha_key, glows_key = f"{prefix}_glow_color", f"{prefix}_glow_alpha", f"{prefix}_glows"
        merged[color_key] = _color(merged[color_key], DEFAULT_CONFIG[color_key])
        merged[alpha_key] = _integer(merged[alpha_key], DEFAULT_CONFIG[alpha_key], 0, 255)
        for name, spec in merged[glows_key].items():
            default = DEFAULT_CONFIG[glows_key][name]
            spec["position"] = _pair(spec["position"], default["position"])
            spec["size"] = _pair(spec["size"], default["size"], 1)
            if max(spec["size"]) > MAX_GLOW_DIMENSION:
                raise ValueError(f"{glows_key}.{name}: 발광 크기가 너무 큽니다.")
    for name, spec in merged["images"].items():
        default = DEFAULT_CONFIG["images"][name]
        spec["path"] = str(spec["path"])
        spec["position"] = _pair(spec["position"], default["position"])
        spec["size"] = _pair(spec["size"], default["size"], 0)
        validate_image_size(*spec["size"])
        spec["keep_aspect"] = _boolean(spec["keep_aspect"], True)
    return merged
