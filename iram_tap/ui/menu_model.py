from __future__ import annotations

from dataclasses import dataclass

from iram_tap.models import Action, Command, WINDOW_SCALES, WindowState


@dataclass(frozen=True)
class MenuEntry:
    label: str
    command: Command | None = None
    checked: bool | None = None
    children: tuple[MenuEntry, ...] = ()


def menu_entries(state: WindowState) -> tuple[MenuEntry, ...]:
    return (
        MenuEntry("설정 열기", Command(Action.OPEN_SETTINGS)),
        MenuEntry("오버레이 숨기기" if state.visible else "오버레이 표시", Command(Action.TOGGLE_VISIBILITY)),
        MenuEntry("크기", children=tuple(
            MenuEntry(f"{round(scale * 100)}%", Command(Action.RESIZE, scale), abs(state.scale - scale) < 0.01)
            for scale in WINDOW_SCALES
        )),
        MenuEntry("Always On Top", Command(Action.TOGGLE_TOPMOST), state.topmost),
        MenuEntry("위치 잠금 (F9)", Command(Action.TOGGLE_LOCK), state.position_locked),
        MenuEntry("로그 폴더 열기", Command(Action.OPEN_LOGS)),
        MenuEntry("프로그램 종료", Command(Action.QUIT)),
    )
