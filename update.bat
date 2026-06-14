@echo off
chcp 65001 >nul
REM ============================================================
REM  Sakura 做题集 · 一键更新（Windows）
REM  有 Git 就拉取代码；没有 Git 也会自动下载最新 Release zip。
REM  会保留 data\、.env、.venv 和 docs\software_copyright\。
REM ============================================================
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "VENV_PY=%CD%\.venv\Scripts\python.exe"

if not exist "%VENV_PY%" (
  set "BASE_PYTHON_CMD="
  python --version >nul 2>nul
  if not errorlevel 1 set "BASE_PYTHON_CMD=python"
  if not defined BASE_PYTHON_CMD (
    py -3 --version >nul 2>nul
    if not errorlevel 1 set "BASE_PYTHON_CMD=py -3"
  )
  if not defined BASE_PYTHON_CMD (
    echo [错误] 未检测到 Python。请先安装 Python 3.10 或更新版本。
    pause
    exit /b 1
  )
  echo [Sakura] 正在创建本地虚拟环境：%CD%\.venv
  !BASE_PYTHON_CMD! -m venv "%CD%\.venv"
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
