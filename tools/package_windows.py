"""Build and verify the standalone Windows EXE (developer/CI use only)."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile

from verify_package import verify


def package() -> None:
    if os.name != "nt":
        raise RuntimeError("Build the Windows EXE on Windows")
    root = Path(__file__).resolve().parents[1]
    output = root / "dist"
    output.mkdir(exist_ok=True)
    # Keep staging on the same volume so replacement is atomic. A failed build
    # or verification leaves the previous executable intact.
    with tempfile.TemporaryDirectory(prefix=".package-", dir=root) as temporary:
        staging = Path(temporary)
        subprocess.run([
            sys.executable, "-X", "utf8", "-m", "PyInstaller",
            "--noconfirm", "--clean", "--onefile", "--windowed",
            "--log-level", "WARN", "--name", "iram_tap",
            "--icon", str(root / "image/keybord_Iram/icon.png"),
            "--add-data", f"{root / 'image'};image",
            "--hidden-import", "pynput.keyboard._win32",
            "--hidden-import", "pynput.mouse._win32",
            "--hidden-import", "pystray._win32",
            "--hidden-import", "sounddevice",
            "--hidden-import", "_sounddevice_data",
            "--collect-binaries", "_sounddevice_data",
            "--collect-all", "faster_whisper",
            "--collect-all", "ctranslate2",
            "--collect-all", "tokenizers",
            "--collect-all", "onnxruntime",
            "--collect-all", "av",
            "--copy-metadata", "huggingface-hub",
            "--distpath", str(staging / "dist"),
            "--workpath", str(staging / "build"),
            "--specpath", str(staging),
            str(root / "main.py"),
        ], cwd=root, check=True, env={
            **os.environ, "PYINSTALLER_CONFIG_DIR": str(staging / "cache"),
        })
        executable = staging / "dist/iram_tap.exe"
        verify(executable)
        try:
            executable.replace(output / "iram_tap.exe")
        except PermissionError as error:
            raise RuntimeError("Close iram_tap.exe before replacing it") from error
    print(f"Ready to distribute: {output / 'iram_tap.exe'}")


if __name__ == "__main__":
    package()
