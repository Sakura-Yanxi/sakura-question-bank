@echo off
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
  set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"
) else (
  set "PYTHON_EXE=python"
)

if "%PORT%"=="" (
  set "PORT_VALUE=8000"
) else (
  set "PORT_VALUE=%PORT%"
)
set "APP_URL=http://127.0.0.1:%PORT_VALUE%"

powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r = Invoke-WebRequest -UseBasicParsing '%APP_URL%/api/health' -TimeoutSec 2; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>nul
if not errorlevel 1 (
  echo [Sakura] 服务已经在运行。
  echo [Sakura] 浏览器地址：%APP_URL%
  start "" "%APP_URL%"
  if /I not "%~1"=="/hidden" pause
  exit /b 0
)

echo [Sakura] 项目目录：%CD%
echo [Sakura] Python：%PYTHON_EXE%
echo [Sakura] 浏览器地址：%APP_URL%
echo [Sakura] 正在启动；窗口保持打开表示服务正在运行。
echo [Sakura] 关闭这个窗口会停止本地服务。
echo.

start "" "%APP_URL%"
"%PYTHON_EXE%" "%CD%\app.py"
echo.
echo [Sakura] 服务已停止或启动失败。请检查上方报错。
if /I not "%~1"=="/hidden" pause
endlocal
