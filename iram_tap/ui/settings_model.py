from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from iram_tap.config.repository import ConfigRepository
from iram_tap.config.validation import normalise_config


def merge_changes(
    baseline: dict[str, Any], draft: dict[str, Any], latest: dict[str, Any], prefix: str = ""
) -> dict[str, Any]:
    """Three-way field merge: untouched fields always come from the latest file."""
    result = copy.deepcopy(latest)
    for key, value in draft.items():
        original, current = baseline.get(key), latest.get(key)
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict) and isinstance(original, dict) and isinstance(current, dict):
            result[key] = merge_changes(original, value, current, path)
        elif value != original:
            if current != original and current != value:
                raise ValueError(f"다른 창에서 변경한 설정과 충돌합니다: {path}. 파일을 다시 읽어 주세요.")
            result[key] = copy.deepcopy(value)
    return result


class SettingsModel:
    def __init__(self, config: dict[str, Any]) -> None:
        self.baseline = copy.deepcopy(config)

    def save(self, candidate: dict[str, Any], path: Path) -> dict[str, Any]:
        draft = normalise_config(candidate)
        saved = ConfigRepository(path).update(
            lambda latest: merge_changes(self.baseline, draft, latest)
        )
        self.baseline = copy.deepcopy(saved)
        return saved
