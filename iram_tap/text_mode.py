from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

MAX_TEXT_LENGTH = 500


class TextPhase(Enum):
    OFF = auto()
    EDITING = auto()
    PINNED = auto()


@dataclass
class TextMode:
    phase: TextPhase = TextPhase.OFF
    value: str = ""
    composition: str = ""
    selection_start: int = 0
    selection_length: int = 0
    commit_pending: bool = False

    @property
    def active(self) -> bool:
        return self.phase is not TextPhase.OFF

    @property
    def editing(self) -> bool:
        return self.phase is TextPhase.EDITING

    @property
    def display_text(self) -> str | None:
        return self.value + self.composition if self.active else None

    def begin(self) -> None:
        self.clear()
        self.phase = TextPhase.EDITING

    def clear(self) -> None:
        self.phase = TextPhase.OFF
        self.value = self.composition = ""
        self.selection_start = self.selection_length = 0
        self.commit_pending = False

    def insert(self, text: str) -> None:
        if self.editing:
            clean = "".join(character for character in text if character.isprintable())
            self.value = (self.value + clean)[:MAX_TEXT_LENGTH]
            self.composition = ""
            self.selection_start = self.selection_length = 0

    def compose(self, text: str, start: int = 0, length: int = 0) -> None:
        if self.editing:
            self.composition = text[:max(0, MAX_TEXT_LENGTH - len(self.value))]
            self.selection_start = max(0, min(start, len(self.composition)))
            self.selection_length = max(0, min(length, len(self.composition) - self.selection_start))

    def backspace(self) -> None:
        # The IME owns deletion while it has an active composition.
        if self.editing and not self.composition:
            self.value = self.value[:-1]

    def request_commit(self) -> None:
        self.commit_pending = self.editing

    def commit(self) -> None:
        if not self.editing:
            return
        self.value = (self.value + self.composition)[:MAX_TEXT_LENGTH].strip()
        self.composition = ""
        self.selection_start = self.selection_length = 0
        self.commit_pending = False
        self.phase = TextPhase.PINNED
