@echo off
setlocal
cd /d "%~dp0"

echo [1/2] Building standalone iram_tap.exe...
py -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name iram_tap --icon=image/keybord_Iram/icon.png ^
    --add-data "image;image" ^
    --hidden-import=pynput.keyboard._win32 ^
    --hidden-import=pynput.mouse._win32 ^
    --hidden-import=pystray._win32 ^
    --hidden-import=sounddevice ^
    --hidden-import=_sounddevice_data ^
    --collect-binaries=_sounddevice_data main.py
if errorlevel 1 goto :error

echo [2/2] Cleaning intermediate files...
if exist "build" rmdir /S /Q "build"
if errorlevel 1 goto :error
if exist "iram_tap.spec" del /Q "iram_tap.spec"
if errorlevel 1 goto :error

echo Build complete.
echo Output: %~dp0dist\iram_tap.exe
exit /b 0

:error
echo Build failed.
exit /b 1
