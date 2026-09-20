from __future__ import annotations

import ctypes
from ctypes import wintypes
import logging
import math
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pygame

from iram_tap.config.repository import (
    load_config,
    load_config_strict,
    resolve_asset_path,
    update_config,
)
from iram_tap.platform.input import InputManager
from iram_tap.image_modes import (
    KEYBOARD_MODE_NAME,
    ImageMode,
    discover_image_modes,
)
from iram_tap.platform.audio import MicrophoneManager
from iram_tap.rendering.renderer import LayerRenderer, TEXT_BUBBLE_AREA_HEIGHT
from iram_tap.ui.tray import TrayManager
from iram_tap.assets import application_directory, file_signature
from iram_tap.lifecycle import Resources
from iram_tap.text_mode import TextMode
from iram_tap.models import Action, Command, WindowState
from iram_tap.platform.windows import (
    LayeredWindowPresenter, WindowController, user32_api,
)


WINDOW_TITLE = "iram_tap"
logger = logging.getLogger(__name__)
LOCKED_HOVER_ALPHA = 128

class OverlayApp:
    def __init__(self, config_path: str | Path, *, config: dict[str, Any] | None = None) -> None:
        self.config_path = Path(config_path).resolve()
        self.config = load_config(self.config_path) if config is None else config
        self.image_modes = discover_image_modes(self.config_path)
        if not self.image_modes:
            self.image_modes = [
                ImageMode(KEYBOARD_MODE_NAME, "keyboard", KEYBOARD_MODE_NAME)
            ]
        self.active_mode_index = 0
        self.selected_character_number = 0
        self.running = True
        self.visible = True
        self.settings_process: subprocess.Popen[Any] | None = None
        self.selected_character_path: str | None = None
        self.selected_character_open_path: str | None = None
        self.last_file_check = 0.0
        self.config_mtime = self._config_mtime()
        self._config_error_mtime: int | None = None
        self._icon_state: tuple[str, object] | None = None
        self.window_scale = 1.0
        self.last_known_window_position: tuple[int, int] | None = None
        self.pending_position_save_at: float | None = None
        self.applied_window_alpha: int | None = None
        self.text = TextMode()
        self.previous_foreground_window: int | None = None
        self.screen: pygame.Surface
        self.layered_presenter = LayeredWindowPresenter() if os.name == "nt" else None
        self.window = WindowController()
        self.resources = Resources()
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self.resources.add(pygame.quit)
        pygame.init()
        icon_path = resolve_asset_path(self.config["icon_path"], self.config_path)
        self._set_window_icon(icon_path)
        self.clock = pygame.time.Clock()
        if self.layered_presenter is not None:
            self.resources.add(self.layered_presenter.close)
        self._create_display()
        self.renderer = LayerRenderer(self.config, self.config_path)
        self.input_manager = InputManager()
        self.resources.add(self.input_manager.stop)
        self.microphone_manager = MicrophoneManager(self.config)
        self.resources.add(self.microphone_manager.stop)
        self.tray_manager = TrayManager(icon_path)
        self.resources.add(self.tray_manager.stop)
        self._reload_active_mode()
        self.asset_state = self._asset_state()
        pygame.key.stop_text_input()
        logger.info("오버레이 초기화 완료")

    def close(self) -> None:
        if self._started:
            try:
                if self.text.editing:
                    self._restore_previous_focus()
            finally:
                self.resources.close()
                self._started = False

    @property
    def text_editing(self) -> bool:
        return self.text.editing

    @property
    def text_mode_active(self) -> bool:
        return self.text.active

    @property
    def text_value(self) -> str:
        return self.text.value

    @property
    def text_composition(self) -> str:
        return self.text.composition

    @staticmethod
    def _set_window_icon(icon_path: Path) -> None:
        if not icon_path.is_file():
            logger.warning("누락된 아이콘: %s", icon_path)
            return
        try:
            pygame.display.set_icon(pygame.image.load(str(icon_path)))
        except (OSError, ValueError, pygame.error) as error:
            logger.warning("아이콘 로딩 실패: %s (%s)", icon_path, error)

    def _is_borderless(self) -> bool:
        return self.config["borderless"] or self.config["transparent_background"]

    def _display_flags(self) -> int:
        flags = pygame.DOUBLEBUF
        flags |= pygame.NOFRAME if self._is_borderless() else pygame.RESIZABLE
        return flags

    def _create_display(self, size: tuple[int, int] | None = None) -> None:
        if self.layered_presenter is not None:
            self.layered_presenter.close()
        self.applied_window_alpha = None
        display_size = size or (
            self.config["window_width"],
            self.config["window_height"] + TEXT_BUBBLE_AREA_HEIGHT,
        )
        self.screen = pygame.display.set_mode(display_size, self._display_flags())
        pygame.display.set_caption(WINDOW_TITLE)
        self._apply_windows_options()
        self._apply_saved_window_position()
        self._remember_window_position()

    def _window_handle(self) -> int | None:
        if os.name != "nt":
            return None
        return pygame.display.get_wm_info().get("window")

    def _apply_windows_options(self) -> None:
        self.window.apply(
            self._window_handle(), borderless=self._is_borderless(),
            transparent=self.config["transparent_background"],
            locked=self.config["window_position_locked"], editing=self.text_editing,
            topmost=self.config["always_on_top"],
        )
        self.applied_window_alpha = None

    def _window_rect(self) -> wintypes.RECT | None:
        return self.window.rectangle(self._window_handle())

    def _window_alpha(self) -> int:
        if (
            os.name != "nt"
            or getattr(self, "text_editing", False)
            or not self.config["window_position_locked"]
        ):
            return 255
        rectangle = self._window_rect()
        if rectangle is None:
            return 255
        cursor = wintypes.POINT()
        if not user32_api().GetCursorPos(ctypes.byref(cursor)):
            return 255
        if (
            rectangle.left <= cursor.x < rectangle.right
            and rectangle.top <= cursor.y < rectangle.bottom
        ):
            return LOCKED_HOVER_ALPHA
        return 255

    def _apply_uniform_window_alpha(self, window_handle: int, alpha: int) -> None:
        if self.config["transparent_background"]:
            return
        if not (self._is_borderless() or self.config["window_position_locked"]):
            return
        alpha = max(0, min(255, int(alpha)))
        if self.applied_window_alpha == alpha:
            return
        if user32_api().SetLayeredWindowAttributes(
            window_handle, 0, alpha, 0x00000002
        ):
            self.applied_window_alpha = alpha

    def _move_window(self, x: int, y: int) -> None:
        self.window.move(self._window_handle(), x, y)

    def _remember_window_position(self) -> None:
        rectangle = self._window_rect()
        if rectangle is not None:
            self.last_known_window_position = (rectangle.left, rectangle.top)

    def _visible_window_position(
        self, x: int, y: int, width: int, height: int
    ) -> tuple[int, int]:
        return self.window.visible_position(x, y, width, height)

    def _apply_saved_window_position(self) -> None:
        configured_x = self.config.get("window_x")
        configured_y = self.config.get("window_y")
        if configured_x is None and configured_y is None:
            return
        rectangle = self._window_rect()
        if rectangle is None:
            return
        requested_x = rectangle.left if configured_x is None else configured_x
        requested_y = rectangle.top if configured_y is None else configured_y
        target_x, target_y = self._visible_window_position(
            requested_x,
            requested_y,
            rectangle.right - rectangle.left,
            rectangle.bottom - rectangle.top,
        )
        self.config["window_x"] = target_x
        self.config["window_y"] = target_y
        self.last_known_window_position = (target_x, target_y)
        self._move_window(target_x, target_y)

    def _save_runtime_config(self, fields: tuple[str, ...]) -> None:
        runtime_state = {name: self.config[name] for name in fields}

        def merge_runtime_state(latest_config: dict[str, Any]) -> dict[str, Any]:
            latest_config.update(runtime_state)
            return latest_config

        try:
            update_config(merge_runtime_state, self.config_path)
        except (OSError, ValueError) as error:
            logger.error("창 상태 저장 실패: %s", error)

    def _start_window_drag(self) -> None:
        if self.config["window_position_locked"]:
            return
        window_handle = self._window_handle()
        if not window_handle:
            return
        user32 = user32_api()
        user32.ReleaseCapture()
        user32.SendMessageW(window_handle, 0x00A1, 0x0002, 0)  # WM_NCLBUTTONDOWN, HTCAPTION
        rectangle = self._window_rect()
        if rectangle is not None:
            self.config["window_x"] = rectangle.left
            self.config["window_y"] = rectangle.top
            self.last_known_window_position = (rectangle.left, rectangle.top)
            self.pending_position_save_at = None
            self._save_runtime_config(("window_x", "window_y"))
            logger.info("위치 저장: %s, %s", rectangle.left, rectangle.top)

    def _set_topmost(self, enabled: bool) -> None:
        self.window.topmost(self._window_handle(), enabled)

    def _toggle_visibility(self) -> None:
        if self.visible and self.text_mode_active:
            self._stop_text_mode()
        self.visible = not self.visible
        window_handle = self._window_handle()
        if window_handle:
            show_command = 8 if self.visible else 0  # SW_SHOWNA / SW_HIDE
            user32_api().ShowWindow(window_handle, show_command)
            if self.visible:
                self._set_topmost(self.config["always_on_top"])
        elif not self.visible:
            pygame.display.iconify()
        self._sync_tray_state()

    def _toggle_topmost(self) -> None:
        self.config["always_on_top"] = not self.config["always_on_top"]
        self._set_topmost(self.config["always_on_top"])
        self._save_runtime_config(("always_on_top",))
        state = "ON" if self.config["always_on_top"] else "OFF"
        logger.info("Always On Top: %s", state)
        self._sync_tray_state()

    def _toggle_position_lock(self) -> None:
        self.config["window_position_locked"] = not self.config["window_position_locked"]
        self._remember_window_position()
        self._apply_windows_options()
        self._save_runtime_config(("window_position_locked",))
        state = "ON" if self.config["window_position_locked"] else "OFF"
        logger.info("위치 잠금: %s", state)
        self._sync_tray_state()

    def _focus_overlay_for_text_input(self) -> bool:
        window_handle = self._window_handle()
        if not window_handle:
            return True
        user32 = user32_api()
        foreground_window = user32.GetForegroundWindow()
        if foreground_window and foreground_window != window_handle:
            self.previous_foreground_window = int(foreground_window)
        user32.ShowWindow(window_handle, 5)  # SW_SHOW
        user32.SetForegroundWindow(window_handle)
        focused = user32.GetForegroundWindow() == window_handle
        if not focused:
            logger.warning("텍스트 입력 포커스 획득 실패")
        return focused

    def _restore_previous_focus(self) -> None:
        previous_window = self.previous_foreground_window
        self.previous_foreground_window = None
        if previous_window and os.name == "nt":
            user32 = user32_api()
            # Do not steal focus if the user has already switched to another app.
            if user32.IsWindow(previous_window) and user32.GetForegroundWindow() == self._window_handle():
                user32.SetForegroundWindow(wintypes.HWND(previous_window))

    def _start_text_mode(self) -> None:
        logger.info("F10 텍스트 입력 시작")
        self.text.begin()
        if not self.visible:
            self.visible = True
            self._sync_tray_state()
        self._apply_windows_options()
        if not self._focus_overlay_for_text_input():
            self.text.clear()
            self.previous_foreground_window = None
            self._apply_windows_options()
            return
        pygame.key.start_text_input()
        pygame.key.set_text_input_rect(
            pygame.Rect(12, 8, max(1, self.screen.get_width() - 24), 96)
        )

    def _commit_text_input(self) -> None:
        if not self.text_editing:
            return
        self.text.commit()
        pygame.key.stop_text_input()
        self._apply_windows_options()
        self._restore_previous_focus()

    def _stop_text_mode(self) -> None:
        logger.info("F10 텍스트 초기화")
        was_editing = self.text_editing
        self.text.clear()
        pygame.key.stop_text_input()
        self._apply_windows_options()
        if was_editing:
            self._restore_previous_focus()

    def _toggle_text_mode(self) -> None:
        if self.text_mode_active:
            self._stop_text_mode()
        else:
            self._start_text_mode()

    def _handle_text_input_event(self, event: pygame.event.Event) -> bool:
        if not self.text_editing:
            return False
        if event.type == pygame.TEXTINPUT:
            self.text.insert(event.text)
            return True
        if event.type == pygame.TEXTEDITING:
            self.text.compose(event.text, getattr(event, "start", 0), getattr(event, "length", 0))
            return True
        if event.type != pygame.KEYDOWN:
            return False
        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self.text.request_commit()
        elif event.key == pygame.K_BACKSPACE and not self.text_composition:
            self.text.backspace()
        return True

    def _active_mode(self) -> ImageMode:
        return self.image_modes[self.active_mode_index]

    def _keyboard_mode(self) -> ImageMode | None:
        return next(
            (mode for mode in self.image_modes if mode.kind == "keyboard"),
            None,
        )

    def _character_paths(self, number: int) -> tuple[str, str]:
        if number == 0:
            return (
                self.config["images"]["character"]["path"],
                self.config["microphone_open_image"],
            )
        keyboard_mode = self._keyboard_mode()
        directory = (
            keyboard_mode.directory_name
            if keyboard_mode is not None
            else KEYBOARD_MODE_NAME
        )
        prefix = (Path("image") / directory).as_posix()
        return (
            f"{prefix}/character{number}.png",
            f"{prefix}/character{number}_open.png",
        )

    def _reload_active_mode(self) -> None:
        mode = self._active_mode()
        avatar_paths = mode.expression_paths
        if mode.kind == "keyboard":
            path_value, open_path_value = self._character_paths(
                self.selected_character_number
            )
            self.selected_character_path = (
                None if self.selected_character_number == 0 else path_value
            )
            self.selected_character_open_path = (
                None if self.selected_character_number == 0 else open_path_value
            )
        else:
            self.selected_character_path = None
            self.selected_character_open_path = None
        self.renderer.reload_config(
            self.config,
            selected_character_path=self.selected_character_path,
            selected_character_open_path=self.selected_character_open_path,
            avatar_expression_paths=avatar_paths,
        )
        self._sync_microphone_character()

    def _switch_mode(self, offset: int) -> None:
        if len(self.image_modes) < 2:
            return
        self.active_mode_index = (self.active_mode_index + offset) % len(
            self.image_modes
        )
        self._reload_active_mode()
        self.asset_state = self._asset_state()
        logger.info("모드 변경: %s", self._active_mode().name)

    def _select_character(self, number: int) -> None:
        if self._active_mode().kind != "keyboard" or number not in range(10):
            return
        path_value, open_path_value = self._character_paths(number)
        if not self.renderer.select_character(path_value, open_path_value):
            logger.warning("캐릭터 변경 실패: %s", path_value)
            return
        self.selected_character_path = None if number == 0 else path_value
        self.selected_character_open_path = (
            None if number == 0 else open_path_value
        )
        self.selected_character_number = number
        self.asset_state = self._asset_state()
        self._sync_microphone_character()
        label = "기본" if number == 0 else str(number)
        logger.info("캐릭터 변경: %s", label)

    def _sync_microphone_character(self) -> None:
        # The app decides expression priority; the renderer only swaps cached images.
        self.renderer.set_microphone_level(
            self.microphone_manager.expression_level()
        )

    def _resize_window(self, scale: float) -> None:
        self.window_scale = scale
        size = (
            max(160, math.floor(self.config["window_width"] * scale + 0.5)),
            max(
                120,
                math.floor(
                    (self.config["window_height"] + TEXT_BUBBLE_AREA_HEIGHT) * scale + 0.5
                ),
            ),
        )
        self._create_display(size)
        self._sync_tray_state()

    def _show_context_menu(self) -> None:
        if self.config["window_position_locked"]:
            return
        window_handle = self._window_handle()
        if not window_handle:
            return
        action = self.window.show_menu(window_handle, WindowState(
            self.visible, self.config["always_on_top"],
            self.config["window_position_locked"], self.window_scale,
        ))
        if action is not None:
            self._handle_action(action)

    def _sync_tray_state(self) -> None:
        if not hasattr(self, "tray_manager"):
            return
        self.tray_manager.update_state(
            visible=self.visible,
            topmost=self.config["always_on_top"],
            position_locked=self.config["window_position_locked"],
            window_scale=self.window_scale,
        )

    def _launch_settings(self) -> None:
        if self.settings_process is not None and self.settings_process.poll() is None:
            return
        if getattr(sys, "frozen", False):
            command = [sys.executable, "--settings", "--config", str(self.config_path)]
        else:
            command = [
                sys.executable,
                str(application_directory() / "main.py"),
                "--settings",
                "--config",
                str(self.config_path),
            ]
        try:
            environment = os.environ.copy()
            if getattr(sys, "frozen", False):
                environment["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
            self.settings_process = subprocess.Popen(command, env=environment)
        except OSError as error:
            logger.error("설정 창 실행 실패: %s", error)

    def _config_mtime(self) -> int | None:
        try:
            return self.config_path.stat().st_mtime_ns
        except OSError:
            return None

    def _asset_state(self) -> dict[str, tuple[int, int, int] | None]:
        path_values = [self.config.get("icon_path", "")]
        path_values.extend(
            spec.get("path", "") for spec in self.config["images"].values()
        )
        if self.selected_character_path is not None:
            path_values.append(self.selected_character_path)
        if self.selected_character_open_path is not None:
            path_values.append(self.selected_character_open_path)
        path_values.append(self.config["microphone_open_image"])
        expression_paths = self._active_mode().expression_paths
        if expression_paths is not None:
            path_values.extend(expression_paths)
        state: dict[str, tuple[int, int, int] | None] = {}
        for path_value in path_values:
            if not path_value:
                continue
            path = resolve_asset_path(path_value, self.config_path)
            state[str(path)] = file_signature(path)
        return state

    def _reload_config_if_changed(self) -> None:
        now = time.monotonic()
        if now - self.last_file_check < 0.5:
            return
        self.last_file_check = now
        config_reloaded = False
        modified = self._config_mtime()
        if modified is not None and modified != self.config_mtime:
            try:
                reloaded_config = load_config_strict(self.config_path)
            except (OSError, ValueError) as error:
                if modified != self._config_error_mtime:
                    logger.warning("변경된 설정이 잘못되어 최근 정상 설정 유지: %s", error)
                    self._config_error_mtime = modified
            else:
                self._config_error_mtime = None
                old_config = self.config
                self.config = reloaded_config
                self.config_mtime = modified
                config_reloaded = True
                recreate_window = any(
                    old_config[name] != self.config[name]
                    for name in (
                        "window_width",
                        "window_height",
                        "borderless",
                        "transparent_background",
                    )
                )
                if recreate_window:
                    self.window_scale = 1.0
                    self._create_display()
                else:
                    self._apply_windows_options()
                    if any(
                        old_config[name] != self.config[name]
                        for name in ("window_x", "window_y")
                    ):
                        self._apply_saved_window_position()

        asset_state = self._asset_state()
        assets_changed = asset_state != self.asset_state
        if not config_reloaded and not assets_changed and not self.renderer.pending_assets:
            return

        if config_reloaded:
            self.microphone_manager.reconfigure(self.config)
        self._reload_active_mode()
        icon_path = resolve_asset_path(self.config["icon_path"], self.config_path)
        icon_state = (str(icon_path), file_signature(icon_path))
        if icon_state != self._icon_state:
            self._set_window_icon(icon_path)
            self.tray_manager.update_icon(icon_path)
            self._icon_state = icon_state
        self.asset_state = asset_state
        self._sync_tray_state()
        if config_reloaded:
            logger.info("변경된 설정 적용")
        elif assets_changed:
            logger.info("변경된 이미지 갱신")

    def _handle_window_events(self) -> None:
        window_moved_event = getattr(pygame, "WINDOWMOVED", -1)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif self._handle_text_input_event(event):
                continue
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._start_window_drag()
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
                self._show_context_menu()
            elif event.type == window_moved_event:
                rectangle = self._window_rect()
                moved_position = (
                    (rectangle.left, rectangle.top)
                    if rectangle is not None
                    else (int(event.x), int(event.y))
                )
                if self.config["window_position_locked"]:
                    if (
                        self.last_known_window_position is not None
                        and moved_position != self.last_known_window_position
                    ):
                        self._move_window(*self.last_known_window_position)
                else:
                    self.last_known_window_position = moved_position
                    self.config["window_x"], self.config["window_y"] = moved_position
                    self.pending_position_save_at = time.monotonic() + 0.3
            elif event.type == pygame.VIDEORESIZE and not self._is_borderless():
                width = max(160, event.w)
                height = max(120, event.h)
                self.window_scale = min(
                    width / self.config["window_width"],
                    height / (self.config["window_height"] + TEXT_BUBBLE_AREA_HEIGHT),
                )
                self._create_display((width, height))
                self._sync_tray_state()
        # SDL may queue the final TEXTINPUT after the Enter KEYDOWN.
        if self.text.commit_pending:
            self._commit_text_input()

    def _save_pending_window_position(self) -> None:
        if (
            self.pending_position_save_at is not None
            and time.monotonic() >= self.pending_position_save_at
        ):
            self.pending_position_save_at = None
            self._save_runtime_config(("window_x", "window_y"))

    def _handle_shortcuts(self) -> None:
        actions = self.input_manager.consume_actions()
        actions.extend(self.tray_manager.consume_actions())
        for action in actions:
            self._handle_action(action)

    def _handle_action(self, action: str | Command) -> None:
        command = Command.parse(action)
        kind = command.action
        if self.text_editing and kind in (
            Action.SELECT_CHARACTER, Action.NEXT_MODE, Action.PREVIOUS_MODE,
        ):
            return
        if kind is Action.TOGGLE_VISIBILITY:
            self._toggle_visibility()
        elif kind is Action.TOGGLE_TOPMOST:
            self._toggle_topmost()
        elif kind is Action.OPEN_SETTINGS:
            self._launch_settings()
        elif kind is Action.TOGGLE_LOCK:
            self._toggle_position_lock()
        elif kind is Action.TOGGLE_TEXT:
            self._toggle_text_mode()
        elif kind is Action.SELECT_CHARACTER and command.value is not None:
            self._select_character(int(command.value))
        elif kind is Action.NEXT_MODE:
            self._switch_mode(1)
        elif kind is Action.PREVIOUS_MODE:
            self._switch_mode(-1)
        elif kind is Action.RESIZE and command.value is not None:
            self._resize_window(float(command.value))
        elif kind is Action.OPEN_LOGS:
            from iram_tap.diagnostics import open_logs
            open_logs()
        elif kind is Action.QUIT:
            self.running = False

    def _present(self, canvas: pygame.Surface) -> None:
        screen_width, screen_height = self.screen.get_size()
        canvas_width, canvas_height = canvas.get_size()
        scale = min(screen_width / canvas_width, screen_height / canvas_height)
        output_size = (
            max(1, round(canvas_width * scale)),
            max(1, round(canvas_height * scale)),
        )
        if self.config.get("transparent_background"):
            output_size = (screen_width, screen_height)
        if output_size == canvas.get_size():
            output = canvas
        else:
            output = pygame.transform.smoothscale(canvas, output_size)
        destination = (
            (screen_width - output_size[0]) // 2,
            (screen_height - output_size[1]) // 2,
        )
        window_handle = self._window_handle()
        window_alpha = self._window_alpha()
        if (
            self.config["transparent_background"]
            and window_handle is not None
            and self.layered_presenter is not None
        ):
            frame = pygame.Surface(
                (screen_width, screen_height), pygame.SRCALPHA, 32
            )
            frame.blit(output, destination)
            self.layered_presenter.present(window_handle, frame, window_alpha)
            return

        if window_handle is not None:
            self._apply_uniform_window_alpha(window_handle, window_alpha)
        self.screen.fill(self.config["background_color"])
        self.screen.blit(output, destination)
        pygame.display.flip()

    @staticmethod
    def _cursor_ratio(
        mouse_position: tuple[float, float] | None,
    ) -> tuple[float, float] | None:
        return WindowController.cursor_ratio(mouse_position)

    def run(self) -> int:
        try:
            self.start()
            try:
                self.input_manager.start()
                logger.info("전역 입력 시작 완료")
            except Exception:
                logger.exception("전역 입력 리스너 시작 실패")
            self.microphone_manager.start()
            self._sync_tray_state()
            self.tray_manager.start()
            logger.info("메인 루프 시작")
            while self.running:
                delta_time = min(self.clock.tick(self.config["fps"]) / 1000.0, 0.1)
                self._handle_window_events()
                self._handle_shortcuts()
                self._save_pending_window_position()
                self._reload_config_if_changed()
                self._sync_microphone_character()
                snapshot = self.input_manager.snapshot()
                if self.visible:
                    canvas = self.renderer.render(
                        snapshot,
                        delta_time,
                        self._cursor_ratio(snapshot.mouse_position),
                        text_overlay=self.text.display_text,
                        text_editing=self.text_editing,
                        reserve_text_space=True,
                    )
                    self._present(canvas)
        finally:
            self.close()
        return 0
