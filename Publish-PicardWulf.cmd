@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Publish-PicardWulf.ps1"
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" echo GitHub-Veroeffentlichung nicht bestaetigt. Fehlercode %RC%.
pause
exit /b %RC%
