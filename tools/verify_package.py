"""Verify standalone runtime and image bytes without launching the executable."""
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
    names = {name.replace("\\", "/") for name in archive.toc}
    assert any(name.startswith("python3") and name.endswith(".dll") for name in names), (
        "Python runtime is missing"
    )
    for required in (
        "SDL2.dll", "_tkinter.pyd", "_tcl_data/init.tcl", "_tk_data/tk.tcl",
        "_sounddevice_data/portaudio-binaries/libportaudio64bit.dll",
    ):
        assert required in names, f"Missing runtime file: {required}"
    modules = archive.open_embedded_archive("PYZ.pyz")
    for required in (
        "iram_tap.bootstrap", "iram_tap.ui.settings_editor", "pygame", "PIL.Image",
        "tkinter", "sounddevice", "pynput.keyboard._win32", "pynput.mouse._win32",
        "pystray._win32",
    ):
        assert required in modules.toc, f"Missing runtime module: {required}"
    print("Package verified: runtime and all default images included; no user config bundled.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    verify(parser.parse_args().executable)
