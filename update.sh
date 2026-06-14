#!/usr/bin/env bash
# ============================================================
#  Sakura 做题集 · 一键更新（Linux / macOS / 服务器）
#  有 Git 就拉取代码；没有 Git 也会自动下载最新 Release zip。
#  会保留 data/、.env、.venv 和 docs/software_copyright/。
# ============================================================
set -e
cd "$(dirname "$0")"

if [ ! -x ".venv/bin/python" ]; then
  if command -v python3 >/dev/null 2>&1; then
    BASE_PY=python3
  else
    BASE_PY=python
  fi
  echo "[Sakura] 正在创建本地虚拟环境：$(pwd)/.venv"
  "$BASE_PY" -m venv .venv
fi

echo "[Sakura] 正在启动轻量更新器。"
echo "[Sakura] 如果当前目录是 Git 仓库，会使用 git pull；否则会下载 GitHub Release zip。"
echo
".venv/bin/python" "scripts/sakura_updater.py"
