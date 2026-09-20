"""Remove generated caches; optionally archive and remove verified legacy files."""
from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path

from verify_package import verify


def clean(legacy: bool = False) -> None:
    root = Path(__file__).resolve().parents[1]
    cache_roots = [root / "__pycache__"]
    for directory in ("iram_tap", "tests", "tools"):
        cache_roots.extend((root / directory).rglob("__pycache__"))
    for cache in cache_roots:
        if cache.is_dir():
            shutil.rmtree(cache)
    if not legacy:
        return
    dist = root / "dist"
    verify(dist / "iram_tap.exe")
    local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
    current_path = local / "iram_tap/config.json"
    if not current_path.is_file():
        raise RuntimeError("Run the new EXE once to migrate your config before legacy cleanup")
    current = json.loads(current_path.read_text(encoding="utf-8"))
    paths = [current.get("icon_path", ""), current.get("microphone_open_image", "")]
    paths.extend(spec.get("path", "") for spec in current.get("images", {}).values())
    for value in paths:
        resolved = (current_path.parent / Path(value).expanduser()).resolve()
        if resolved.is_relative_to(dist.resolve()):
            raise RuntimeError(f"A current user image still depends on dist: {resolved}")
    images = dist / "image"
    if images.exists():
        for duplicate in images.rglob("*"):
            if duplicate.is_file():
                original = root / duplicate.relative_to(dist)
                if not original.is_file() or original.read_bytes() != duplicate.read_bytes():
                    raise RuntimeError(f"Custom image preserved; cleanup stopped: {duplicate}")
    backup = root / "artifacts/legacy"
    backup.mkdir(parents=True, exist_ok=True)
    for name in ("config.json", "session.omo"):
        source = dist / name
        if source.is_file():
            destination = backup / name
            if destination.exists() and destination.read_bytes() != source.read_bytes():
                raise RuntimeError(f"Existing legacy backup differs: {destination}")
            shutil.copy2(source, destination)
            source.unlink()
    if images.exists():
        shutil.rmtree(images)
    (dist / ".config.json.lock").unlink(missing_ok=True)
    print(f"Legacy settings/session archived in {backup}; verified image copies removed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--legacy", action="store_true", help="Close the app and settings before use")
    clean(parser.parse_args().legacy)
