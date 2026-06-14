@echo off
chcp 65001 >nul
REM ============================================================
REM  Sakura 做题集 · 一键更新（Windows）
REM  作用：拉取最新代码 + 更新依赖。
REM  绝不触碰你的 data\（题库/数据库/题图）和 .env（密钥配置）。
REM ============================================================
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

where git >nul 2>nul
if errorlevel 1 (
  echo [错误] 未检测到 git。
  echo 你可以改用「下载最新 zip，解压后覆盖代码文件」的方式更新，
  echo 覆盖时不要动 data\ 和 .env 即可。
  pause
  exit /b 1
)

echo == 1/2 拉取最新代码 ==
git pull --ff-only
if errorlevel 1 (
  echo.
  echo [错误] git pull 失败：通常是本地代码被改过，或网络/远程仓库问题。
  echo 放心：你的题库数据在 data\、配置在 .env，都不受影响。
  pause
  exit /b 1
)

echo.
echo == 2/2 更新依赖 ==
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
  echo 正在创建本地虚拟环境：%CD%\.venv
  !BASE_PYTHON_CMD! -m venv "%CD%\.venv"
  if errorlevel 1 (
    echo [错误] 虚拟环境创建失败。
    pause
    exit /b 1
  )
)
"%VENV_PY%" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
  echo [错误] 依赖安装失败，请检查网络后重试。
  pause
  exit /b 1
)

echo.
echo ✅ 更新完成。请重新启动服务：双击 run_server.bat。
pause
endlocal
