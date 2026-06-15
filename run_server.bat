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

set "VENV_DIR=%CD%\.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"

call "%CD%\scripts\ensure_windows_python.bat"
if errorlevel 1 (
  if /I not "%~1"=="/hidden" pause
  exit /b 1
)

if exist "%VENV_DIR%" if not exist "%VENV_PY%" (
  echo [Sakura] 检测到旧的虚拟环境格式，准备重建 .venv。
  call :backup_venv
  if errorlevel 1 exit /b 1
)

if exist "%VENV_PY%" (
  "%VENV_PY%" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) and sys.maxsize > 2**32 else 1)" >nul 2>nul
  if errorlevel 1 (
    echo [Sakura] 当前 .venv 不是 64 位 Python 3.10+，准备自动重建。
    "%VENV_PY%" -c "import sys, platform; print('[Sakura] 旧 .venv Python：{} ({})'.format(sys.version.split()[0], platform.architecture()[0]))" 2>nul
    call :backup_venv
    if errorlevel 1 exit /b 1
  )
)

if not exist "%VENV_PY%" (
  echo [Sakura] 第一次运行，正在创建本地虚拟环境：%VENV_DIR%
  echo [Sakura] 使用 Python：%BASE_PYTHON_CMD%  %BASE_PYTHON_VERSION%
  !BASE_PYTHON_CMD! -m venv "%VENV_DIR%"
  if errorlevel 1 (
    echo [Sakura] 虚拟环境创建失败，请检查 Python 是否安装完整。
    if /I not "%~1"=="/hidden" pause
    exit /b 1
  )
)

set "PYTHON_EXE=%VENV_PY%"
"%PYTHON_EXE%" -c "import sys, platform; print('[Sakura] 当前运行环境：Python {} ({})'.format(sys.version.split()[0], platform.architecture()[0]))"

echo [Sakura] 正在检查依赖，已安装的依赖会自动跳过。
"%PYTHON_EXE%" -m ensurepip --upgrade >nul 2>nul
"%PYTHON_EXE%" -m pip install --disable-pip-version-check --upgrade pip setuptools wheel
if errorlevel 1 (
  echo [Sakura] pip 升级失败，将继续尝试安装依赖。
)

"%PYTHON_EXE%" -m pip install --disable-pip-version-check -r "%CD%\requirements.txt"
if errorlevel 1 (
  echo [Sakura] 默认源安装失败，正在改用官方 PyPI 重试。
  "%PYTHON_EXE%" -m pip install --disable-pip-version-check -i https://pypi.org/simple -r "%CD%\requirements.txt"
)
if errorlevel 1 (
  echo [Sakura] 依赖安装失败。
  echo [Sakura] 如果仍提示 PyMuPDF 没有匹配版本，请确认当前环境是 64 位 Python 3.10+。
  echo [Sakura] 也可以删除本目录下的 .venv 文件夹后重新双击本文件。
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
echo [Sakura] 服务已停止或启动失败，请检查上方报错。
if /I not "%~1"=="/hidden" pause
endlocal
exit /b 0

:backup_venv
for /f %%T in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss"') do set "TS=%%T"
set "OLD_VENV=%CD%\.venv.old-!TS!"
move "%VENV_DIR%" "!OLD_VENV!" >nul
if errorlevel 1 (
  echo [Sakura] 无法移动旧 .venv。请先关闭正在运行的 Sakura/Python 窗口后重试。
  if /I not "%~1"=="/hidden" pause
  exit /b 1
)
echo [Sakura] 旧 .venv 已保留为：!OLD_VENV!
exit /b 0
