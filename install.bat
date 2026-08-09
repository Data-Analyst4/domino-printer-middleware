@echo off
setlocal
set "ROOT_DIR=%~dp0"
cd /d "%ROOT_DIR%"

:: Self-elevate to Administrator (one click)
net session >nul 2>&1
if errorlevel 1 (
  echo Requesting Administrator privileges...
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "Start-Process -FilePath '%~f0' -ArgumentList '%*' -Verb RunAs -WorkingDirectory '%ROOT_DIR%'"
  exit /b
)

echo.
echo ============================================================
echo   Domino Printer Middleware - One-Click Install
echo ============================================================
echo.
echo   This will:
echo     1. Install Python 3.11 via winget if missing
echo     2. Create .venv and pip install requirements
echo     3. Create config files from examples if missing
echo     4. Install DominoPrinterMiddleware Windows service
echo        (auto-start on boot + restart on crash)
echo     5. Install Cloudflare tunnel service when possible
echo        -^> https://domino-print.k95foods.com
echo     6. Verify local (and public) /health
echo.
echo   LAN only:  install.bat -SkipCloudflare
echo   Guide:     INSTALL_GUIDE.md
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT_DIR%scripts\install-windows.ps1" %*
set "RC=%ERRORLEVEL%"

echo.
if not "%RC%"=="0" (
  echo [ERROR] Install failed with exit code %RC%.
) else (
  echo [OK] Install finished.
)
echo.
pause
exit /b %RC%
