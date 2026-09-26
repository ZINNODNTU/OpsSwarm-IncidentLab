@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0competition-demo.ps1" %*
exit /b %ERRORLEVEL%
