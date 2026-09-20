from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pygame

from iram_tap.config.repository import (
    KEY_GLOW_REFERENCE_SIZE,
    MOUSE_GLOW_REFERENCE_SIZE,
)
from iram_tap.models import InputSnapshot
from iram_tap.geometry import ImageTransform
from iram_tap.rendering.images import ImageCache, LoadedImage
from iram_tap.rendering.effects import glow_rings
from iram_tap.rendering.speech_bubble import SpeechBubbleRenderer, TEXT_BUBBLE_AREA_HEIGHT, wrap_text


DESK_ANGLE_RADIANS = math.radians(26.0)


class LayerRenderer:
    def __init__(self, config: dict[str, Any], config_path: str | Path) -> None:
        self.config_path = Path(config_path)
        self.config: dict[str, Any] = {}
        self.canvas: pygame.Surface
        self.images: dict[str, LoadedImage] = {}
        self._image_cache = ImageCache(self.config_path)
        self._right_position: list[float] | None = None
        self._selected_character: LoadedImage | None = None
        self._open_character: LoadedImage | None = None
        self._open_path: str | None = None
        self._avatar_expressions: tuple[LoadedImage, LoadedImage, LoadedImage] | None = None
        self._microphone_level = 0
        self._glow_cache: dict[tuple[int, int, tuple[int, int, int], int], pygame.Surface] = {}
        self.speech_bubble = SpeechBubbleRenderer()
        self.reload_config(config)

    def reload_config(
        self,
        config: dict[str, Any],
        *,
        selected_character_path: str | None = None,
        selected_character_open_path: str | None = None,
        avatar_expression_paths: tuple[str, str, str] | None = None,
    ) -> None:
        self.config = config
        new_size = (self.config["window_width"], self.config["window_height"])
        if not hasattr(self, "canvas") or self.canvas.get_size() != new_size:
            self.canvas = pygame.Surface(new_size, pygame.SRCALPHA, 32).convert_alpha()
            self._text_canvas = pygame.Surface(
                (new_size[0], new_size[1] + TEXT_BUBBLE_AREA_HEIGHT),
                pygame.SRCALPHA, 32,
            ).convert_alpha()

        previous_character = self._selected_character
        previous_right = self.images.get("right_hand_mouse")
        self.images = {}
        for name, spec in self.config["images"].items():
            if name == "character" and selected_character_path is not None:
                spec = {**spec, "path": selected_character_path}
            self.images[name] = self._load_image(name, spec)
        if self.images["character"].surface is None and previous_character is not None:
            self.images["character"] = previous_character
        self._selected_character = self.images["character"]
        open_path = (
            self.config["microphone_open_image"]
            if selected_character_path is None
            else selected_character_open_path
        )
        self._open_character = self._load_open_character(open_path)
        self._avatar_expressions = None
        if avatar_expression_paths is not None:
            character_spec = self.config["images"]["character"]
            expressions = tuple(
                self._load_image(
                    f"avatar_{index}",
                    {**character_spec, "path": path_value},
                )
                for index, path_value in enumerate(avatar_expression_paths)
            )
            self._avatar_expressions = (expressions[0], expressions[1], expressions[2])
        self._image_cache.retain(set(self.images) | {"character_open"} | (
            {"avatar_0", "avatar_1", "avatar_2"} if avatar_expression_paths else set()
        ))
        self._apply_character_state()
        right = self.images["right_hand_mouse"]
        if self._right_position is None or previous_right is None or previous_right.position != right.position:
            self._right_position = [right.position[0], right.position[1]]
        self._glow_cache.clear()

    def select_character(
        self, path_value: str, open_path_value: str | None = None
    ) -> bool:
        spec = {**self.config["images"]["character"], "path": path_value}
        character = self._load_image("character", spec)
        if character.surface is None or "character" in self._image_cache.failed:
            return False
        self._selected_character = character
        self._open_character = self._load_open_character(open_path_value)
        self._avatar_expressions = None
        self._apply_character_state()
        return True

    def _load_open_character(self, path_value: str | None) -> LoadedImage | None:
        if path_value != self._open_path:
            self._image_cache.forget("character_open")
            self._open_path = path_value
        if path_value is None:
            return None
        spec = {**self.config["images"]["character"], "path": path_value}
        return self._load_image("character_open", spec)

    def set_microphone_active(self, active: bool) -> None:
        self.set_microphone_level(1 if active else 0)

    def set_microphone_level(self, level: int) -> None:
        level = max(0, min(2, int(level)))
        if self._microphone_level == level:
            return
        self._microphone_level = level
        self._apply_character_state()

    def _apply_character_state(self) -> None:
        if self._avatar_expressions is not None:
            level = self._microphone_level
            character = self._avatar_expressions[level]
            if character.surface is None:
                character = next(
                    (
                        candidate
                        for candidate in reversed(self._avatar_expressions[:level])
                        if candidate.surface is not None
                    ),
                    self._avatar_expressions[0],
                )
            self.images["character"] = character
            return
        if self._selected_character is None:
            return
        character = self._selected_character
        if (
            self._microphone_level > 0
            and self._open_character is not None
            and self._open_character.surface is not None
        ):
            character = self._open_character
        self.images["character"] = character

    def _load_image(self, name: str, spec: dict[str, Any]) -> LoadedImage:
        return self._image_cache.load(name, spec)

    @property
    def pending_assets(self) -> bool:
        return bool(self._image_cache.failed)

    def _lerp_position(
        self,
        current: list[float],
        target: tuple[float, float] | list[float],
        speed: float,
        delta_time: float,
    ) -> None:
        if not self.config["smooth_movement"]:
            current[0], current[1] = target[0], target[1]
            return
        frames = max(0.0, min(delta_time, 0.1) * self.config["fps"])
        alpha = 1.0 - math.pow(1.0 - speed, frames)
        current[0] += (target[0] - current[0]) * alpha
        current[1] += (target[1] - current[1]) * alpha

    @staticmethod
    def _blit(
        destination: pygame.Surface,
        source: pygame.Surface | None,
        position: tuple[float, float] | list[float],
    ) -> None:
        if source is not None:
            destination.blit(source, (round(position[0]), round(position[1])))

    def _glow_surface(
        self,
        width: float,
        height: float,
        color_value: list[int],
        alpha: int,
    ) -> pygame.Surface:
        pixel_width = max(1, round(width))
        pixel_height = max(1, round(height))
        color = (color_value[0], color_value[1], color_value[2])
        cache_key = (pixel_width, pixel_height, color, alpha)
        cached = self._glow_cache.get(cache_key)
        if cached is not None:
            return cached

        glow = pygame.Surface((pixel_width, pixel_height), pygame.SRCALPHA, 32)
        for width_value, height_value, ring_alpha in glow_rings(pixel_width, pixel_height, alpha):
            ellipse_width = max(1, round(width_value))
            ellipse_height = max(1, round(height_value))
            rectangle = pygame.Rect(
                (pixel_width - ellipse_width) // 2,
                (pixel_height - ellipse_height) // 2,
                ellipse_width,
                ellipse_height,
            )
            pygame.draw.ellipse(glow, (*color, ring_alpha), rectangle)
        self._glow_cache[cache_key] = glow
        return glow

    def _draw_key_glows(
        self,
        pressed_keys: frozenset[str],
        keyboard: LoadedImage,
    ) -> None:
        image_size = (
            keyboard.surface.get_size() if keyboard.surface else KEY_GLOW_REFERENCE_SIZE
        )
        self._draw_glows(
            pressed_keys,
            "key",
            ImageTransform(keyboard.position, image_size, KEY_GLOW_REFERENCE_SIZE),
        )

    def _draw_mouse_button_glows(
        self,
        right: LoadedImage,
        position: tuple[float, float] | list[float],
        pressed_buttons: frozenset[str],
    ) -> None:
        if right.surface is None:
            return
        self._draw_glows(
            pressed_buttons,
            "mouse",
            ImageTransform(position, right.surface.get_size(), MOUSE_GLOW_REFERENCE_SIZE),
        )

    def _draw_glows(
        self, pressed: frozenset[str], prefix: str, transform: ImageTransform
    ) -> None:
        for name in pressed:
            spec = self.config[f"{prefix}_glows"].get(name)
            if spec is None:
                continue
            center_x, center_y, width, height = transform.glow_geometry(spec)
            self._blit(
                self.canvas,
                self._glow_surface(
                    width,
                    height,
                    self.config[f"{prefix}_glow_color"],
                    self.config[f"{prefix}_glow_alpha"],
                ),
                (center_x - width / 2, center_y - height / 2),
            )

    def _right_target(
        self, cursor_ratio: tuple[float, float] | None
    ) -> tuple[float, float]:
        base_x, base_y = self.images["right_hand_mouse"].position
        if cursor_ratio is None:
            return base_x, base_y
        range_x, range_y = self.config["right_hand_range"]
        hand_ratio_x = 1.0 - max(0.0, min(1.0, cursor_ratio[0]))
        hand_ratio_y = 1.0 - max(0.0, min(1.0, cursor_ratio[1]))
        movement_x = (hand_ratio_x * 2.0 - 1.0) * range_x
        movement_y = (hand_ratio_y * 2.0 - 1.0) * range_y
        cosine = math.cos(DESK_ANGLE_RADIANS)
        sine = math.sin(DESK_ANGLE_RADIANS)
        return (
            base_x + movement_x * cosine - movement_y * sine,
            base_y + movement_x * sine + movement_y * cosine,
        )

    def _text_font(self, size: int) -> pygame.font.Font:
        return self.speech_bubble.font(size)

    @staticmethod
    def _wrap_text(
        text: str,
        font: pygame.font.Font,
        max_width: int,
        max_lines: int = 3,
    ) -> list[str]:
        return wrap_text(text, lambda value: font.size(value)[0], max_width, max_lines)

    def _draw_text_bubble(
        self, destination: pygame.Surface, text: str | None, editing: bool
    ) -> None:
        self.speech_bubble.draw(destination, text, editing)

    def render(
        self,
        snapshot: InputSnapshot,
        delta_time: float,
        cursor_ratio: tuple[float, float] | None = None,
        *,
        text_overlay: str | None = None,
        text_editing: bool = False,
        reserve_text_space: bool = False,
    ) -> pygame.Surface:
        if self.config["transparent_background"]:
            self.canvas.fill((0, 0, 0, 0))
        else:
            self.canvas.fill((*self.config["background_color"], 255))

        if self._avatar_expressions is not None:
            character = self.images["character"]
            self._blit(self.canvas, character.surface, character.position)
        else:
            idle = self.images["left_hand_idle"]
            pressed = self.images["left_hand_pressed"]
            left = (
                pressed
                if snapshot.pressed_keys and pressed.surface is not None
                else idle
            )
            desk_keyboard = self.images["desk_keyboard"]

            right = self.images["right_hand_mouse"]
            assert self._right_position is not None
            self._lerp_position(
                self._right_position,
                self._right_target(cursor_ratio),
                self.config["right_hand_speed"],
                delta_time,
            )

            for layer in self.config["layer_order"]:
                if layer == "left_hand":
                    self._draw_key_glows(snapshot.pressed_keys, desk_keyboard)
                    self._blit(self.canvas, left.surface, left.position)
                elif layer == "right_hand":
                    self._blit(self.canvas, right.surface, self._right_position)
                    if snapshot.pressed_mouse_buttons:
                        self._draw_mouse_button_glows(
                            right,
                            self._right_position,
                            snapshot.pressed_mouse_buttons,
                        )
                else:
                    loaded = self.images.get(layer)
                    if loaded is not None:
                        self._blit(self.canvas, loaded.surface, loaded.position)
        if reserve_text_space or text_overlay or text_editing:
            background = (
                (0, 0, 0, 0)
                if self.config["transparent_background"]
                else (*self.config["background_color"], 255)
            )
            self._text_canvas.fill(background)
            self._text_canvas.blit(self.canvas, (0, TEXT_BUBBLE_AREA_HEIGHT))
            self._draw_text_bubble(self._text_canvas, text_overlay, text_editing)
            return self._text_canvas
        return self.canvas
