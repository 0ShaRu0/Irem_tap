from __future__ import annotations

import threading
from pathlib import Path
from queue import Empty, SimpleQueue
from typing import Any, Callable

from PIL import Image, ImageDraw

from config_manager import WINDOW_SCALES


class TrayManager:
    def __init__(self, icon_path: str | Path | None = None) -> None:
        self.icon_path = Path(icon_path) if icon_path else None
        self._actions: SimpleQueue[str] = SimpleQueue()
        self._state_lock = threading.Lock()
        self._visible = True
        self._topmost = True
        self._position_locked = True
        self._window_scale = 1.0
        self._icon: Any = None
        self._thread: threading.Thread | None = None
        self._ready_event = threading.Event()

    def _emit(self, action: str) -> None:
        self._actions.put(action)

    def _callback(self, action: str) -> Callable[[Any, Any], None]:
        return lambda _icon, _item: self._emit(action)

    def consume_actions(self) -> list[str]:
        actions: list[str] = []
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
                self._icon.update_menu()
            except (AttributeError, OSError):
                pass

    def _visibility_text(self, _item: Any) -> str:
        with self._state_lock:
            return "오버레이 숨기기" if self._visible else "오버레이 표시"

    def _is_topmost(self, _item: Any) -> bool:
        with self._state_lock:
            return self._topmost

    def _is_position_locked(self, _item: Any) -> bool:
        with self._state_lock:
            return self._position_locked

    def _is_scale(self, expected: float) -> Callable[[Any], bool]:
        def checked(_item: Any) -> bool:
            with self._state_lock:
                return abs(self._window_scale - expected) < 0.01

        return checked

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

            size_items = tuple(
                pystray.MenuItem(
                    f"{round(scale * 100)}%",
                    self._callback(f"resize:{scale}"),
                    checked=self._is_scale(scale),
                    radio=True,
                )
                for scale in WINDOW_SCALES
            )
            menu = pystray.Menu(
                pystray.MenuItem("설정 열기", self._callback("open_settings"), default=True),
                pystray.MenuItem(self._visibility_text, self._callback("toggle_visibility")),
                pystray.MenuItem("크기", pystray.Menu(*size_items)),
                pystray.MenuItem(
                    "Always On Top",
                    self._callback("toggle_topmost"),
                    checked=self._is_topmost,
                ),
                pystray.MenuItem(
                    "위치 잠금 (F9)",
                    self._callback("toggle_position_lock"),
                    checked=self._is_position_locked,
                ),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("프로그램 종료", self._callback("quit")),
            )
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
                print("[tray] 트레이 아이콘 초기화가 지연되고 있습니다. 오버레이를 우클릭해 메뉴를 열 수 있습니다.")
                return False
            return self._thread.is_alive()
        except (ImportError, OSError, RuntimeError) as error:
            print(f"[tray] 트레이 아이콘을 시작할 수 없습니다: {error}")
            self._icon = None
            self._thread = None
            return False

    def _run_icon(self) -> None:
        try:
            self._icon.run(setup=self._setup_icon)
        except Exception as error:
            print(f"[tray] 트레이 아이콘 오류: {error}")
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
