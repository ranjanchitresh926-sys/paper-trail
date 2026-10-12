@echo off
setlocal
cd /d "%~dp0"
call "%~dp0env.bat"
python --version >nul 2>&1
if errorlevel 1 goto nopython
if not exist .venv python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install torch --index-url https://download.pytorch.org/whl/cu128
if errorlevel 1 goto fail
pip install -U -r requirements.txt
if errorlevel 1 goto fail
python check_setup.py
echo.
echo Setup finished. Any line marked FAIL tells you what to do. Ollama and model FAILs are normal until you run pull_models.bat.
pause
exit /b 0
:nopython
echo Python was not found. Install Python 3.12 from python.org and tick Add python.exe to PATH, then run this again.
pause
exit /b 1
:fail
echo Something failed above. A dropped download is the usual cause: run setup.bat again.
pause
exit /b 1
