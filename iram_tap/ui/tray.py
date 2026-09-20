from __future__ import annotations

import threading
import logging
from pathlib import Path
from queue import Empty, SimpleQueue
from typing import Any, Callable

from PIL import Image, ImageDraw

from iram_tap.models import Action, Command, WindowState
from iram_tap.ui.menu_model import menu_entries

logger = logging.getLogger(__name__)


class TrayManager:
    def __init__(self, icon_path: str | Path | None = None) -> None:
        self.icon_path = Path(icon_path) if icon_path else None
        self._actions: SimpleQueue[Command] = SimpleQueue()
        self._state_lock = threading.Lock()
        self._visible = True
        self._topmost = True
        self._position_locked = True
        self._window_scale = 1.0
        self._icon: Any = None
        self._thread: threading.Thread | None = None
        self._ready_event = threading.Event()

    def _emit(self, action: Command) -> None:
        self._actions.put(action)

    def _callback(self, action: Command) -> Callable[[Any, Any], None]:
        return lambda _icon, _item: self._emit(action)

    def consume_actions(self) -> list[Command]:
        actions: list[Command] = []
        while True:
            try:
                actions.append(self._actions.get_nowait())
            except Empty:
                return actions

    def update_state(
        self,
        *,
        visible: bool,
        topmost: bool,
        position_locked: bool,
        window_scale: float,
    ) -> None:
        with self._state_lock:
            self._visible = visible
            self._topmost = topmost
            self._position_locked = position_locked
            self._window_scale = window_scale
        if self._icon is not None:
            try:
                import pystray
                self._icon.menu = self._build_menu(pystray)
                self._icon.update_menu()
            except (AttributeError, OSError):
                pass

    def _build_menu(self, pystray: Any) -> Any:
        with self._state_lock:
            state = WindowState(self._visible, self._topmost, self._position_locked, self._window_scale)
        def item(entry: Any) -> Any:
            action = pystray.Menu(*(item(child) for child in entry.children)) if entry.children else self._callback(entry.command)
            checked = None if entry.checked is None else lambda _item: entry.checked
            return pystray.MenuItem(entry.label, action, checked=checked,
                default=entry.command == Command(Action.OPEN_SETTINGS))
        return pystray.Menu(*(item(entry) for entry in menu_entries(state)))

    def _load_icon_image(self) -> Image.Image:
        if self.icon_path and self.icon_path.is_file():
            try:
                with Image.open(self.icon_path) as opened:
                    image = opened.convert("RGBA")
                bounds = image.getbbox()
                if bounds:
                    image = image.crop(bounds)
                    side = max(image.size)
                    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
                    square.alpha_composite(
                        image,
                        ((side - image.width) // 2, (side - image.height) // 2),
                    )
                    return square.resize((64, 64), Image.Resampling.LANCZOS)
            except (OSError, ValueError):
                pass

        image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.polygon(((8, 22), (15, 5), (28, 18)), fill=(255, 224, 170, 255))
        draw.polygon(((36, 18), (49, 5), (56, 22)), fill=(255, 224, 170, 255))
        draw.ellipse((7, 13, 57, 61), fill=(255, 224, 170, 255), outline=(87, 58, 42, 255), width=3)
        draw.ellipse((20, 31, 25, 38), fill=(48, 42, 45, 255))
        draw.ellipse((39, 31, 44, 38), fill=(48, 42, 45, 255))
        draw.ellipse((28, 39, 36, 45), fill=(244, 148, 158, 255))
        return image

    def update_icon(self, icon_path: str | Path | None) -> None:
        self.icon_path = Path(icon_path) if icon_path else None
        if self._icon is not None:
            try:
                self._icon.icon = self._load_icon_image()
            except (AttributeError, OSError, RuntimeError):
                pass

    def start(self) -> bool:
        if self._thread is not None and self._thread.is_alive():
            return True
        try:
            import pystray

            menu = self._build_menu(pystray)
            self._icon = pystray.Icon(
                "iram_tap",
                self._load_icon_image(),
                "iram_tap",
                menu,
            )
            self._thread = threading.Thread(
                target=self._run_icon,
                name="iram_tap_tray_icon",
                daemon=True,
            )
            self._ready_event.clear()
            self._thread.start()
            if not self._ready_event.wait(timeout=2.0):
                logger.warning("트레이 초기화 지연. F9로 잠금을 해제한 후 오버레이 우클릭 메뉴를 사용하세요.")
                return False
            return self._thread.is_alive()
        except (ImportError, OSError, RuntimeError):
            logger.exception("트레이 시작 실패")
            self._icon = None
            self._thread = None
            return False

    def _run_icon(self) -> None:
        try:
            self._icon.run(setup=self._setup_icon)
        except Exception:
            logger.exception("트레이 실행 실패")
            self._ready_event.set()

    def _setup_icon(self, icon: Any) -> None:
        icon.visible = True
        self._ready_event.set()
        try:
            icon.notify(
                "iram_tap을 드래그하거나 우클릭할 수 있습니다. F9로 위치를 잠급니다.",
                "iram_tap",
            )
        except (AttributeError, NotImplementedError, OSError):
            pass

    def stop(self) -> None:
        if self._icon is not None:
            try:
                self._icon.stop()
            except (AttributeError, OSError):
                pass
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._icon = None
        self._thread = None
        self._ready_event.clear()
