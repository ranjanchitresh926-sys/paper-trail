@echo off
cd /d "%~dp0"
call "%~dp0env.bat"
call .venv\Scripts\activate.bat
if not exist scout.m4a goto norec
python scripts\scout_to_stops.py scout.m4a %*
pause
exit /b 0
:norec
echo scout.m4a not found in this folder. Save your scouting recording here with that exact name.
pause
exit /b 1
