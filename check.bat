@echo off
cd /d "%~dp0"
call "%~dp0env.bat"
call .venv\Scripts\activate.bat
python check_setup.py
pause
