from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from config_manager import application_directory
from image_modes import KEYBOARD_MODE_NAME


SESSION_VERSION = 1
READ_ONLY_SESSION_KEY = "_read_only"


def default_session() -> dict[str, Any]:
    return {
        "version": SESSION_VERSION,
        "active_mode": KEYBOARD_MODE_NAME,
        "mode_state": {
            KEYBOARD_MODE_NAME: {"selected_character": 0},
        },
    }


def default_session_path() -> Path:
    return application_directory() / "session.omo"


def normalise_session(value: Any) -> dict[str, Any]:
    default = default_session()
    if not isinstance(value, dict):
        return default

    active_mode = value.get("active_mode")
    if not isinstance(active_mode, str) or not active_mode:
        active_mode = default["active_mode"]

    mode_state: dict[str, dict[str, int]] = {}
    requested_state = value.get("mode_state")
    if isinstance(requested_state, dict):
        for mode_name, state in requested_state.items():
            if not isinstance(mode_name, str) or not isinstance(state, dict):
                continue
            try:
                selected_character = int(state.get("selected_character", 0))
            except (OverflowError, TypeError, ValueError):
                selected_character = 0
            mode_state[mode_name] = {
                "selected_character": max(0, min(9, selected_character))
            }
    mode_state.setdefault(
        KEYBOARD_MODE_NAME,
        {"selected_character": 0},
    )
    return {
        "version": SESSION_VERSION,
        "active_mode": active_mode,
        "mode_state": mode_state,
    }


def load_session(path: str | Path | None = None) -> dict[str, Any]:
    session_path = Path(path) if path else default_session_path()
    try:
        with session_path.open("r", encoding="utf-8") as file:
            loaded = json.load(file)
        if (
            isinstance(loaded, dict)
            and loaded.get("version", SESSION_VERSION) != SESSION_VERSION
        ):
            session = default_session()
            session[READ_ONLY_SESSION_KEY] = True
            print(
                f"[session] 지원하지 않는 세션 버전이라 저장하지 않습니다: "
                f"{loaded.get('version')}"
            )
            return session
        return normalise_session(loaded)
    except FileNotFoundError:
        return default_session()
    except (UnicodeError, json.JSONDecodeError) as error:
        print(f"[session] 세션 파일을 읽을 수 없어 기본값을 사용합니다: {error}")
        return default_session()
    except OSError as error:
        session = default_session()
        session[READ_ONLY_SESSION_KEY] = True
        print(f"[session] 세션 파일을 읽을 수 없어 저장하지 않습니다: {error}")
        return session


def save_session(
    session: dict[str, Any], path: str | Path | None = None
) -> dict[str, Any]:
    session_path = Path(path) if path else default_session_path()
    normalised = normalise_session(session)
    session_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=session_path.parent,
        prefix=f".{session_path.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as file:
            json.dump(normalised, file, ensure_ascii=False, indent=2)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_path, session_path)
    finally:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass
    return normalised
