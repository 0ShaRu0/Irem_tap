# Architecture and verification

Updated for the 2026-10-01 Fish Audio implementation. See [README](../README.md)
for user instructions and [CHANGELOG](../CHANGELOG.md) for the dated validation
record and local executable delivery status.

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
- `voice.py` owns the F11 workflow, local transcription, Fish Audio requests,
  selected-device playback, cancellation and playback-based expression priority.
- `playback_activity.py` shares amplitude and a monotonic timestamp between the
  settings process and overlay through a Windows named memory mapping.
- `config/secrets.py` protects API keys using current-user Windows DPAPI.
- `ui/fish_settings.py` owns voice settings and the headset connection test.
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

## F11 voice workflow

`idle -> recording -> working -> playing -> idle`. F11 ends a recording or
cancels work/playback. Windows F11 uses the same configurable `RegisterHotKey`
wrapper as F10; the keyboard hook skips registered shortcuts to avoid duplicates.

`MicrophoneManager` shares its existing mono int16 input stream with the recorder.
Recording is bounded to 30 seconds and can temporarily open input even when
microphone expression detection is disabled. Input overflow rejects the recording;
short or silent input does not reach the API.

`VoiceController` performs local faster-whisper `base` transcription in Korean,
Fish Audio TTS and PCM playback on a worker thread. Worker status reaches the main
thread through a queue. A per-job event suppresses late responses after cancellation.
An in-flight request/model preparation can finish before a new job is accepted.
Changes to voice settings or input-device/enable settings cancel the active job;
unrelated window changes do not.

The model cache is `speech-models` under the source root for source runs and under
`%LOCALAPPDATA%\iram_tap` for frozen runs. The first transcription can download the
model. PyAV is pinned to 16.1.0 because the tested faster-whisper version uses the
`metadata_errors` argument removed in PyAV 19.

Fish Audio receives the recognized text and `reference_id`, with the selected
model header. The app requests 44.1 kHz mono int16 PCM, adjusts the sample rate and
channels for the selected PortAudio device, and applies playback volume. Output
is one selected route, not simultaneous mirroring. Missing named output devices
fail explicitly; only an empty local device follows the system default. An empty
virtual device is not a valid virtual route.

## Connection test and expression priority

The settings button reads the unsaved API key, voice ID, model, local output and
volume. It synthesizes exactly `fish audio 테스트` and forces the local
speaker/headset route without changing or saving the selected normal output mode.
It does not require a configured virtual device or microphone recording. An empty
key field retains the stored protected key; the delete checkbox removes it from
the test draft as well. Zero volume rejects the audible test. Successful synthesis
and playback produce a completion message; this is not a separate API health ping.

Playback reports the RMS of each roughly 20 ms output chunk after volume scaling.
The overlay applies microphone threshold/high-threshold values to this amplitude.
During F11 recording or conversion, the mouth stays closed even if input is loud.
Fresh playback amplitude, including the settings test, takes priority over ordinary
microphone expression. When the job and short playback tail finish, ordinary
microphone behavior resumes. The renderer still only selects existing cached
character images; missing open-mouth images keep their existing fallback behavior.

The shared mapping name is derived from the normalized absolute config path, so
settings and overlay must use the same `--config` path to share activity. It carries
only amplitude and time, never keys, text or recorded audio. Stale activity expires
after 0.3 seconds, including when the settings process disappears. Cancellation
closes playback, and normal/error completion resets the reported amplitude.

Keys are encrypted in `fish_api_key_protected`; there is no plaintext config field.
Moving settings to another Windows account or PC requires re-entering the key.
Recordings stay in memory for processing. Application logs omit the key, request
body and transcription; the package contains no user configuration.

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
python tools/smoke_voice_settings.py
python tools/smoke_local_stt.py
python tools/package_windows.py
python tools/verify_package.py dist/iram_tap.exe
python tools/smoke_windows.py dist/iram_tap.exe
```

The Windows CI checks Python 3.10, 3.13 and 3.14. Release dependencies in
`requirements-build.lock` target Python 3.14 / Windows x64.
`tools/package_windows.py` uses the current Python interpreter, stages the build
in a temporary directory on the project volume, verifies it, and atomically
replaces `dist/iram_tap.exe`. Intermediate files are removed automatically, and a
failed build preserves the previous EXE. Close the running EXE before packaging.
`clean.bat` only removes intermediates left by the former build process.

CI uploads only `dist/iram_tap.exe` as its artifact. Pushing a `v*` tag runs the
same checks and packaging, then publishes that artifact as a GitHub Release asset.
The release job alone receives write permission. End users download the EXE from
Releases, without Python, source files, or a build command.

Before release, test actual Korean IME composition/Enter/Backspace and focus return,
F9/F10/F11, tray settings, device changes and both image modes on Windows. Headless SDL
tests do not replace real OS focus/IME checks. Test the copied EXE in an empty folder
with a fresh temporary `LOCALAPPDATA`, and preserve existing user settings.

`tools/smoke_windows.py` uses an isolated config and a copied EXE in a directory
with a Korean name and spaces. It asserts actual bubble pixel changes, keyboard
focus, click-through restoration, reset behavior, F11 missing-key guidance, disabled F12 and the settings
window. It requires an unlocked desktop and all other overlay instances closed.
It injects completed Korean Unicode text; native IME composition remains a manual
acceptance check in addition to the deterministic event-sequence unit tests.

`smoke_voice_settings.py` uses temporary settings and a dummy key. It checks the
real Tk UI, DPAPI storage/deletion, unsaved headset-test routing, and cross-process
amplitude sharing without calling Fish Audio. `smoke_local_stt.py` loads/downloads
the local model and decodes synthetic silence through VAD; it does not establish
speech-recognition accuracy. Actual API credentials, audible headset output and
virtual-device routing remain end-to-end checks on the user's hardware. Consult
the changelog for which checks were completed for a particular local build.

## Generated files

`python tools/clean_workspace.py` removes Python caches. After closing the app and
settings, `--legacy` additionally verifies the EXE archive and current config,
archives old `dist/config.json` and `dist/session.omo` in ignored `artifacts/legacy/`,
and removes only byte-identical external image copies. It stops if current images
depend on `dist` or an external image has been customized. Source `character9.png`
is intentionally retained: it is a numbered user-replaceable slot even when its
current bytes equal `character.png`.
