from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from iram_tap.assets import asset_roots


KEYBOARD_MODE_NAME = "keybord_Iram"
IRAM_MODE_NAME = "Iram"


@dataclass(frozen=True)
class ImageMode:
    name: str
    kind: str
    directory_name: str

    def asset_path(self, filename: str) -> str:
        return (Path("image") / self.directory_name / filename).as_posix()

    @property
    def expression_paths(self) -> tuple[str, str, str] | None:
        if self.kind != "avatar":
            return None
        return (
            self.asset_path("iram.png"),
            self.asset_path("iram1.png"),
            self.asset_path("iram2.png"),
        )


def discover_image_modes(config_path: str | Path) -> list[ImageMode]:
    directories: dict[str, str] = {}
    for root in reversed(asset_roots(config_path)):
        try:
            directories.update({
                path.name.casefold(): path.name
                for path in (root / "image").iterdir()
                if path.is_dir()
            })
        except OSError:
            continue

    modes: list[ImageMode] = []
    for expected_name, kind in (
        (KEYBOARD_MODE_NAME, "keyboard"),
        (IRAM_MODE_NAME, "avatar"),
    ):
        directory_name = directories.get(expected_name.casefold())
        if directory_name is not None:
            modes.append(ImageMode(expected_name, kind, directory_name))
    return modes
