@echo off
cd /d "%~dp0"
call "%~dp0env.bat"
call .venv\Scripts\activate.bat
python -m pytest -q tests
pause
