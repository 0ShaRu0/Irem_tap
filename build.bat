@echo off
setlocal
cd /d "%~dp0"

echo [1/3] Building iram_tap.exe...
py -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name iram_tap --icon=image/keybord_Iram/icon.png ^
    --hidden-import=pynput.keyboard._win32 ^
    --hidden-import=pynput.mouse._win32 ^
    --hidden-import=pystray._win32 ^
    --hidden-import=sounddevice ^
    --hidden-import=_sounddevice_data ^
    --collect-binaries=_sounddevice_data main.py
if errorlevel 1 goto :error

echo [2/3] Copying external configuration...
if not exist "dist\config.json" copy /Y "config.json" "dist\config.json" >nul
if errorlevel 1 goto :error
if exist "dist\image" rmdir /S /Q "dist\image"
if errorlevel 1 goto :error
if not exist "dist\image" mkdir "dist\image"
if errorlevel 1 goto :error
xcopy "image\*" "dist\image\" /E /I /Y >nul
if errorlevel 2 goto :error

echo [3/3] Cleaning intermediate files...
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
