from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

import pygame

TEXT_BUBBLE_AREA_HEIGHT = 140
MAX_LINES = 3
MARGIN = 10
PADDING_X, PADDING_Y, TAIL_HEIGHT = 10, 7, 7
BACKGROUND = (255, 255, 255, 255)
BORDER = (47, 112, 224, 255)


def wrap_text(text: str, measure: Callable[[str], int], width: int, max_lines: int = MAX_LINES) -> list[str]:
    if width <= 0 or max_lines <= 0:
        return []
    lines: list[str] = []
    current = ""
    normalised = text.replace("\r\n", "\n").replace("\r", "\n").replace("\t", " ")
    truncated = False
    for index, character in enumerate(normalised):
        if character == "\n":
            lines.append(current.rstrip())
            current = ""
        elif current and measure(current + character) > width:
            lines.append(current.rstrip())
            current = "" if character.isspace() else character
        else:
            current += character
            continue
        if len(lines) == max_lines:
            truncated = bool(current) or index < len(normalised) - 1
            break
    else:
        if current or not lines:
            lines.append(current.rstrip())
    if truncated:
        suffix = "..."
        while suffix and measure(suffix) > width:
            suffix = suffix[:-1]
        last = lines[-1].rstrip()
        while last and measure(last + suffix) > width:
            last = last[:-1].rstrip()
        lines[-1] = last + suffix
    return lines


class SpeechBubbleRenderer:
    def __init__(self) -> None:
        self._fonts: dict[int, pygame.font.Font] = {}
        self._key: tuple[str, bool, int] | None = None
        self._surface: pygame.Surface | None = None

    def font(self, size: int) -> pygame.font.Font:
        if size not in self._fonts:
            windows_font = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/malgun.ttf"
            path = str(windows_font) if windows_font.is_file() else pygame.font.match_font("malgungothic,arial")
            self._fonts[size] = pygame.font.Font(path, size)
        return self._fonts[size]

    def surface(self, text: str, editing: bool, width: int) -> pygame.Surface:
        key = text, editing, width
        if key == self._key and self._surface is not None:
            return self._surface
        display = f"{text}|" if text and editing else text or "텍스트를 입력하고 Enter"
        font = self.font(max(14, min(22, round(width * 0.073))))
        max_width = max(80, width - MARGIN * 2)
        line_height = font.get_linesize()
        max_lines = max(1, min(MAX_LINES, (TEXT_BUBBLE_AREA_HEIGHT - 2 * MARGIN - 2 * PADDING_Y - TAIL_HEIGHT) // (line_height + 2)))
        lines = wrap_text(display, lambda value: font.size(value)[0], max_width - PADDING_X * 2, max_lines)
        bubble_width = min(max_width, max(80, max(font.size(line)[0] for line in lines) + PADDING_X * 2))
        body_height = PADDING_Y * 2 + line_height * len(lines) + max(0, len(lines) - 1) * 2
        bubble = pygame.Surface((bubble_width, body_height + TAIL_HEIGHT), pygame.SRCALPHA, 32)
        body = pygame.Rect(0, 0, bubble_width, body_height)
        pygame.draw.rect(bubble, BACKGROUND, body, border_radius=11)
        pygame.draw.rect(bubble, BORDER, body, width=2, border_radius=11)
        center = bubble_width // 2
        tail = ((center - 8, body_height - 2), (center, body_height + TAIL_HEIGHT - 1), (center + 8, body_height - 2))
        pygame.draw.polygon(bubble, BACKGROUND, tail)
        pygame.draw.lines(bubble, BORDER, False, tail, width=2)
        color = (30, 48, 76) if text else (105, 120, 144)
        for index, line in enumerate(lines):
            rendered = font.render(line, True, color)
            bubble.blit(rendered, ((bubble_width - rendered.get_width()) // 2, PADDING_Y + index * (line_height + 2)))
        self._key, self._surface = key, bubble
        return bubble

    def draw(self, destination: pygame.Surface, text: str | None, editing: bool) -> None:
        if text is None or (not text and not editing):
            return
        bubble = self.surface(text, editing, destination.get_width())
        destination.blit(bubble, ((destination.get_width() - bubble.get_width()) // 2,
            TEXT_BUBBLE_AREA_HEIGHT - MARGIN - bubble.get_height()))
