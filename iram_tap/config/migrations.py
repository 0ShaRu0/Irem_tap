from __future__ import annotations

import copy
import hashlib
from pathlib import Path
from typing import Any

from iram_tap.config.defaults import KEYBOARD_IMAGE_DIRECTORY, SCHEMA_VERSION


def migrate_schema(config: Any) -> dict[str, Any]:
    if not isinstance(config, dict):
        raise ValueError("설정 최상위 값은 JSON 객체여야 합니다.")
    result = copy.deepcopy(config)
    version = result.get("schema_version", 0)
    if type(version) is not int or not 0 <= version <= SCHEMA_VERSION:
        raise ValueError(f"지원하지 않는 설정 버전: {version}")
    if version == 0:
        def migrate_path(value: Any) -> Any:
            if not isinstance(value, str):
                return value
            path = value.replace("\\", "/")
            if path in {
                f"image/{name}.png" for name in (
                    "character", "character_open", "desk_keyboard", "right_hand_mouse",
                    "left_hand_idle", "left_hand_pressed", "icon",
                )
            }:
                return f"{KEYBOARD_IMAGE_DIRECTORY}/{Path(path).name}"
            return value

        for key in ("icon_path", "microphone_open_image"):
            if key in result:
                result[key] = migrate_path(result[key])
        images = result.get("images")
        if isinstance(images, dict):
            for spec in images.values():
                if isinstance(spec, dict) and "path" in spec:
                    spec["path"] = migrate_path(spec["path"])
    result["schema_version"] = SCHEMA_VERSION
    return result


def rebase_external_paths(
    config: dict[str, Any], source: Path, resources: Path
) -> dict[str, Any]:
    """Keep bundled defaults portable and preserve custom legacy relative paths."""
    result = copy.deepcopy(config)

    def rebase(value: str) -> str:
        path = Path(value).expanduser()
        if not value or path.is_absolute():
            return value
        local = (source / path).resolve()
        bundled = resources / path
        if local.is_file() and bundled.is_file():
            if hashlib.sha256(local.read_bytes()).digest() == hashlib.sha256(
                bundled.read_bytes()
            ).digest():
                return value
        elif not local.exists() and bundled.is_file():
            return value
        return str(local)

    for key in ("icon_path", "microphone_open_image"):
        result[key] = rebase(result[key])
    for spec in result["images"].values():
        spec["path"] = rebase(spec["path"])
    return result
