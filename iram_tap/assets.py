from __future__ import annotations

import os
import sys
from pathlib import Path

from iram_tap.config.defaults import APPLICATION_NAME


def application_directory() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def resource_directory() -> Path:
    bundle_directory = getattr(sys, "_MEIPASS", None)
    return Path(bundle_directory).resolve() if bundle_directory else application_directory()


def user_data_directory() -> Path:
    if not getattr(sys, "frozen", False):
        return application_directory()
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return base / APPLICATION_NAME


def default_config_path() -> Path:
    return user_data_directory() / "config.json"


def asset_roots(config_path: str | Path | None = None) -> tuple[Path, ...]:
    local = Path(config_path).resolve().parent if config_path else user_data_directory()
    return tuple(dict.fromkeys((local, resource_directory())))


def resolve_asset_path(path_value: str, config_path: str | Path | None = None) -> Path:
    path = Path(path_value).expanduser()
    if path.is_absolute():
        return path.resolve()
    candidates = [(base / path).resolve() for base in asset_roots(config_path)]
    return next((candidate for candidate in candidates if candidate.exists()), candidates[0])


def file_signature(path: Path) -> tuple[int, int, int] | None:
    try:
        information = path.stat()
        return information.st_mtime_ns, information.st_ctime_ns, information.st_size
    except OSError:
        return None
