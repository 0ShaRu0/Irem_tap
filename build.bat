@echo off
setlocal
cd /d "%~dp0"

if not defined IRAM_PYTHON if defined VIRTUAL_ENV set "IRAM_PYTHON=%VIRTUAL_ENV%\Scripts\python.exe"
if not defined IRAM_PYTHON if exist ".venv\Scripts\python.exe" set "IRAM_PYTHON=%~dp0.venv\Scripts\python.exe"
if not defined IRAM_PYTHON set "IRAM_PYTHON=py"

echo Building standalone iram_tap.exe with %IRAM_PYTHON%...
"%IRAM_PYTHON%" -X utf8 -m PyInstaller --noconfirm --clean --onefile --windowed --log-level WARN ^
    --name iram_tap --icon=image/keybord_Iram/icon.png ^
    --add-data "image;image" ^
    --hidden-import=pynput.keyboard._win32 ^
    --hidden-import=pynput.mouse._win32 ^
    --hidden-import=pystray._win32 ^
    --hidden-import=sounddevice ^
    --hidden-import=_sounddevice_data ^
    --collect-binaries=_sounddevice_data main.py
if errorlevel 1 goto :error

echo Build complete.
echo Output: %~dp0dist\iram_tap.exe
echo Diagnostics: %~dp0build\iram_tap\warn-iram_tap.txt
exit /b 0

:error
echo Build failed.
echo Close the running EXE before replacing it. Build diagnostics are kept in build\.
exit /b 1
