@echo off
setlocal
cd /d "%~dp0"
python scripts\sprint5_voice_replan_smoke.py
echo.
if errorlevel 1 (
  echo [FAILED] Sprint 5 Voice Replan smoke failed.
) else (
  echo [PASSED] Sprint 5 Voice Replan smoke passed.
)
pause
