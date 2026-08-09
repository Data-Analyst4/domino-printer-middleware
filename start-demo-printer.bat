@echo off
setlocal
cd /d "%~dp0.."
echo.
echo Starting demo Domino printer on 127.0.0.1:7000 ...
echo Keep this window open while testing the middleware.
echo.
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\mock_domino_printer.py --host 127.0.0.1 --port 7000 %*
) else (
  python scripts\mock_domino_printer.py --host 127.0.0.1 --port 7000 %*
)
