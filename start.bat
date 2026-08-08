@echo off
REM Start Domino middleware on port 5003 (separate from Rynan)
cd /d "%~dp0"
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python.exe main.py %*
) else (
  python main.py %*
)
