@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_uv_envs.ps1" %*
exit /b %ERRORLEVEL%
