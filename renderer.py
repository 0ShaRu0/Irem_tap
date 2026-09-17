from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pygame

from config_manager import (
    KEY_GLOW_REFERENCE_SIZE,
    MOUSE_GLOW_REFERENCE_SIZE,
    resolve_asset_path,
)
from input_manager import InputSnapshot
from image_geometry import ImageTransform, scaled_image_size


@dataclass
class LoadedImage:
    surface: pygame.Surface | None
    position: tuple[float, float]


DESK_ANGLE_RADIANS = math.radians(26.0)
TEXT_BUBBLE_MAX_LINES = 3
TEXT_BUBBLE_MARGIN = 10
TEXT_BUBBLE_PADDING_X = 10
TEXT_BUBBLE_PADDING_Y = 7
TEXT_BUBBLE_TAIL_HEIGHT = 7


class LayerRenderer:
    def __init__(self, config: dict[str, Any], config_path: str | Path) -> None:
        self.config_path = Path(config_path)
        self.config: dict[str, Any] = {}
        self.canvas: pygame.Surface
        self.images: dict[str, LoadedImage] = {}
        self._reported_asset_errors: set[str] = set()
        self._right_position: list[float] | None = None
        self._selected_character: LoadedImage | None = None
        self._open_character: LoadedImage | None = None
        self._avatar_expressions: tuple[LoadedImage, LoadedImage, LoadedImage] | None = None
        self._microphone_level = 0
        self._glow_cache: dict[tuple[int, int, tuple[int, int, int], int], pygame.Surface] = {}
        self._text_font_path: str | None = None
        self._text_font_cache: dict[int, pygame.font.Font] = {}
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
        self.canvas = pygame.Surface(new_size, pygame.SRCALPHA, 32).convert_alpha()

        previous_character = self._selected_character
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
            self._avatar_expressions = tuple(
                self._load_image(
                    f"avatar_{index}",
                    {**character_spec, "path": path_value},
                )
                for index, path_value in enumerate(avatar_expression_paths)
            )
        self._apply_character_state()
        right = self.images["right_hand_mouse"]
        self._right_position = [right.position[0], right.position[1]]
        self._glow_cache.clear()

    def select_character(
        self, path_value: str, open_path_value: str | None = None
    ) -> bool:
        spec = {**self.config["images"]["character"], "path": path_value}
        character = self._load_image("character", spec)
        if character.surface is None:
            return False
        self._selected_character = character
        self._open_character = self._load_open_character(open_path_value)
        self._avatar_expressions = None
        self._apply_character_state()
        return True

    def _load_open_character(self, path_value: str | None) -> LoadedImage | None:
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

    def _report_asset_error(self, key: str, message: str) -> None:
        if key not in self._reported_asset_errors:
            self._reported_asset_errors.add(key)
            print(message)

    def _load_image(self, name: str, spec: dict[str, Any]) -> LoadedImage:
        position = (float(spec["position"][0]), float(spec["position"][1]))
        path_value = spec.get("path", "")
        if not path_value:
            self._report_asset_error(name, f"[images] 이미지 경로가 비어 있습니다: {name}")
            return LoadedImage(None, position)

        path = resolve_asset_path(path_value, self.config_path)
        if not path.is_file():
            self._report_asset_error(str(path), f"[images] 누락된 이미지: {path}")
            return LoadedImage(None, position)

        try:
            surface = pygame.image.load(str(path)).convert_alpha()
            target_size = scaled_image_size(surface.get_size(), spec)
            if target_size != surface.get_size():
                surface = pygame.transform.smoothscale(surface, target_size)
            return LoadedImage(surface, position)
        except (OSError, ValueError, pygame.error) as error:
            self._report_asset_error(str(path), f"[images] 이미지를 불러올 수 없습니다: {path} ({error})")
            return LoadedImage(None, position)

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
        color = tuple(color_value)
        cache_key = (pixel_width, pixel_height, color, alpha)
        cached = self._glow_cache.get(cache_key)
        if cached is not None:
            return cached

        glow = pygame.Surface((pixel_width, pixel_height), pygame.SRCALPHA, 32)
        for step in range(12, 0, -1):
            fraction = step / 12
            ellipse_width = max(1, round(pixel_width * fraction))
            ellipse_height = max(1, round(pixel_height * fraction))
            rectangle = pygame.Rect(
                (pixel_width - ellipse_width) // 2,
                (pixel_height - ellipse_height) // 2,
                ellipse_width,
                ellipse_height,
            )
            ring_alpha = round(alpha * (1.0 - fraction * 0.72))
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
        cached = self._text_font_cache.get(size)
        if cached is not None:
            return cached
        if self._text_font_path is None:
            malgun_gothic = Path("C:/Windows/Fonts/malgun.ttf")
            self._text_font_path = (
                str(malgun_gothic)
                if malgun_gothic.is_file()
                else pygame.font.match_font("malgungothic,arial") or ""
            )
        font = pygame.font.Font(self._text_font_path or None, size)
        self._text_font_cache[size] = font
        return font

    @staticmethod
    def _wrap_text(
        text: str,
        font: pygame.font.Font,
        max_width: int,
        max_lines: int = TEXT_BUBBLE_MAX_LINES,
    ) -> list[str]:
        lines: list[str] = []
        current = ""
        truncated = False
        normalised = (
            text.replace("\r\n", "\n").replace("\r", "\n").replace("\t", " ")
        )

        for character in normalised:
            if character == "\n":
                lines.append(current.rstrip())
                current = ""
            else:
                candidate = current + character
                if not current or font.size(candidate)[0] <= max_width:
                    current = candidate
                    continue
                lines.append(current.rstrip())
                current = "" if character.isspace() else character

            if len(lines) >= max_lines:
                truncated = True
                break
        else:
            if current or not lines:
                lines.append(current.rstrip())

        if len(lines) > max_lines:
            lines = lines[:max_lines]
            truncated = True
        if truncated:
            ellipsis = "..."
            last_line = lines[-1].rstrip()
            while last_line and font.size(last_line + ellipsis)[0] > max_width:
                last_line = last_line[:-1].rstrip()
            lines[-1] = last_line + ellipsis
        return lines

    def _draw_text_bubble(self, text: str | None, editing: bool) -> None:
        if text is None or (not text and not editing):
            return

        display_text = (
            f"{text}|" if text and editing else text or "텍스트를 입력하고 Enter"
        )
        font_size = max(14, min(22, round(self.canvas.get_width() * 0.073)))
        font = self._text_font(font_size)
        max_bubble_width = max(80, self.canvas.get_width() - TEXT_BUBBLE_MARGIN * 2)
        max_text_width = max_bubble_width - TEXT_BUBBLE_PADDING_X * 2
        lines = self._wrap_text(display_text, font, max_text_width)
        line_height = font.get_linesize()
        content_width = max(font.size(line)[0] for line in lines)
        bubble_width = min(
            max_bubble_width,
            max(80, content_width + TEXT_BUBBLE_PADDING_X * 2),
        )
        body_height = (
            TEXT_BUBBLE_PADDING_Y * 2
            + line_height * len(lines)
            + max(0, len(lines) - 1) * 2
        )
        bubble = pygame.Surface(
            (bubble_width, body_height + TEXT_BUBBLE_TAIL_HEIGHT),
            pygame.SRCALPHA,
            32,
        )
        body = pygame.Rect(0, 0, bubble_width, body_height)
        pygame.draw.rect(bubble, (18, 22, 30, 218), body, border_radius=11)
        pygame.draw.rect(
            bubble,
            (255, 255, 255, 185),
            body,
            width=1,
            border_radius=11,
        )
        center_x = bubble_width // 2
        pygame.draw.polygon(
            bubble,
            (18, 22, 30, 218),
            (
                (center_x - 7, body_height - 1),
                (center_x + 7, body_height - 1),
                (center_x, body_height + TEXT_BUBBLE_TAIL_HEIGHT - 1),
            ),
        )

        text_color = (255, 255, 255) if text else (200, 206, 216)
        y = TEXT_BUBBLE_PADDING_Y
        for line in lines:
            foreground = font.render(line, True, text_color)
            outline = font.render(line, True, (0, 0, 0))
            x = (bubble_width - foreground.get_width()) // 2
            for offset_x, offset_y in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                bubble.blit(outline, (x + offset_x, y + offset_y))
            bubble.blit(foreground, (x, y))
            y += line_height + 2

        self.canvas.blit(
            bubble,
            ((self.canvas.get_width() - bubble_width) // 2, TEXT_BUBBLE_MARGIN),
        )

    def render(
        self,
        snapshot: InputSnapshot,
        delta_time: float,
        cursor_ratio: tuple[float, float] | None = None,
        *,
        text_overlay: str | None = None,
        text_editing: bool = False,
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
        self._draw_text_bubble(text_overlay, text_editing)
        return self.canvas
