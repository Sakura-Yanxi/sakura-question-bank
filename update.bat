@echo off
chcp 65001 >nul
REM ============================================================
REM  Sakura 做题集 · 一键更新（Windows）
REM  作用：拉取最新代码 + 更新依赖。
REM  绝不触碰你的 data\（题库/数据库/题图）和 .env（密钥配置）。
REM ============================================================
setlocal
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
python -m pip install -r requirements.txt

echo.
echo ✅ 更新完成。请重新启动服务：双击 run_server.bat，或运行 python app.py。
pause
endlocal
