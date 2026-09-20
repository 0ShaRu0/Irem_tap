# Architecture and verification

## Entry points

`main.py` and `settings.py` call `iram_tap.bootstrap`. The bootstrap configures
logging and selects either the overlay or settings UI. A built EXE uses the same
entry point for `--settings`. The settings process is intentionally independent:
it may finish editing after the overlay exits, and both use atomic config writes.

## Dependencies

- `models`, `text_mode`, configuration validation and settings merge logic do not
  import SDL or Tk. Commands carry typed actions and payloads.
- `config/defaults.py` is the only hand-maintained default configuration.
- `config/repository.py` owns the lock, atomic replacement and explicit repair backup.
- `assets.py` resolves user paths and bundled resources; `image_modes.py` merges
  available modes instead of choosing one root directory.
- `platform/windows.py` owns Win32 declarations, GDI buffers and window/menu operations.
- `platform/input.py` and `platform/audio.py` own device listeners and streams.
- `app.py` coordinates input, config refresh, window state and rendering.
- `rendering/images.py` caches decoded layers and retains the last good image
  while retrying failures. A config-only change reuses decoded surfaces.
- `rendering/speech_bubble.py` caches the last text surface. The 140-pixel area above
  the character is reserved by the app, so toggling text does not move the character.
- `ui/settings_model.py` uses a three-way field merge. Unmodified fields preserve
  concurrent edits; conflicting edits to the same field fail instead of overwriting.
- `ui/preview.py` and the SDL renderer share geometry and glow rings, but keep
  backend-specific drawing separate.
- `ui/menu_model.py` is shared by the native popup menu and tray.

## Data and migrations

Source runs use the untracked root `config.json`; frozen runs use
`%LOCALAPPDATA%\iram_tap\config.json`. `--config` explicitly overrides the path.
The current JSON schema is version 1; unversioned configurations are migrated.
Future schemas are rejected without overwriting them.

On the first frozen run without AppData settings, an EXE-adjacent legacy config
is imported. Paths to identical bundled images remain portable. Custom relative
images are converted to absolute paths relative to the old config; those custom
files must remain at that location. No user image is deleted or moved by migration.

Settings values are normalized before storage. Non-finite numbers and excessive
image/glow dimensions are rejected before allocation. Normal config saves do not
repair corrupt files automatically. Explicit repository repair keeps a `.bak` copy.

## Text mode

`OFF -> EDITING -> PINNED -> OFF`. Each new edit starts empty. Committed SDL text
and IME composition are separate. Enter is finalized after the current SDL event
batch to accept a trailing IME `TEXTINPUT` event. Input is limited to 500 characters;
the bubble displays up to three lines. While editing, numpad character/mode commands
are ignored. F10 cancels editing or hides a pinned bubble. Failed focus acquisition
cancels the edit instead of silently accepting input in another window.
Windows F10 uses `RegisterHotKey`/`WM_HOTKEY` so the process is eligible to request
foreground focus. The low-level keyboard listener skips this key while registration
is active to avoid double toggles; if registration fails, the error is logged and
the original listener remains available as a fallback.

## Cleanup and diagnostics

The app constructor does not open SDL windows or devices. `run()` starts resources
inside its cleanup scope. Registered resources close in reverse order, continuing
even after a stop error. Logs are per-process rotating files in
`%LOCALAPPDATA%\iram_tap\logs`, available from the tray and popup menus.

## Checks

```bat
python -m ruff check .
python -m mypy
python -m unittest discover -s tests -v
python -m unittest discover -s tests/unit -v
build.bat
python tools/verify_package.py dist/iram_tap.exe
python tools/smoke_windows.py dist/iram_tap.exe
```

The Windows CI checks Python 3.10, 3.13 and 3.14. Release dependencies in
`requirements-build.lock` target Python 3.14 / Windows x64. `build.bat` prefers
`IRAM_PYTHON`, then the active venv, then `.venv`, and finally the Windows `py`
launcher. `clean.bat` removes intermediates, not user data or the executable.

Before release, test actual Korean IME composition/Enter/Backspace and focus return,
F9/F10, tray settings, device changes and both image modes on Windows. Headless SDL
tests do not replace real OS focus/IME checks. Test the copied EXE in an empty folder
with a fresh temporary `LOCALAPPDATA`, and preserve existing user settings.

`tools/smoke_windows.py` uses an isolated config and a copied EXE in a directory
with a Korean name and spaces. It asserts actual bubble pixel changes, keyboard
focus, click-through restoration, reset behavior, disabled F12 and the settings
window. It requires an unlocked desktop and all other overlay instances closed.
It injects completed Korean Unicode text; native IME composition remains a manual
acceptance check in addition to the deterministic event-sequence unit tests.

## Generated files

`python tools/clean_workspace.py` removes Python caches. After closing the app and
settings, `--legacy` additionally verifies the EXE archive and current config,
archives old `dist/config.json` and `dist/session.omo` in ignored `artifacts/legacy/`,
and removes only byte-identical external image copies. It stops if current images
depend on `dist` or an external image has been customized. Source `character9.png`
is intentionally retained: it is a numbered user-replaceable slot even when its
current bytes equal `character.png`.
