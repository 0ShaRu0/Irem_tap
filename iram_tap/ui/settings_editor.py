from __future__ import annotations

import copy
from functools import partial
from collections.abc import Callable
import re
from pathlib import Path
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, ttk
from typing import Any

from PIL import Image, ImageTk

from iram_tap.config.repository import (
    DEFAULT_CONFIG,
    KEY_GLOW_REFERENCE_SIZE,
    KEYS,
    MOUSE_GLOW_REFERENCE_SIZE,
    default_config_path,
    load_config,
    resolve_asset_path,
)
from iram_tap.platform.audio import DEFAULT_DEVICE_LABEL, input_device_names
from iram_tap.geometry import ImageTransform, scaled_image_size
from iram_tap.config.validation import finite_number, normalise_config
from iram_tap.ui.settings_model import SettingsModel
from iram_tap.ui.preview import PreviewRenderer


IMAGE_NAMES = tuple(DEFAULT_CONFIG["images"])
IMAGE_LABELS = {
    "character": "캐릭터",
    "desk_keyboard": "책상/키보드",
    "right_hand_mouse": "오른손 (마우스)",
    "left_hand_idle": "왼손 (대기)",
    "left_hand_pressed": "왼손 (입력 중)",
}
IMAGE_NAMES_BY_LABEL = {label: name for name, label in IMAGE_LABELS.items()}
KEY_LABELS = {key: ("Space" if key == "SPACE" else key) for key in KEYS}
MOUSE_BUTTON_LABELS = {"left": "왼쪽 클릭", "right": "오른쪽 클릭"}
GLOW_IMAGE_REFERENCES = {
    "glow": ("desk_keyboard", KEY_GLOW_REFERENCE_SIZE),
    "mouse_glow": ("right_hand_mouse", MOUSE_GLOW_REFERENCE_SIZE),
}


class SettingsEditor:
    def __init__(self, root: tk.Tk | None, config_path: str | Path,
                 *, config: dict[str, Any] | None = None) -> None:
        self.root = root
        self.config_path = Path(config_path).resolve()
        self.config = load_config(self.config_path) if config is None else copy.deepcopy(config)
        self.model = SettingsModel(self.config)
        self.preview = PreviewRenderer(self.config_path)
        self.active_image_name = "right_hand_mouse"
        self.selected_key = "Q"
        self.selected_mouse_button = "left"
        self.drag_offset: tuple[float, float] | None = None
        self.drag_target: str | None = None
        self.preview_scale = 1.0
        self.preview_origin = (0.0, 0.0)
        self.preview_photo: ImageTk.PhotoImage | None = None
        self.pil_cache = self.preview.cache

        if self.root is None:
            return
        self.root.title("iram_tap 설정")
        self.root.geometry("1180x760")
        self.root.minsize(950, 650)
        self._create_variables()
        self._build_ui()
        self._load_image_fields()
        self._load_glow_fields()
        self._load_mouse_glow_fields()
        self.root.after(50, self._redraw_preview)

    def _create_variables(self) -> None:
        self.image_choice = tk.StringVar(value=IMAGE_LABELS[self.active_image_name])
        self.image_path = tk.StringVar()
        self.image_x = tk.StringVar()
        self.image_y = tk.StringVar()
        self.image_width = tk.StringVar()
        self.image_height = tk.StringVar()
        self.image_keep_aspect = tk.BooleanVar(value=True)

        self.selected_key_text = tk.StringVar(value="선택 키: Q")
        self.glow_x = tk.StringVar()
        self.glow_y = tk.StringVar()
        self.glow_width = tk.StringVar()
        self.glow_height = tk.StringVar()
        self.preview_glow = tk.BooleanVar(value=True)

        self.selected_mouse_button_text = tk.StringVar(value="선택: 왼쪽 클릭")
        self.mouse_glow_x = tk.StringVar()
        self.mouse_glow_y = tk.StringVar()
        self.mouse_glow_width = tk.StringVar()
        self.mouse_glow_height = tk.StringVar()
        self.preview_mouse_glow = tk.BooleanVar(value=True)

        self.window_width = tk.StringVar(value=str(self.config["window_width"]))
        self.window_height = tk.StringVar(value=str(self.config["window_height"]))
        self.window_x = tk.StringVar(
            value="" if self.config["window_x"] is None else str(self.config["window_x"])
        )
        self.window_y = tk.StringVar(
            value="" if self.config["window_y"] is None else str(self.config["window_y"])
        )
        self.fps = tk.StringVar(value=str(self.config["fps"]))
        self.right_hand_speed = tk.StringVar(value=str(self.config["right_hand_speed"]))
        range_x, range_y = self.config["right_hand_range"]
        self.right_hand_range_x = tk.StringVar(value=self._format_number(range_x))
        self.right_hand_range_y = tk.StringVar(value=self._format_number(range_y))
        red, green, blue = self.config["background_color"]
        self.background_color = tk.StringVar(value=f"#{red:02X}{green:02X}{blue:02X}")
        red, green, blue = self.config["key_glow_color"]
        self.key_glow_color = tk.StringVar(value=f"#{red:02X}{green:02X}{blue:02X}")
        self.key_glow_alpha = tk.StringVar(value=str(self.config["key_glow_alpha"]))
        red, green, blue = self.config["mouse_glow_color"]
        self.mouse_glow_color = tk.StringVar(
            value=f"#{red:02X}{green:02X}{blue:02X}"
        )
        self.mouse_glow_alpha = tk.StringVar(value=str(self.config["mouse_glow_alpha"]))
        self.microphone_enabled = tk.BooleanVar()
        self.microphone_device = tk.StringVar()
        self.microphone_threshold = tk.StringVar()
        self.microphone_high_threshold = tk.StringVar()
        self.microphone_release_delay = tk.StringVar()
        self.microphone_open_image = tk.StringVar()
        self._sync_microphone_variables()
        self.window_position_locked = tk.BooleanVar(
            value=self.config["window_position_locked"]
        )
        self.always_on_top = tk.BooleanVar(value=self.config["always_on_top"])
        self.borderless = tk.BooleanVar(value=self.config["borderless"])
        self.transparent_background = tk.BooleanVar(
            value=self.config["transparent_background"]
        )
        self.smooth_movement = tk.BooleanVar(value=self.config["smooth_movement"])

    def _build_ui(self) -> None:
        assert self.root is not None
        bottom = ttk.Frame(self.root, padding=(8, 4, 8, 8))
        bottom.pack(side=tk.BOTTOM, fill=tk.X)
        ttk.Button(bottom, text="저장", command=self._save).pack(side=tk.RIGHT, padx=4)
        ttk.Button(bottom, text="닫기", command=self.root.destroy).pack(side=tk.RIGHT, padx=4)
        ttk.Button(bottom, text="파일 다시 읽기", command=self._reload).pack(
            side=tk.RIGHT, padx=4
        )
        ttk.Label(
            bottom, text="저장하면 실행 중인 오버레이에 자동으로 반영됩니다."
        ).pack(side=tk.LEFT)

        panes = ttk.Panedwindow(self.root, orient=tk.HORIZONTAL)
        panes.pack(fill=tk.BOTH, expand=True, padx=8, pady=(8, 4))
        controls = ttk.Frame(panes, width=390)
        preview_frame = ttk.Frame(panes)
        panes.add(controls, weight=0)
        panes.add(preview_frame, weight=1)

        self.notebook = ttk.Notebook(controls)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        self.image_tab = ttk.Frame(self.notebook, padding=12)
        self.glow_tab = ttk.Frame(self.notebook, padding=12)
        self.mouse_glow_tab = ttk.Frame(self.notebook, padding=12)
        self.microphone_tab = ttk.Frame(self.notebook, padding=12)
        self.motion_tab = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(self.image_tab, text="이미지")
        self.notebook.add(self.glow_tab, text="키 발광")
        self.notebook.add(self.mouse_glow_tab, text="마우스 발광")
        self.notebook.add(self.microphone_tab, text="마이크")
        self.notebook.add(self.motion_tab, text="창/동작")
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)
        self._build_image_tab(self.image_tab)
        self._build_glow_tab(self.glow_tab)
        self._build_mouse_glow_tab(self.mouse_glow_tab)
        self._build_microphone_tab(self.microphone_tab)
        self._build_motion_tab(self.motion_tab)

        ttk.Label(
            preview_frame,
            text="미리보기 - 선택한 이미지 또는 발광 점선 영역을 드래그할 수 있습니다.",
        ).pack(anchor=tk.W, pady=(0, 4))
        self.preview_canvas = tk.Canvas(
            preview_frame,
            background="#252525",
            highlightthickness=1,
            highlightbackground="#555555",
            cursor="fleur",
        )
        self.preview_canvas.pack(fill=tk.BOTH, expand=True)
        self.preview_canvas.bind("<Configure>", lambda _event: self._redraw_preview())
        self.preview_canvas.bind("<ButtonPress-1>", self._start_drag)
        self.preview_canvas.bind("<B1-Motion>", self._drag_preview)
        self.preview_canvas.bind("<ButtonRelease-1>", lambda _event: self._end_drag())

    def _build_image_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(1, weight=1)
        ttk.Label(parent, text="이미지 선택").grid(row=0, column=0, sticky=tk.W, pady=4)
        chooser = ttk.Combobox(
            parent,
            textvariable=self.image_choice,
            values=tuple(IMAGE_LABELS.values()),
            state="readonly",
        )
        chooser.grid(row=0, column=1, columnspan=2, sticky=tk.EW, pady=4)
        chooser.bind("<<ComboboxSelected>>", self._on_image_selected)

        ttk.Label(parent, text="PNG 경로").grid(row=1, column=0, sticky=tk.W, pady=4)
        ttk.Entry(parent, textvariable=self.image_path).grid(
            row=1, column=1, sticky=tk.EW, pady=4
        )
        ttk.Button(parent, text="찾기", command=self._browse_image).grid(
            row=1, column=2, padx=(5, 0), pady=4
        )
        self._entry_row(parent, 2, "X", self.image_x)
        self._entry_row(parent, 3, "Y", self.image_y)
        self._entry_row(parent, 4, "너비 (0=원본)", self.image_width)
        self._entry_row(parent, 5, "높이 (0=원본)", self.image_height)
        ttk.Checkbutton(
            parent, text="이미지 비율 유지", variable=self.image_keep_aspect
        ).grid(row=6, column=0, columnspan=3, sticky=tk.W, pady=6)
        ttk.Button(parent, text="미리보기에 적용", command=self._apply_image_fields).grid(
            row=7, column=0, columnspan=3, sticky=tk.EW, pady=(8, 4)
        )
        ttk.Label(
            parent,
            text="미리보기의 선택 영역을 드래그하면 X/Y가 바뀝니다.\n"
            "왼손 대기/입력 중 이미지는 각각 조절됩니다.\n"
            "오른손 X/Y는 마우스 이동 범위의 중심 위치입니다.\n"
            "상대 경로는 config.json이 있는 폴더 기준입니다.",
            wraplength=335,
            foreground="#555555",
        ).grid(row=8, column=0, columnspan=3, sticky=tk.W, pady=10)

    def _build_glow_tab(self, parent: ttk.Frame) -> None:
        for column in range(4):
            parent.columnconfigure(column, weight=1)
        for index, key in enumerate(KEYS):
            row = index // 4
            column = index % 4
            span = 4 if key == "SPACE" else 1
            ttk.Button(
                parent,
                text=KEY_LABELS[key],
                command=partial(self._select_key, key),
            ).grid(row=row, column=column, columnspan=span, sticky=tk.EW, padx=2, pady=3)

        ttk.Separator(parent).grid(row=3, column=0, columnspan=4, sticky=tk.EW, pady=10)
        ttk.Label(parent, textvariable=self.selected_key_text).grid(
            row=4, column=0, columnspan=4, sticky=tk.W, pady=4
        )
        self._build_glow_geometry_fields(
            parent, 5, "glow", self._apply_glow_fields
        )
        ttk.Checkbutton(
            parent,
            text="선택한 키 발광 미리보기",
            variable=self.preview_glow,
            command=self._redraw_preview,
        ).grid(row=8, column=0, columnspan=4, sticky=tk.W, pady=4)
        ttk.Label(
            parent,
            text="X/Y는 책상+키보드 PNG 내부 기준 좌표입니다. 미리보기의 점선 영역을 "
            "드래그하면 해당 키의 발광 중심이 이동합니다.",
            wraplength=335,
            foreground="#555555",
        ).grid(row=9, column=0, columnspan=4, sticky=tk.W, pady=8)

    def _build_mouse_glow_tab(self, parent: ttk.Frame) -> None:
        for column in range(4):
            parent.columnconfigure(column, weight=1)
        for index, button in enumerate(("left", "right")):
            ttk.Button(
                parent,
                text=MOUSE_BUTTON_LABELS[button],
                command=partial(self._select_mouse_button, button),
            ).grid(
                row=0,
                column=index * 2,
                columnspan=2,
                sticky=tk.EW,
                padx=2,
                pady=3,
            )

        ttk.Separator(parent).grid(row=1, column=0, columnspan=4, sticky=tk.EW, pady=10)
        ttk.Label(parent, textvariable=self.selected_mouse_button_text).grid(
            row=2, column=0, columnspan=4, sticky=tk.W, pady=4
        )
        self._build_glow_geometry_fields(
            parent, 3, "mouse_glow", self._apply_mouse_glow_fields
        )
        ttk.Checkbutton(
            parent,
            text="선택한 클릭 발광 미리보기",
            variable=self.preview_mouse_glow,
            command=self._redraw_preview,
        ).grid(row=6, column=0, columnspan=4, sticky=tk.W, pady=4)
        self._entry_row(
            parent,
            7,
            "발광 투명도 (0~255)",
            self.mouse_glow_alpha,
        )
        self._color_row(
            parent,
            8,
            "마우스 발광색",
            self.mouse_glow_color,
            "mouse_glow_color",
        )
        ttk.Label(
            parent,
            text="X/Y는 오른손 PNG 내부 기준 좌표입니다. 미리보기의 점선 영역을 "
            "드래그하면 클릭 발광 중심이 이동합니다.",
            wraplength=335,
            foreground="#555555",
        ).grid(row=9, column=0, columnspan=4, sticky=tk.W, pady=8)

    def _build_glow_geometry_fields(
        self, parent: ttk.Frame, row: int, mode: str, apply: Callable[[], None]
    ) -> None:
        labels = ("중심 X", "중심 Y", "발광 너비", "발광 높이")
        for index, (label, variable) in enumerate(zip(labels, self._glow_variables(mode), strict=True)):
            field_row = row + index // 2
            column = (index % 2) * 2
            ttk.Label(parent, text=label).grid(row=field_row, column=column, sticky=tk.W)
            ttk.Entry(parent, textvariable=variable, width=9).grid(
                row=field_row,
                column=column + 1,
                sticky=tk.EW,
                padx=(0, 8) if column == 0 else 0,
            )
        ttk.Button(parent, text="좌표/크기 적용", command=apply).grid(
            row=row + 2, column=0, columnspan=4, sticky=tk.EW, pady=8
        )

    def _build_microphone_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(1, weight=1)
        ttk.Checkbutton(
            parent,
            text="마이크 입력 감지 사용",
            variable=self.microphone_enabled,
        ).grid(row=0, column=0, columnspan=3, sticky=tk.W, pady=(0, 8))

        ttk.Label(parent, text="입력 장치").grid(row=1, column=0, sticky=tk.W, pady=4)
        self.microphone_device_chooser = ttk.Combobox(
            parent,
            textvariable=self.microphone_device,
            state="readonly",
        )
        self.microphone_device_chooser.grid(
            row=1, column=1, columnspan=2, sticky=tk.EW, pady=4
        )
        ttk.Button(
            parent,
            text="장치 목록 새로고침",
            command=self._refresh_microphone_devices,
        ).grid(row=2, column=0, columnspan=3, sticky=tk.EW, pady=(2, 8))
        self._entry_row(
            parent,
            3,
            "감지 임계값 (%)",
            self.microphone_threshold,
        )
        self._entry_row(
            parent,
            4,
            "큰 입 임계값 (%)",
            self.microphone_high_threshold,
        )
        self._entry_row(
            parent,
            5,
            "무음 복귀 시간 (ms)",
            self.microphone_release_delay,
        )
        ttk.Label(parent, text="열린 입 PNG").grid(
            row=6, column=0, sticky=tk.W, pady=4
        )
        ttk.Entry(parent, textvariable=self.microphone_open_image).grid(
            row=6, column=1, sticky=tk.EW, pady=4
        )
        ttk.Button(parent, text="찾기", command=self._browse_microphone_image).grid(
            row=6, column=2, padx=(5, 0), pady=4
        )
        ttk.Label(
            parent,
            text="Iram 모드는 감지/큰 입 임계값에 따라 3단계로 바뀝니다.\n"
            "숫자패드 표정은 같은 번호의 _open PNG를 사용합니다.",
            wraplength=335,
            foreground="#555555",
        ).grid(row=7, column=0, columnspan=3, sticky=tk.W, pady=10)
        self._refresh_microphone_devices()

    def _build_motion_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(1, weight=1)
        fields = (
            ("창 너비", self.window_width),
            ("창 높이", self.window_height),
            ("창 X (빈 값=자동)", self.window_x),
            ("창 Y (빈 값=자동)", self.window_y),
            ("FPS", self.fps),
            ("오른손 이동 속도", self.right_hand_speed),
            ("오른손 X 이동 범위", self.right_hand_range_x),
            ("오른손 Y 이동 범위", self.right_hand_range_y),
            ("키 발광 투명도 (0~255)", self.key_glow_alpha),
        )
        row = 0
        for label, variable in fields:
            self._entry_row(parent, row, label, variable)
            row += 1

        row = self._color_row(
            parent, row, "배경색", self.background_color, "background_color"
        )
        row = self._color_row(
            parent, row, "키 발광색", self.key_glow_color, "key_glow_color"
        )
        for label, bool_variable in (
            ("창 위치 잠금", self.window_position_locked),
            ("Always On Top", self.always_on_top),
            ("Borderless", self.borderless),
            ("투명 배경", self.transparent_background),
            ("부드러운 오른손 이동", self.smooth_movement),
        ):
            command = (
                self._redraw_preview
                if bool_variable is self.transparent_background
                else None
            )
            ttk.Checkbutton(
                parent, text=label, variable=bool_variable, command=command or ""
            ).grid(
                row=row, column=0, columnspan=3, sticky=tk.W, pady=3
            )
            row += 1

    def _color_row(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.StringVar,
        config_key: str,
    ) -> int:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky=tk.W, pady=4)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky=tk.EW)
        ttk.Button(
            parent,
            text="선택",
            command=lambda: self._choose_color(variable, config_key),
        ).grid(row=row, column=2, padx=(5, 0))
        return row + 1

    @staticmethod
    def _entry_row(parent: ttk.Frame, row: int, label: str, variable: tk.StringVar) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky=tk.W, pady=4)
        ttk.Entry(parent, textvariable=variable).grid(
            row=row, column=1, columnspan=2, sticky=tk.EW, pady=4
        )

    @staticmethod
    def _format_number(value: float) -> str:
        numeric = float(value)
        return str(int(numeric)) if numeric.is_integer() else str(numeric)

    def _load_image_fields(self) -> None:
        spec = self.config["images"][self.active_image_name]
        self.image_path.set(spec["path"])
        self.image_x.set(self._format_number(spec["position"][0]))
        self.image_y.set(self._format_number(spec["position"][1]))
        self.image_width.set(self._format_number(spec["size"][0]))
        self.image_height.set(self._format_number(spec["size"][1]))
        self.image_keep_aspect.set(spec["keep_aspect"])

    def _commit_image_fields(self, show_error: bool = True) -> bool:
        try:
            x = finite_number(self.image_x.get(), "이미지 X")
            y = finite_number(self.image_y.get(), "이미지 Y")
            width = max(0.0, finite_number(self.image_width.get(), "이미지 너비"))
            height = max(0.0, finite_number(self.image_height.get(), "이미지 높이"))
            scaled_image_size((300, 300), {"size": [width, height], "keep_aspect": False})
        except ValueError:
            if show_error:
                messagebox.showerror("입력 오류", "이미지 위치와 크기는 숫자로 입력하세요.")
            return False
        spec = self.config["images"][self.active_image_name]
        spec["path"] = self.image_path.get().strip()
        spec["position"] = [x, y]
        spec["size"] = [width, height]
        spec["keep_aspect"] = self.image_keep_aspect.get()
        return True

    def _on_image_selected(self, _event: tk.Event[Any]) -> None:
        self._commit_image_fields(show_error=False)
        self.active_image_name = IMAGE_NAMES_BY_LABEL[self.image_choice.get()]
        self._load_image_fields()
        self._redraw_preview()

    def _on_tab_changed(self, _event: tk.Event[Any]) -> None:
        self._end_drag()
        if hasattr(self, "preview_canvas"):
            cursor = (
                "fleur"
                if self._preview_mode() in {"image", "glow", "mouse_glow"}
                else ""
            )
            self.preview_canvas.configure(cursor=cursor)
            self._redraw_preview()

    def _apply_image_fields(self) -> None:
        if self._commit_image_fields():
            self.pil_cache.clear()
            self._redraw_preview()

    def _browse_image(self) -> None:
        if self._choose_image_path(self.image_path, "PNG 이미지 선택"):
            self._apply_image_fields()

    def _choose_image_path(self, variable: tk.StringVar, title: str) -> bool:
        current = variable.get().strip()
        initial_directory = self.config_path.parent
        if current:
            resolved = resolve_asset_path(current, self.config_path)
            if resolved.parent.is_dir():
                initial_directory = resolved.parent
        selected = filedialog.askopenfilename(
            title=title,
            initialdir=initial_directory,
            filetypes=(("PNG 이미지", "*.png"), ("모든 파일", "*.*")),
        )
        if not selected:
            return False
        selected_path = Path(selected).resolve()
        try:
            stored_path = selected_path.relative_to(self.config_path.parent).as_posix()
        except ValueError:
            stored_path = str(selected_path)
        variable.set(stored_path)
        return True

    def _refresh_microphone_devices(self) -> None:
        selected = self.microphone_device.get() or DEFAULT_DEVICE_LABEL
        options = [DEFAULT_DEVICE_LABEL, *input_device_names()]
        if selected not in options:
            options.append(selected)
        self.microphone_device_chooser.configure(values=options)
        self.microphone_device.set(selected)

    def _browse_microphone_image(self) -> None:
        self._choose_image_path(self.microphone_open_image, "열린 입 PNG 선택")

    def _glow_variables(self, mode: str) -> tuple[tk.StringVar, ...]:
        if mode == "mouse_glow":
            return (
                self.mouse_glow_x, self.mouse_glow_y,
                self.mouse_glow_width, self.mouse_glow_height,
            )
        return self.glow_x, self.glow_y, self.glow_width, self.glow_height

    def _selected_glow(self, mode: str) -> dict[str, Any]:
        if mode == "mouse_glow":
            return self.config["mouse_glows"][self.selected_mouse_button]
        return self.config["key_glows"][self.selected_key]

    def _load_glow_geometry_fields(self, mode: str) -> None:
        spec = self._selected_glow(mode)
        for variable, value in zip(
            self._glow_variables(mode), (*spec["position"], *spec["size"]), strict=True
        ):
            variable.set(self._format_number(value))

    def _load_glow_fields(self) -> None:
        self._load_glow_geometry_fields("glow")
        self.selected_key_text.set(f"선택 키: {KEY_LABELS[self.selected_key]}")

    def _commit_glow_fields(self, show_error: bool = True) -> bool:
        return self._commit_glow_geometry_fields("glow", show_error)

    def _commit_glow_geometry_fields(self, mode: str, show_error: bool) -> bool:
        try:
            x, y, width, height = (
                finite_number(variable.get(), "발광") for variable in self._glow_variables(mode)
            )
        except ValueError:
            if show_error:
                messagebox.showerror("입력 오류", "발광 위치와 크기는 숫자로 입력하세요.")
            return False
        spec = self._selected_glow(mode)
        spec["position"] = [x, y]
        spec["size"] = [max(1.0, width), max(1.0, height)]
        return True

    def _select_key(self, key: str) -> None:
        self._commit_glow_fields(show_error=False)
        self.selected_key = key
        self.preview_glow.set(True)
        self._load_glow_fields()
        self._redraw_preview()

    def _apply_glow_fields(self) -> None:
        if self._commit_glow_fields():
            self._redraw_preview()

    def _load_mouse_glow_fields(self) -> None:
        self._load_glow_geometry_fields("mouse_glow")
        self.selected_mouse_button_text.set(
            f"선택: {MOUSE_BUTTON_LABELS[self.selected_mouse_button]}"
        )

    def _commit_mouse_glow_fields(self, show_error: bool = True) -> bool:
        return self._commit_glow_geometry_fields("mouse_glow", show_error)

    def _select_mouse_button(self, button: str) -> None:
        self._commit_mouse_glow_fields(show_error=False)
        self.selected_mouse_button = button
        self.preview_mouse_glow.set(True)
        self._load_mouse_glow_fields()
        self._redraw_preview()

    def _apply_mouse_glow_fields(self) -> None:
        if self._commit_mouse_glow_fields():
            self._redraw_preview()

    @staticmethod
    def _parse_color(value: str) -> list[int]:
        match = re.fullmatch(r"#?([0-9A-Fa-f]{6})", value.strip())
        if not match:
            raise ValueError("색상은 #00FF00 형식으로 입력하세요.")
        hexadecimal = match.group(1)
        return [int(hexadecimal[index : index + 2], 16) for index in (0, 2, 4)]

    def _choose_color(self, variable: tk.StringVar, config_key: str) -> None:
        result = colorchooser.askcolor(color=variable.get(), title="색상 선택")
        if not result[1]:
            return
        variable.set(result[1].upper())
        try:
            self.config[config_key] = self._parse_color(variable.get())
        except ValueError:
            return
        self._redraw_preview()

    @staticmethod
    def _optional_int(value: str) -> int | None:
        stripped = value.strip()
        return None if not stripped else int(stripped)

    def _collect_general_fields(self) -> None:
        try:
            self.config["window_width"] = int(self.window_width.get())
            self.config["window_height"] = int(self.window_height.get())
            self.config["window_x"] = self._optional_int(self.window_x.get())
            self.config["window_y"] = self._optional_int(self.window_y.get())
            self.config["fps"] = int(self.fps.get())
            self.config["right_hand_speed"] = finite_number(self.right_hand_speed.get(), "이동 속도")
            range_x = max(0.0, finite_number(self.right_hand_range_x.get(), "X 범위"))
            range_y = max(0.0, finite_number(self.right_hand_range_y.get(), "Y 범위"))
            self.config["key_glow_alpha"] = int(self.key_glow_alpha.get())
            self.config["mouse_glow_alpha"] = int(self.mouse_glow_alpha.get())
        except ValueError as error:
            raise ValueError("창과 동작 설정에는 올바른 숫자를 입력하세요.") from error
        self.config["right_hand_range"] = [range_x, range_y]
        self.config["background_color"] = self._parse_color(self.background_color.get())
        self.config["key_glow_color"] = self._parse_color(self.key_glow_color.get())
        self.config["mouse_glow_color"] = self._parse_color(
            self.mouse_glow_color.get()
        )
        self.config["window_position_locked"] = self.window_position_locked.get()
        self.config["always_on_top"] = self.always_on_top.get()
        self.config["borderless"] = self.borderless.get()
        self.config["transparent_background"] = self.transparent_background.get()
        self.config["smooth_movement"] = self.smooth_movement.get()

    def _collect_microphone_fields(self) -> None:
        try:
            threshold = max(0.01, finite_number(self.microphone_threshold.get(), "마이크 임계값")) / 100
            high_threshold = max(
                0.01, finite_number(self.microphone_high_threshold.get(), "큰 입 임계값")
            ) / 100
            release_delay = max(
                0.0, finite_number(self.microphone_release_delay.get(), "복귀 시간")
            ) / 1000
        except ValueError as error:
            raise ValueError("마이크 감도와 복귀 시간은 숫자로 입력하세요.") from error
        if high_threshold < threshold:
            raise ValueError("큰 입 임계값은 감지 임계값 이상이어야 합니다.")
        selected_device = self.microphone_device.get()
        self.config["microphone_enabled"] = self.microphone_enabled.get()
        self.config["microphone_device"] = (
            "" if selected_device == DEFAULT_DEVICE_LABEL else selected_device
        )
        self.config["microphone_threshold"] = threshold
        self.config["microphone_high_threshold"] = high_threshold
        self.config["microphone_release_delay"] = release_delay
        self.config["microphone_open_image"] = self.microphone_open_image.get().strip()

    def _validated_draft(self) -> dict[str, Any]:
        original = self.config
        self.config = copy.deepcopy(original)
        try:
            if (not self._commit_image_fields(show_error=False)
                or not self._commit_glow_fields(show_error=False)
                or not self._commit_mouse_glow_fields(show_error=False)):
                raise ValueError("이미지와 발광 설정에는 올바른 숫자를 입력하세요.")
            self._collect_general_fields()
            self._collect_microphone_fields()
            return normalise_config(self.config)
        finally:
            self.config = original

    def _save(self) -> None:
        try:
            self.config = self.model.save(self._validated_draft(), self.config_path)
        except (OSError, ValueError) as error:
            messagebox.showerror("저장 오류", str(error))
            return
        self._sync_general_variables()
        messagebox.showinfo("저장 완료", f"설정을 저장했습니다.\n{self.config_path}")
        self._redraw_preview()

    def _sync_general_variables(self) -> None:
        self.window_width.set(str(self.config["window_width"]))
        self.window_height.set(str(self.config["window_height"]))
        self.window_x.set(
            "" if self.config["window_x"] is None else str(self.config["window_x"])
        )
        self.window_y.set(
            "" if self.config["window_y"] is None else str(self.config["window_y"])
        )
        self.fps.set(str(self.config["fps"]))
        self.right_hand_speed.set(str(self.config["right_hand_speed"]))
        range_x, range_y = self.config["right_hand_range"]
        self.right_hand_range_x.set(self._format_number(range_x))
        self.right_hand_range_y.set(self._format_number(range_y))
        self.key_glow_alpha.set(str(self.config["key_glow_alpha"]))
        self.mouse_glow_alpha.set(str(self.config["mouse_glow_alpha"]))
        self._sync_microphone_variables()
        red, green, blue = self.config["background_color"]
        self.background_color.set(f"#{red:02X}{green:02X}{blue:02X}")
        red, green, blue = self.config["key_glow_color"]
        self.key_glow_color.set(f"#{red:02X}{green:02X}{blue:02X}")
        red, green, blue = self.config["mouse_glow_color"]
        self.mouse_glow_color.set(f"#{red:02X}{green:02X}{blue:02X}")
        self.window_position_locked.set(self.config["window_position_locked"])
        self.always_on_top.set(self.config["always_on_top"])
        self.borderless.set(self.config["borderless"])
        self.transparent_background.set(self.config["transparent_background"])
        self.smooth_movement.set(self.config["smooth_movement"])

    def _sync_microphone_variables(self) -> None:
        self.microphone_enabled.set(self.config["microphone_enabled"])
        self.microphone_device.set(
            self.config["microphone_device"] or DEFAULT_DEVICE_LABEL
        )
        self.microphone_threshold.set(
            self._format_number(self.config["microphone_threshold"] * 100)
        )
        self.microphone_high_threshold.set(
            self._format_number(self.config["microphone_high_threshold"] * 100)
        )
        self.microphone_release_delay.set(
            self._format_number(self.config["microphone_release_delay"] * 1000)
        )
        self.microphone_open_image.set(self.config["microphone_open_image"])

    def _reload(self) -> None:
        self.config = load_config(self.config_path)
        self.model = SettingsModel(self.config)
        self.pil_cache.clear()
        self._sync_general_variables()
        self._refresh_microphone_devices()
        self._load_image_fields()
        self._load_glow_fields()
        self._load_mouse_glow_fields()
        self._redraw_preview()

    def _read_pil_image(self, spec: dict[str, Any]) -> Image.Image | None:
        return self.preview.read_image(spec)

    def _preview_image_size(
        self, name: str, spec: dict[str, Any]
    ) -> tuple[int, int]:
        return self.preview.image_size(name, spec)

    def _draw_layer(
        self,
        composition: Image.Image,
        name: str,
        spec: dict[str, Any],
        position: tuple[float, float] | list[float] | None = None,
    ) -> None:
        self.preview.draw_layer(composition, name, spec, position)

    def _scaled_glow_geometry(
        self, spec: dict[str, Any]
    ) -> tuple[float, float, float, float]:
        return self._glow_transform("glow").glow_geometry(spec)

    def _scaled_mouse_glow_geometry(
        self, spec: dict[str, Any]
    ) -> tuple[float, float, float, float]:
        return self._glow_transform("mouse_glow").glow_geometry(spec)

    def _glow_transform(self, mode: str) -> ImageTransform:
        image_name, reference_size = GLOW_IMAGE_REFERENCES[mode]
        image = self.config["images"][image_name]
        return ImageTransform(
            image["position"], self._preview_image_size(image_name, image), reference_size
        )

    def _draw_selected_glow(self, composition: Image.Image, mode: str) -> None:
        prefix = "mouse" if mode == "mouse_glow" else "key"
        self._draw_glow(
            composition,
            self._glow_transform(mode).glow_geometry(self._selected_glow(mode)),
            self.config[f"{prefix}_glow_color"],
            self.config[f"{prefix}_glow_alpha"],
        )

    @staticmethod
    def _draw_glow(
        composition: Image.Image,
        geometry: tuple[float, float, float, float],
        color_value: list[int],
        alpha: int,
    ) -> None:
        PreviewRenderer.draw_glow(composition, geometry, color_value, alpha)

    def _preview_mode(self) -> str | None:
        selected_tab = self.notebook.select()
        if selected_tab == str(self.image_tab):
            return "image"
        if selected_tab == str(self.glow_tab):
            return "glow"
        if selected_tab == str(self.mouse_glow_tab):
            return "mouse_glow"
        return None

    def _redraw_preview(self) -> None:
        if not hasattr(self, "preview_canvas"):
            return
        preview_mode = self._preview_mode()
        logical_width = int(self.config["window_width"])
        logical_height = int(self.config["window_height"])
        try:
            red, green, blue = self._parse_color(self.background_color.get())
        except ValueError:
            red, green, blue = self.config["background_color"]
        background = (
            (0, 0, 0, 0)
            if self.transparent_background.get()
            else (red, green, blue, 255)
        )
        composition = Image.new("RGBA", (logical_width, logical_height), background)
        show_key_glow = preview_mode == "glow" and self.preview_glow.get()
        if preview_mode == "image" and self.active_image_name.startswith("left_hand_"):
            left_name = self.active_image_name
        else:
            left_name = "left_hand_pressed" if show_key_glow else "left_hand_idle"
        left_spec = self.config["images"][left_name]

        for layer in self.config["layer_order"]:
            if layer == "left_hand":
                if show_key_glow:
                    self._draw_selected_glow(composition, "glow")
                self._draw_layer(composition, layer, left_spec)
            elif layer == "right_hand":
                self._draw_layer(
                    composition, layer, self.config["images"]["right_hand_mouse"]
                )
                if preview_mode == "mouse_glow" and self.preview_mouse_glow.get():
                    self._draw_selected_glow(composition, "mouse_glow")
            elif layer in {"character", "desk_keyboard"}:
                self._draw_layer(composition, layer, self.config["images"][layer])

        canvas_width = max(1, self.preview_canvas.winfo_width())
        canvas_height = max(1, self.preview_canvas.winfo_height())
        self.preview_scale = min(canvas_width / logical_width, canvas_height / logical_height)
        output_size = (
            max(1, round(logical_width * self.preview_scale)),
            max(1, round(logical_height * self.preview_scale)),
        )
        preview = composition.resize(output_size, Image.Resampling.LANCZOS)
        self.preview_photo = ImageTk.PhotoImage(preview)
        origin_x = (canvas_width - output_size[0]) / 2
        origin_y = (canvas_height - output_size[1]) / 2
        self.preview_origin = (origin_x, origin_y)
        self.preview_canvas.delete("all")
        self.preview_canvas.create_image(
            origin_x, origin_y, image=self.preview_photo, anchor=tk.NW
        )

        if preview_mode in GLOW_IMAGE_REFERENCES:
            center_x, center_y, width, height = self._glow_transform(
                preview_mode
            ).glow_geometry(self._selected_glow(preview_mode))
            x, y = center_x - width / 2, center_y - height / 2
            label, outline = (
                (MOUSE_BUTTON_LABELS[self.selected_mouse_button], "#FF7A66")
                if preview_mode == "mouse_glow"
                else (KEY_LABELS[self.selected_key], "#FFCC33")
            )
        elif preview_mode == "image":
            spec = self.config["images"][self.active_image_name]
            width, height = self._preview_image_size(self.active_image_name, spec)
            x, y = spec["position"]
            label = IMAGE_LABELS[self.active_image_name]
            outline = "#66D9EF"
        else:
            return

        x1 = origin_x + x * self.preview_scale
        y1 = origin_y + y * self.preview_scale
        x2 = origin_x + (x + width) * self.preview_scale
        y2 = origin_y + (y + height) * self.preview_scale
        self.preview_canvas.create_rectangle(
            x1, y1, x2, y2, outline=outline, width=2, dash=(5, 3)
        )
        self.preview_canvas.create_text(
            x1 + 4,
            y1 - 6,
            text=label,
            fill=outline,
            anchor=tk.SW,
            font=("Segoe UI", 10, "bold"),
        )

    def _canvas_to_logical(self, x: float, y: float) -> tuple[float, float]:
        origin_x, origin_y = self.preview_origin
        return (
            (x - origin_x) / max(self.preview_scale, 0.0001),
            (y - origin_y) / max(self.preview_scale, 0.0001),
        )

    def _start_drag(self, event: tk.Event[Any]) -> None:
        self._end_drag()
        logical_x, logical_y = self._canvas_to_logical(event.x, event.y)
        mode = self._preview_mode()
        if mode == "image":
            spec = self.config["images"][self.active_image_name]
            x, y = spec["position"]
            width, height = self._preview_image_size(self.active_image_name, spec)
            if not (x <= logical_x <= x + width and y <= logical_y <= y + height):
                return
            self.drag_offset = (logical_x - x, logical_y - y)
            self.drag_target = self.active_image_name
            return
        if mode not in GLOW_IMAGE_REFERENCES:
            return
        center_x, center_y, _width, _height = self._glow_transform(mode).glow_geometry(
            self._selected_glow(mode)
        )
        self.drag_offset = (logical_x - center_x, logical_y - center_y)
        self.drag_target = mode

    def _drag_preview(self, event: tk.Event[Any]) -> None:
        if self.drag_offset is None or self.drag_target is None:
            return
        logical_x, logical_y = self._canvas_to_logical(event.x, event.y)
        if self.drag_target in IMAGE_NAMES:
            new_x = round(logical_x - self.drag_offset[0], 1)
            new_y = round(logical_y - self.drag_offset[1], 1)
            self.config["images"][self.drag_target]["position"] = [new_x, new_y]
            self.image_x.set(self._format_number(new_x))
            self.image_y.set(self._format_number(new_y))
            self._redraw_preview()
            return

        if self.drag_target not in GLOW_IMAGE_REFERENCES:
            return
        new_x, new_y = self._glow_transform(self.drag_target).to_image(
            logical_x - self.drag_offset[0], logical_y - self.drag_offset[1]
        )
        new_position = [round(new_x, 1), round(new_y, 1)]
        self._selected_glow(self.drag_target)["position"] = new_position
        for variable, value in zip(self._glow_variables(self.drag_target), new_position, strict=False):
            variable.set(self._format_number(value))
        self._redraw_preview()

    def _end_drag(self) -> None:
        self.drag_offset = None
        self.drag_target = None


def run_settings(config_path: str | Path | None = None) -> None:
    root = tk.Tk()
    SettingsEditor(root, config_path or default_config_path())
    root.mainloop()

