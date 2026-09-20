from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from iram_tap.config.validation import validate_image_size


def scaled_image_size(
    source_size: tuple[int, int], spec: dict[str, Any]
) -> tuple[int, int]:
    source_width, source_height = source_size
    if source_width <= 0 or source_height <= 0:
        raise ValueError("Image dimensions must be positive")
    requested_width = max(0, round(spec["size"][0]))
    requested_height = max(0, round(spec["size"][1]))
    if requested_width == 0 and requested_height == 0:
        validate_image_size(*source_size)
        return source_size
    if not spec.get("keep_aspect", True):
        result = (requested_width or source_width, requested_height or source_height)
        validate_image_size(*result)
        return result

    if requested_width == 0:
        scale = requested_height / source_height
    elif requested_height == 0:
        scale = requested_width / source_width
    else:
        scale = min(requested_width / source_width, requested_height / source_height)
    result = (max(1, round(source_width * scale)), max(1, round(source_height * scale)))
    validate_image_size(*result)
    return result


@dataclass(frozen=True)
class ImageTransform:
    """Convert reference-image coordinates to and from the logical canvas."""

    position: Sequence[float]
    image_size: tuple[int, int]
    reference_size: tuple[int, int]

    @property
    def scale(self) -> tuple[float, float]:
        return (
            self.image_size[0] / self.reference_size[0],
            self.image_size[1] / self.reference_size[1],
        )

    def to_canvas(self, x: float, y: float) -> tuple[float, float]:
        scale_x, scale_y = self.scale
        return self.position[0] + x * scale_x, self.position[1] + y * scale_y

    def to_image(self, x: float, y: float) -> tuple[float, float]:
        scale_x, scale_y = self.scale
        return (x - self.position[0]) / scale_x, (y - self.position[1]) / scale_y

    def glow_geometry(self, spec: dict[str, Any]) -> tuple[float, float, float, float]:
        center_x, center_y = self.to_canvas(*spec["position"])
        scale_x, scale_y = self.scale
        return center_x, center_y, spec["size"][0] * scale_x, spec["size"][1] * scale_y
