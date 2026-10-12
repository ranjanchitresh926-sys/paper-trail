@echo off
cd /d "%~dp0"
call .venv\Scripts\activate.bat
if not exist stops.json goto nostops
python scripts\build_hunt.py %*
pause
exit /b 0
:nostops
echo stops.json not found. Run scout.bat first and confirm your stops, see SCOUTING.md.
pause
exit /b 1
