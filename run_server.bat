@echo off
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "PORT_VALUE=%PORT%"
if "%PORT_VALUE%"=="" if exist ".env" (
  for /f "usebackq tokens=1,* delims==" %%A in (`findstr /R /B /C:"PORT=" ".env" 2^>nul`) do (
    if /I "%%A"=="PORT" set "PORT_VALUE=%%B"
  )
)
if "%PORT_VALUE%"=="" set "PORT_VALUE=8000"
set "PORT_VALUE=%PORT_VALUE:"=%"
set "APP_URL=http://127.0.0.1:%PORT_VALUE%"

powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r = Invoke-WebRequest -UseBasicParsing '%APP_URL%/api/health' -TimeoutSec 2; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>nul
if not errorlevel 1 (
  echo [Sakura] 服务已经在运行。
  echo [Sakura] 浏览器地址：%APP_URL%
  start "" "%APP_URL%"
  if /I not "%~1"=="/hidden" pause
  exit /b 0
)

set "VENV_PY=%CD%\.venv\Scripts\python.exe"

if not exist "%VENV_PY%" (
  set "BASE_PYTHON_CMD="
  where py >nul 2>nul
  if not errorlevel 1 set "BASE_PYTHON_CMD=py -3"
  if not defined BASE_PYTHON_CMD (
    where python >nul 2>nul
    if not errorlevel 1 set "BASE_PYTHON_CMD=python"
  )
  if not defined BASE_PYTHON_CMD (
    echo [Sakura] 没有检测到 Python。
    echo [Sakura] 请先安装 Python 3.10 或更新版本，并勾选 Add Python to PATH。
    if /I not "%~1"=="/hidden" pause
    exit /b 1
  )
  echo [Sakura] 第一次运行，正在创建本地虚拟环境：%CD%\.venv
  %BASE_PYTHON_CMD% -m venv "%CD%\.venv"
  if errorlevel 1 (
    echo [Sakura] 虚拟环境创建失败，请检查 Python 是否安装完整。
    if /I not "%~1"=="/hidden" pause
    exit /b 1
  )
)

set "PYTHON_EXE=%VENV_PY%"

echo [Sakura] 正在检查依赖，已安装的依赖会自动跳过。
"%PYTHON_EXE%" -m pip install --disable-pip-version-check -r "%CD%\requirements.txt"
if errorlevel 1 (
  echo [Sakura] 依赖安装失败，请检查网络后重新运行本文件。
  if /I not "%~1"=="/hidden" pause
  exit /b 1
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
