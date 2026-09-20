from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


KEYS = ("Q", "W", "E", "R", "A", "S", "D", "F", "SPACE")
MOUSE_BUTTONS = ("left", "right")
WINDOW_SCALES = (1.25, 1.5)


class Action(str, Enum):
    TOGGLE_LOCK = "toggle_position_lock"
    TOGGLE_TEXT = "toggle_text_mode"
    TOGGLE_VISIBILITY = "toggle_visibility"
    TOGGLE_TOPMOST = "toggle_topmost"
    OPEN_SETTINGS = "open_settings"
    OPEN_LOGS = "open_logs"
    NEXT_MODE = "next_mode"
    PREVIOUS_MODE = "previous_mode"
    SELECT_CHARACTER = "select_character"
    RESIZE = "resize"
    QUIT = "quit"


@dataclass(frozen=True)
class Command:
    action: Action
    value: int | float | None = None

    @classmethod
    def parse(cls, value: str | Command) -> Command:
        """Accept legacy commands at the public boundary during migration."""
        if isinstance(value, Command):
            return value
        name, separator, argument = value.partition(":")
        action = Action(name)
        if action is Action.SELECT_CHARACTER and separator:
            number = int(argument)
            if number not in range(10):
                raise ValueError("Character number must be between 0 and 9")
            return cls(action, number)
        if action is Action.RESIZE and separator:
            scale = float(argument)
            if scale not in WINDOW_SCALES:
                raise ValueError("Unsupported window scale")
            return cls(action, scale)
        if separator or action in (Action.SELECT_CHARACTER, Action.RESIZE):
            raise ValueError("Invalid command argument")
        return cls(action)


@dataclass(frozen=True)
class InputSnapshot:
    pressed_keys: frozenset[str]
    mouse_position: tuple[float, float] | None
    pressed_mouse_buttons: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class ImageSpec:
    path: str
    position: tuple[float, float]
    size: tuple[float, float]
    keep_aspect: bool


@dataclass(frozen=True)
class WindowState:
    visible: bool = True
    topmost: bool = True
    position_locked: bool = False
    scale: float = 1.0
