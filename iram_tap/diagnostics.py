from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def log_directory() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    return (Path(base) if base else Path.home() / "AppData/Local") / "iram_tap/logs"


def configure_logging() -> None:
    directory = log_directory()
    directory.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [RotatingFileHandler(
        directory / f"iram_tap-{os.getpid()}.log", maxBytes=1_000_000, backupCount=2,
        encoding="utf-8",
    )]
    if sys.stderr is not None:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers, force=True,
    )


def open_logs() -> None:
    directory = log_directory()
    directory.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        os.startfile(directory)
