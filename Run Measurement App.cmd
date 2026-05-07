@echo off
setlocal

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\run_app.ps1" %*
set EXITCODE=%ERRORLEVEL%

if not "%EXITCODE%"=="0" (
    echo.
    echo Python Measurement App exited with code %EXITCODE%.
    pause
)

exit /b %EXITCODE%
