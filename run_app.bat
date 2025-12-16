@echo off
setlocal enabledelayedexpansion

REM Batch script to set up .venv, install deps, and run the app
REM Usage: double-click or run from terminal

REM Move to script directory
pushd "%~dp0"

REM Detect Python
for %%P in (python.exe py.exe) do (
  where %%P >nul 2>nul && set PYCMD=%%P && goto :found
)
echo Python not found in PATH. Please install Python 3.10+ and retry.
goto :end

:found
REM Create venv if missing
if not exist .venv (
  echo Creating virtual environment in .venv ...
  %PYCMD% -m venv .venv
  if errorlevel 1 (
    echo Failed to create virtual environment.
    goto :end
  )
)

REM Activate venv
call .venv\Scripts\activate
if errorlevel 1 (
  echo Failed to activate virtual environment.
  goto :end
)

REM Upgrade pip
python -m pip install --upgrade pip

REM Install dependencies
if exist requirements.txt (
  echo Installing requirements from requirements.txt ...
  python -m pip install -r requirements.txt
) else (
  echo requirements.txt not found; installing core deps ...
  python -m pip install flask flask-socketio python-socketio[client] eventlet pyserial
)

REM Optional environment variables
set SECRET_KEY=development-secret
set SERIAL_BAUD=115200
set LOG_DIR=%CD%\logs

REM Run the app
python app.py

REM Deactivate and return
call .venv\Scripts\deactivate 2>nul
:done
popd
:end
