from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Any

from iram_tap.config.secrets import protect_key
from iram_tap.platform.audio import MicrophoneManager
from iram_tap.voice import DEFAULT_OUTPUT, OUTPUT_MODES, VoiceController, output_devices


class FishSettings(ttk.Frame):
    def __init__(self, parent: Any, config: dict[str, Any], config_path: Path | None = None) -> None:
        super().__init__(parent, padding=12)
        self.config_path = config_path
        self.key = tk.StringVar()
        self.delete_key = tk.BooleanVar()
        self.reference = tk.StringVar()
        self.model = tk.StringVar()
        self.mode = tk.StringVar()
        self.local_device = tk.StringVar()
        self.virtual_device = tk.StringVar()
        self.volume = tk.DoubleVar()
        self.status = tk.StringVar()
        self.key_status = tk.StringVar()
        self._tester: VoiceController | None = None
        self._timer: str | None = None
        self._input_error = ""
        self.columnconfigure(0, weight=1)
        ttk.Label(self, text="F11: 녹음 시작 / 종료 · 변환·재생 중 누르면 취소").grid(sticky="w")
        ttk.Label(self, textvariable=self.key_status).grid(sticky="w", pady=(12, 2))
        self.key_entry = ttk.Entry(self, textvariable=self.key, show="*")
        self.key_entry.grid(sticky="ew")
        show = tk.BooleanVar()
        ttk.Checkbutton(self, text="입력한 키 표시", variable=show,
                        command=lambda: self.key_entry.configure(show="" if show.get() else "*")).grid(sticky="w")
        ttk.Checkbutton(self, text="저장된 API 키 삭제", variable=self.delete_key).grid(sticky="w")
        ttk.Label(self, text="목소리 ID (reference_id)").grid(sticky="w", pady=(8, 2))
        ttk.Entry(self, textvariable=self.reference).grid(sticky="ew")
        self.test_button = ttk.Button(self, text="API 키·ID 연결 테스트 (헤드셋)", command=self.test)
        self.test_button.grid(sticky="w", pady=8)
        ttk.Label(self, text='입력한 키·ID로 "fish audio 테스트"를 재생합니다.', wraplength=350).grid(sticky="w")
        ttk.Label(self, textvariable=self.status, wraplength=350).grid(sticky="w")
        ttk.Label(self, text="Fish Audio 모델").grid(sticky="w", pady=(8, 2))
        ttk.Combobox(self, textvariable=self.model, state="readonly",
                     values=("s2-pro", "s2.1-pro", "s2.1-pro-free", "s1")).grid(sticky="ew")
        ttk.Label(self, text="현재 사용할 출력").grid(sticky="w", pady=(12, 2))
        for value, label in OUTPUT_MODES.items():
            ttk.Radiobutton(self, text=label, variable=self.mode, value=value).grid(sticky="w")
        ttk.Label(self, text="스피커·헤드셋 장치").grid(sticky="w", pady=(8, 2))
        self.local_chooser = ttk.Combobox(self, textvariable=self.local_device, state="readonly", width=42)
        self.local_chooser.grid(sticky="ew")
        ttk.Label(self, text="가상 오디오 장치 (예: CABLE Input)").grid(sticky="w", pady=(8, 2))
        self.virtual_chooser = ttk.Combobox(self, textvariable=self.virtual_device, state="readonly")
        self.virtual_chooser.grid(sticky="ew")
        ttk.Button(self, text="출력 장치 새로 고침", command=self.refresh).grid(sticky="w", pady=4)
        ttk.Label(self, text="음량").grid(sticky="w")
        ttk.Scale(self, variable=self.volume, from_=0, to=100).grid(sticky="ew")
        ttk.Label(self, text="연결 테스트는 위 출력 선택과 관계없이 스피커·헤드셋 장치로 재생됩니다.",
                  wraplength=350).grid(sticky="w", pady=8)
        ttk.Label(self, wraplength=350, text=(
            "저장하면 출력 선택이 반영됩니다. 가상 장치는 별도 설치가 필요합니다. "
            "대화 앱에서는 연결된 가상 장치의 녹음 측을 마이크로 선택하세요.\n"
            "음성 인식 모델은 최초 사용 시 다운로드됩니다. 인식된 텍스트는 Fish Audio로 전송되며 API 요금이 발생할 수 있습니다."
        )).grid(sticky="w", pady=8)
        self.load(config)
        self.refresh()
        self.bind("<Destroy>", self._destroy)

    def load(self, config: dict[str, Any]) -> None:
        if self._tester is not None:
            self._tester.reconfigure(config)
        self._config = dict(config)
        self.key.set("")
        self.delete_key.set(False)
        self.key_status.set("API 키 (저장됨 · 빈칸은 기존 키 유지)" if config["fish_api_key_protected"]
                            else "Fish Audio API 키")
        self.reference.set(config["fish_reference_id"])
        self.model.set(config["fish_model"])
        self.mode.set(config["fish_output_mode"])
        self.local_device.set(config["fish_local_device"] or DEFAULT_OUTPUT)
        self.virtual_device.set(config["fish_virtual_device"])
        self.volume.set(config["fish_volume"] * 100)

    def collect(self, config: dict[str, Any], *, headset_test: bool = False) -> None:
        if self.delete_key.get():
            config["fish_api_key_protected"] = ""
        elif self.key.get().strip():
            config["fish_api_key_protected"] = protect_key(self.key.get().strip())
        config["fish_reference_id"] = self.reference.get().strip()
        config["fish_model"] = self.model.get()
        config["fish_output_mode"] = "local" if headset_test else self.mode.get()
        config["fish_local_device"] = "" if self.local_device.get() == DEFAULT_OUTPUT else self.local_device.get()
        config["fish_virtual_device"] = self.virtual_device.get()
        config["fish_volume"] = self.volume.get() / 100
        if config["fish_output_mode"] == "virtual" and not self.virtual_device.get():
            raise ValueError("가상 오디오 출력 장치를 선택하세요.")

    def refresh(self) -> None:
        try:
            names = list(dict.fromkeys(name for _, name in output_devices()))
            self.local_chooser.configure(values=[DEFAULT_OUTPUT, *names])
            self.virtual_chooser.configure(values=names)
            self.status.set("출력 장치 목록을 갱신했습니다.")
        except Exception:
            self.status.set("출력 장치를 읽을 수 없습니다.")

    def test(self) -> None:
        self._input_error = ""
        if self._tester is not None and self._tester.state != "idle":
            self._tester.stop()
            return
        try:
            config = dict(self._config)
            self.collect(config, headset_test=True)
            if self._tester is None:
                self._tester = VoiceController(config, MicrophoneManager(config), self.config_path)
            else:
                self._tester.reconfigure(config)
            self._tester.test_voice()
            if self._timer is None:
                self._poll()
        except (ValueError, OSError) as error:
            self._input_error = str(error)
            self.status.set(str(error))

    def _poll(self) -> None:
        if self._tester is not None:
            self._tester.poll()
            message = self._input_error or self._tester.status
            if message:
                self.status.set(message)
            self.test_button.configure(text="테스트 중지" if self._tester.state != "idle"
                                       else "API 키·ID 연결 테스트 (헤드셋)")
        self._timer = self.after(100, self._poll)

    def _destroy(self, event: Any) -> None:
        if event.widget is not self:
            return
        if self._tester is not None:
            self._tester.close()
        if self._timer is not None:
            self.after_cancel(self._timer)


def create_fish_tab(parent: Any, config: dict[str, Any],
                    config_path: Path | None = None) -> tuple[ttk.Frame, FishSettings]:
    container = ttk.Frame(parent)
    canvas = tk.Canvas(container, highlightthickness=0, width=390)
    scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)
    settings = FishSettings(canvas, config, config_path)
    item = canvas.create_window((0, 0), window=settings, anchor="nw")
    settings.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.bind("<Configure>", lambda event: canvas.itemconfigure(item, width=event.width))
    return container, settings
