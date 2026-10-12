@echo off
rem Keeps every cache and temp file inside this folder.
set "CACHE=%~dp0cache"
if not exist "%CACHE%" mkdir "%CACHE%"
if not exist "%CACHE%\tmp" mkdir "%CACHE%\tmp"
set "HF_HOME=%CACHE%\hf"
set "PIP_CACHE_DIR=%CACHE%\pip"
set "TEMP=%CACHE%\tmp"
set "TMP=%CACHE%\tmp"
