@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo First run: installing...
  python -m venv .venv || goto :error
)
rem Installs anything new after an update; takes a second when everything is already there.
".venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check -r requirements.txt || goto :error
".venv\Scripts\python.exe" run.py
goto :eof

:error
echo Setup failed. Make sure Python is installed and on PATH.
pause
