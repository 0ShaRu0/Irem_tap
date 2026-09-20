from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from iram_tap.assets import file_signature, resolve_asset_path
from iram_tap.config.validation import validate_image_size
from iram_tap.geometry import scaled_image_size
from iram_tap.rendering.effects import glow_rings


class PreviewRenderer:
    def __init__(self, config_path: Path) -> None:
        self.config_path = config_path
        self.cache: dict[str, tuple[object, Image.Image]] = {}

    def read_image(self, spec: dict[str, Any]) -> Image.Image | None:
        value = spec.get("path", "")
        if not value:
            return None
        path = resolve_asset_path(value, self.config_path)
        key, modified = str(path), file_signature(path)
        previous = self.cache.get(key)
        try:
            if previous is not None and previous[0] == modified:
                source = previous[1]
            else:
                with Image.open(path) as opened:
                    validate_image_size(*opened.size)
                    source = opened.convert("RGBA").copy()
                self.cache[key] = (modified, source)
            size = scaled_image_size(source.size, spec)
            return source if size == source.size else source.resize(size, Image.Resampling.LANCZOS)
        except (OSError, ValueError):
            return None

    def image_size(self, name: str, spec: dict[str, Any]) -> tuple[int, int]:
        image = self.read_image(spec)
        return image.size if image is not None else (300, 300)

    def draw_layer(self, composition: Image.Image, name: str, spec: dict[str, Any],
                   position: tuple[float, float] | list[float] | None = None) -> None:
        actual = position if position is not None else spec["position"]
        x, y = round(actual[0]), round(actual[1])
        image = self.read_image(spec)
        if image is not None:
            composition.alpha_composite(image, (x, y))
            return
        width, height = self.image_size(name, spec)
        draw = ImageDraw.Draw(composition, "RGBA")
        draw.rectangle((x, y, x + width, y + height), fill=(45, 45, 45, 150),
                       outline=(240, 240, 240, 210), width=2)
        draw.text((x + 5, y + 5), name, fill=(255, 255, 255, 255))

    @staticmethod
    def draw_glow(composition: Image.Image, geometry: tuple[float, float, float, float],
                  color_value: list[int], alpha: int) -> None:
        x, y, width, height = geometry
        overlay = Image.new("RGBA", composition.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay, "RGBA")
        for ring_width, ring_height, ring_alpha in glow_rings(width, height, alpha):
            draw.ellipse((x - ring_width / 2, y - ring_height / 2,
                          x + ring_width / 2, y + ring_height / 2),
                         fill=(*color_value, ring_alpha))
        composition.alpha_composite(overlay)
