@echo off
setlocal

echo.
echo ============================================================
echo   yt-dlp GUI  -  One-Click Build Script (Windows)
echo ============================================================
echo.

:: Check Python
where python > nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found.
    echo         Please install from https://www.python.org/
    echo         Make sure to check "Add Python to PATH" during install.
    pause
    exit /b 1
)

for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo [OK] Python %PYVER% detected.
echo.

:: Run build script
echo [INFO] Running build.py ...
echo.
python build.py %*

if errorlevel 1 (
    echo.
    echo [ERROR] Build failed. Please check the log above.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   Build complete!
echo   Output : dist\ytdlp_gui\
echo   ZIP    : dist\ytdlp_gui_v*.zip
echo ============================================================
echo.
pause
