@echo off
chcp 65001 >nul
REM ============================================================
REM  Sakura 做题集 · 一键更新（Windows）
REM  Git 目录会使用 git pull；普通压缩包目录会下载最新 Release zip。
REM  会保留 data\、.env、.venv 和 docs\software_copyright\。
REM ============================================================
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "VENV_DIR=%CD%\.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"

call "%CD%\scripts\ensure_windows_python.bat"
if errorlevel 1 (
  pause
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
  echo [Sakura] 正在创建本地虚拟环境：%VENV_DIR%
  echo [Sakura] 使用 Python：%BASE_PYTHON_CMD%  %BASE_PYTHON_VERSION%
  !BASE_PYTHON_CMD! -m venv "%VENV_DIR%"
  if errorlevel 1 (
    echo [错误] 虚拟环境创建失败。
    pause
    exit /b 1
  )
)

echo [Sakura] 正在启动轻量更新器。
echo [Sakura] 如果当前目录是 Git 仓库，会使用 git pull；否则会下载 GitHub Release zip。
echo.
"%VENV_PY%" "%CD%\scripts\sakura_updater.py" --pause
exit /b %ERRORLEVEL%

:backup_venv
for /f %%T in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss"') do set "TS=%%T"
set "OLD_VENV=%CD%\.venv.old-!TS!"
move "%VENV_DIR%" "!OLD_VENV!" >nul
if errorlevel 1 (
  echo [Sakura] 无法移动旧 .venv。请先关闭正在运行的 Sakura/Python 窗口后重试。
  pause
  exit /b 1
)
echo [Sakura] 旧 .venv 已保留为：!OLD_VENV!
exit /b 0
