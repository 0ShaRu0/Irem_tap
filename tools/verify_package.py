"""Verify bundled image bytes without launching or modifying the executable."""
from __future__ import annotations

import argparse
from pathlib import Path

from PyInstaller.archive.readers import CArchiveReader


def verify(executable: Path) -> None:
    archive = CArchiveReader(str(executable))
    root = Path(__file__).resolve().parents[1]
    for source in (root / "image").rglob("*.png"):
        name = source.relative_to(root).as_posix().replace("/", "\\")
        assert archive.extract(name) == source.read_bytes(), f"Missing or stale asset: {name}"
    assert "config.json" not in archive.toc, "User config must not be bundled"
    print("Package verified: all default image bytes included; no user config bundled.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    verify(parser.parse_args().executable)
