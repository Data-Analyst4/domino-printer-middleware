@echo off
setlocal
cd /d "%~dp0"

net session >nul 2>&1
if errorlevel 1 (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process '%~f0' -Verb RunAs -WorkingDirectory '%~dp0'"
  exit /b
)

set "SERVICE=DominoPrinterMiddleware"
set "CF=DominoCloudflared"
set "NSSM="

if exist "%~dp0nssm.exe" set "NSSM=%~dp0nssm.exe"
if not defined NSSM if exist "%~dp0..\nssm.exe" set "NSSM=%~dp0..\nssm.exe"

if not defined NSSM (
  where nssm >nul 2>&1
  if not errorlevel 1 set "NSSM=nssm"
)

if not defined NSSM (
  echo nssm.exe not found. Service may still be removable via:
  echo   sc stop %SERVICE%
  echo   sc delete %SERVICE%
  sc stop "%SERVICE%" >nul 2>&1
  sc delete "%SERVICE%" >nul 2>&1
  sc stop "%CF%" >nul 2>&1
  sc delete "%CF%" >nul 2>&1
  echo Done.
  pause
  exit /b 0
)

"%NSSM%" stop "%SERVICE%" 2>nul
"%NSSM%" remove "%SERVICE%" confirm 2>nul
"%NSSM%" stop "%CF%" 2>nul
"%NSSM%" remove "%CF%" confirm 2>nul
sc delete "%SERVICE%" >nul 2>&1
sc delete "%CF%" >nul 2>&1

echo Services removed: %SERVICE%, %CF%
pause
