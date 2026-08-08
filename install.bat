@echo off
setlocal
set "ROOT_DIR=%~dp0"
cd /d "%ROOT_DIR%"

echo.
echo ============================================================
echo   Domino Printer Middleware - One-Click Install
echo ============================================================
echo.
echo   IMPORTANT:
echo   - Right-click install.bat -^> Run as administrator
echo     OR run from an Administrator Command Prompt
echo.
echo   This will:
echo     1. Install Python 3.11 via winget if missing
echo     2. Create .venv and pip install requirements
echo     3. Create config\printers.json from example if missing
echo     4. Install DominoPrinterMiddleware Windows service
echo        (auto-start on boot + restart on crash)
echo     5. Verify http://127.0.0.1:5003/health
echo.
echo   Optional public URL later:
echo     install.bat -WithCloudflare
echo.
echo   Full guide: INSTALL_GUIDE.md
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
