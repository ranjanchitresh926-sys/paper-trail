@echo off
cd /d "%~dp0"
call "%~dp0env.bat"
call .venv\Scripts\activate.bat
if not exist recording.m4a goto norec
if not exist signs.txt goto nosigns
python scripts\gate_test_whisper.py recording.m4a signs.txt --model small --lang en %*
pause
exit /b 0
:norec
echo recording.m4a not found in this folder. Save your voice recording here with that exact name.
pause
exit /b 1
:nosigns
echo signs.txt not found. Copy signs_TEMPLATE.txt to signs.txt and put your 10 real signs in it.
pause
exit /b 1
