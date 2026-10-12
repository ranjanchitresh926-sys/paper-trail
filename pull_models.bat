@echo off
cd /d "%~dp0"
where ollama >nul 2>&1
if errorlevel 1 goto noollama
if not exist "%~dp0cache\ollama" mkdir "%~dp0cache\ollama"
setx OLLAMA_MODELS "%~dp0cache\ollama" >nul
echo.
echo Models will be stored in: %~dp0cache\ollama
echo.
echo Quit Ollama from the system tray and start it again so it uses the new model folder.
echo Press a key once it is running.
pause
ollama pull gemma4:e4b
ollama pull gemma4:e2b
ollama list
echo.
echo Models ready. Next: run check.bat
pause
exit /b 0
:noollama
echo Ollama was not found. Install it from https://ollama.com/download, then run this again.
pause
exit /b 1
