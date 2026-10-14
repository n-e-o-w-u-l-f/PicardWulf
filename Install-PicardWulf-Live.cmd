@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-NEOWULF.ps1" -LiveUpdate
set "rc=%ERRORLEVEL%"
if not "%rc%"=="0" pause
exit /b %rc%
