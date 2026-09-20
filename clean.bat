@echo off
setlocal
cd /d "%~dp0"
if exist "build" rmdir /S /Q "build"
if errorlevel 1 exit /b 1
if exist "iram_tap.spec" del /Q "iram_tap.spec"
exit /b %errorlevel%
