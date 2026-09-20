from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pygame
from PIL import Image

from iram_tap.assets import file_signature, resolve_asset_path
from iram_tap.config.validation import validate_image_size
from iram_tap.geometry import scaled_image_size
from iram_tap.models import ImageSpec

logger = logging.getLogger(__name__)


@dataclass
class LoadedImage:
    surface: pygame.Surface | None
    position: tuple[float, float]


class ImageCache:
    """Only publish fully decoded images; retain the last good layer on failure."""

    def __init__(self, config_path: Path) -> None:
        self.config_path = config_path
        self._entries: dict[str, tuple[object, pygame.Surface]] = {}
        self.failed: set[str] = set()
        self._reported: dict[str, object] = {}

    def load(self, name: str, mapping: dict[str, Any]) -> LoadedImage:
        spec = ImageSpec(
            str(mapping["path"]), tuple(mapping["position"]),
            tuple(mapping["size"]), bool(mapping["keep_aspect"]),
        )
        path = resolve_asset_path(spec.path, self.config_path)
        signature = file_signature(path)
        key = (str(path), signature, spec.size, spec.keep_aspect)
        previous = self._entries.get(name)
        if previous is not None and previous[0] == key and name not in self.failed:
            return LoadedImage(previous[1], spec.position)
        try:
            if not spec.path:
                raise ValueError("빈 이미지 경로")
            # Check header dimensions before SDL allocates the decoded bitmap.
            with Image.open(path) as header:
                validate_image_size(*header.size)
            surface = pygame.image.load(str(path)).convert_alpha()
            target_size = scaled_image_size(surface.get_size(), mapping)
            if target_size != surface.get_size():
                surface = pygame.transform.smoothscale(surface, target_size)
        except (OSError, ValueError, pygame.error) as error:
            self.failed.add(name)
            if self._reported.get(name) != key:
                logger.warning("이미지 로딩 실패, 최근 정상 이미지 유지: %s (%s)", path, error)
                self._reported[name] = key
            return LoadedImage(previous[1] if previous else None, spec.position)
        self._entries[name] = (key, surface)
        self.failed.discard(name)
        self._reported.pop(name, None)
        return LoadedImage(surface, spec.position)

    def retain(self, names: set[str]) -> None:
        for name in set(self._entries) - names:
            del self._entries[name]
        self.failed.intersection_update(names)
        self._reported = {name: key for name, key in self._reported.items() if name in names}

    def forget(self, name: str) -> None:
        self._entries.pop(name, None)
        self.failed.discard(name)
        self._reported.pop(name, None)
