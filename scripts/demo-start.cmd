@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0demo-start.ps1" %*
exit /b %ERRORLEVEL%
