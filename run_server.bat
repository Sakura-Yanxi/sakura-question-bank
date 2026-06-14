@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
  set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"
) else (
  set "PYTHON_EXE=python"
)

"%PYTHON_EXE%" "%CD%\app.py" > "%CD%\server.out.log" 2> "%CD%\server.err.log"
endlocal
