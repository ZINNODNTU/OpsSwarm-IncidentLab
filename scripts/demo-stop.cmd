@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0demo-stop.ps1" %*
exit /b %ERRORLEVEL%
