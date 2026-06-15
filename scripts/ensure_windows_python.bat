@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "SELECTED_PYTHON_CMD="
set "SELECTED_PYTHON_VERSION="

call :try_candidate "py -3.12"
if defined SELECTED_PYTHON_CMD goto :found
call :try_candidate "py -3.11"
if defined SELECTED_PYTHON_CMD goto :found
call :try_candidate "py -3.10"
if defined SELECTED_PYTHON_CMD goto :found
call :try_candidate "python"
if defined SELECTED_PYTHON_CMD goto :found
call :try_candidate "py -3"
if defined SELECTED_PYTHON_CMD goto :found

echo [Sakura] 没有检测到可用的 64 位 Python 3.10 或更新版本。
echo [Sakura] 请安装 64 位 Python 3.11/3.12，并在安装时勾选 Add python.exe to PATH。
echo [Sakura] 下载地址：https://www.python.org/downloads/windows/
exit /b 1

:found
for /f "delims=" %%V in ('!SELECTED_PYTHON_CMD! -c "import sys; print('{}.{}.{}'.format(*sys.version_info[:3]))" 2^>nul') do set "SELECTED_PYTHON_VERSION=%%V"
endlocal & set "BASE_PYTHON_CMD=%SELECTED_PYTHON_CMD%" & set "BASE_PYTHON_VERSION=%SELECTED_PYTHON_VERSION%"
exit /b 0

:try_candidate
set "CANDIDATE=%~1"
%CANDIDATE% -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) and sys.maxsize > 2**32 else 1)" >nul 2>nul
if not errorlevel 1 set "SELECTED_PYTHON_CMD=%CANDIDATE%"
exit /b 0
