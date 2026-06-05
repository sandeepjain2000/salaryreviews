@echo off
title Salary Review Portal Launcher
echo ==================================================
echo Starting Salary Review Portal...
echo ==================================================
echo.

:: Refresh PATH from registry just in case execution environment context is stale
for /f "tokens=2*" %%a in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "USER_PATH=%%b"
for /f "tokens=2*" %%a in ('reg query "HKLM\System\CurrentControlSet\Control\Session Manager\Environment" /v Path 2^>nul') do set "MACHINE_PATH=%%b"
set "PATH=%USER_PATH%;%MACHINE_PATH%;%PATH%"

python --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python is not found in your PATH. 
    echo Please make sure Python is installed and check "Add Python to PATH" in the installer.
    echo.
    pause
    exit /b 1
)

echo Calling Streamlit server...
python -m streamlit run app.py
if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Failed to start the Streamlit server.
    echo Checking Python dependencies...
    echo.
    echo Please ensure dependencies are installed by running:
    echo pip install streamlit pandas openpyxl plotly
    echo.
    pause
)
