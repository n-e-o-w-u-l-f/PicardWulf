@echo off
setlocal
rem Opt-in replacement for a locally customized but UUID-confirmed PicardWulf.
rem Original plugin is MOVED intact into a retained rollback directory.
rem The PowerShell installer asks for two separate operator confirmations.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-NEOWULF.ps1" -LiveUpdate -AllowUnrecognizedExisting
set "rc=%ERRORLEVEL%"
if not "%rc%"=="0" pause
exit /b %rc%
