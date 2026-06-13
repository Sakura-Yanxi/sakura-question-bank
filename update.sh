#!/usr/bin/env bash
# ============================================================
#  Sakura 做题集 · 一键更新（Linux / macOS / 服务器）
#  作用：拉取最新代码 + 更新依赖。
#  绝不触碰你的 data/（题库/数据库/题图）和 .env（密钥配置）。
# ============================================================
set -e
cd "$(dirname "$0")"

if ! command -v git >/dev/null 2>&1; then
  echo "[错误] 未检测到 git。"
  echo "可改用「下载最新 zip 覆盖代码文件」的方式更新，覆盖时不要动 data/ 和 .env。"
  exit 1
fi

echo "== 1/2 拉取最新代码 =="
if ! git pull --ff-only; then
  echo
  echo "[错误] git pull 失败：通常是本地代码被改过，或网络/远程仓库问题。"
  echo "放心：你的题库数据在 data/、配置在 .env，都不受影响。"
  exit 1
fi

echo
echo "== 2/2 更新依赖 =="
if command -v python3 >/dev/null 2>&1; then
  PY=python3
else
  PY=python
fi
"$PY" -m pip install -r requirements.txt

echo
echo "✅ 更新完成。请重启服务（python app.py，或你的 systemd / pm2 / screen 进程）。"
