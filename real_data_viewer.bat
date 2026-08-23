@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 (
  echo Python was not found on PATH.
  echo Install Python 3 from https://www.python.org/downloads/
  echo and tick "Add python.exe to PATH".
  echo Then run:  python -m pip install -r requirements.txt
  pause
  exit /b 1
)

python -c "import numpy, matplotlib" >nul 2>&1
if errorlevel 1 (
  echo Installing numpy and matplotlib from requirements.txt ...
  python -m pip install -r requirements.txt
  if errorlevel 1 (
    echo pip install failed.
    pause
    exit /b 1
  )
)

echo Starting the SDD + Fe-55 pulse viewer ...
python real_data_viewer.py
if errorlevel 1 (
  echo The viewer exited with an error.
  pause
  exit /b 1
)
