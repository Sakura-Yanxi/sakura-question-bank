# Sakura 版本发布与用户更新

Sakura 的更新提示走 GitHub Releases。维护者发布 `v1.0.1`、`v1.1.0` 这类版本后，已经下载或部署过的人会在页面里看到提示，并可在页面内一键更新。

一键更新会写入新版代码文件，但不会热更新当前 Python 进程；更新完成后必须重启 Sakura 服务才会生效。

## 当前仓库

- 仓库：`Sakura-Yanxi/sakura-question-bank`
- 默认分支：`main`
- 发布页：[https://github.com/Sakura-Yanxi/sakura-question-bank/releases](https://github.com/Sakura-Yanxi/sakura-question-bank/releases)
- 应用内当前版本来自 `sakura/__init__.py`

## 维护者发布新版本

1. 修改 `sakura/__init__.py`：

   ```python
   __version__ = "1.0.11"
   ```

2. 更新 README 或变更说明，确认版本说明和实际功能一致。

3. 本地检查：

   ```bash
   python -m py_compile app.py notify_daily.py
   python tests/smoke_refactor.py
   git diff --check
   ```

4. 提交并推送到 GitHub：

   ```bash
   git add .
   git commit -m "Release v1.0.11"
   git push origin main
   ```

5. 打开 GitHub 仓库的 **Releases** 页面，点击 **Create a new release**。

6. `Choose a tag` 填 `v1.0.11`，目标分支选 `main`。

7. Release title 写 `v1.0.11`。说明里建议写：

   ```text
   - 主要新增功能
   - 修复的问题
   - 是否需要重启
   - 是否需要重新安装依赖
   - 是否涉及数据迁移
   ```

8. 点击 **Publish release**。用户端下一次检查版本时就能看到新版本。

## v1.0.11 发布说明

建议 GitHub Release 只保留最新版本 `v1.0.11`，避免新用户下载到旧包。

本版本主要修复复盘记录和复习排期的混用问题：

- 保存题目详情标注时，不再自动改动艾宾浩斯的 `last_reviewed_at`、`review_count` 和 `next_review_at`。
- 每日练习正式提交结果时，仍然按复习结果更新保持阶段和下次复习日期。
- 新增旧备注迁移保护：如果旧版本只在 `user_note` 里保存过备注，第一次追加新复盘前会先把旧备注补进多刷记录。
- 更新题目详情脚本缓存版本，部署后浏览器会加载新的保存逻辑。

升级方式：

- Git 安装用户：运行 `update.bat` / `update.sh`，或在页面的“提醒与设置 -> 版本管理”中一键更新。
- Release zip 用户：下载最新源码包覆盖代码文件，保留自己的 `data/`、`.env` 和 `.venv`。
- systemd 服务器部署：页面内更新后会尝试自动重启；手动更新后请执行 `systemctl restart sakura-study.service`。

本版本不需要迁移数据库，不会删除题库、题图、教材、复盘记录、`.env` 或本地虚拟环境。

## 使用者更新

推荐方式是在页面里打开“提醒与设置 -> 版本管理”，看到新版本后点击“一键更新”。

页面会按当前安装方式自动选择：

- Git 仓库：执行 `git pull --ff-only`，再用当前 Python 环境安装依赖。
- Release zip：下载 GitHub Release 源码包，先备份旧代码到 `data/update_backups/`，再覆盖代码文件；默认只保留最近 3 份旧代码备份。

两种方式都会保留 `data/`、`.env` 和 `.venv`。systemd 托管的服务器会在页面内更新完成后自动重启 Sakura；本地窗口运行时需要手动关闭并重新打开。

也可以直接运行项目自带脚本。脚本会自动判断安装方式：是 Git 仓库就拉取代码，不是 Git 仓库就下载最新 Release zip。

```bash
# Windows
update.bat

# Linux / macOS / 服务器
bash update.sh
```

脚本内部会执行其中一种流程：

```bash
# Git 仓库
git pull --ff-only
.venv/bin/python -m pip install -r requirements.txt

# 非 Git 目录
下载最新 Release zip
备份旧代码到 data/update_backups/
清理更旧的 update_backups 备份
覆盖代码文件
.venv/bin/python -m pip install -r requirements.txt
```

它不会碰 `data/`、`.env`、`.venv`、数据库、题图、教材文件和用户上传文件；本仓库额外保留 `docs/software_copyright/`。

不用 Git 且页面无法一键更新的用户，优先运行 `update.bat` / `update.sh`。只有脚本也无法连接 GitHub 时，才需要到 Release 页面下载最新 zip，解压后覆盖代码文件。

如果用户手里的旧版本还没有轻量更新器，需要先手动升级到包含新 `update.bat` / `update.sh` 的版本一次；之后再更新就可以直接用脚本或页面一键更新。

## 应用内版本提示

- 当前版本来自 `sakura/__init__.py`。
- 最新版本来自 GitHub 最新 Release tag。
- 默认检查仓库是 `Sakura-Yanxi/sakura-question-bank`。
- 如果你 fork 或迁移仓库，在 `.env` 设置：

  ```env
  SAKURA_UPDATE_REPO=你的用户名/你的仓库名
  ```

- 检查结果缓存约 6 小时；页面的“版本管理”卡片可以手动刷新。
- 当环境支持自动更新时，顶部横幅和版本管理卡片会显示“一键更新”；否则显示手动下载入口。
- 如果 GitHub 还没有发布 Release、网络失败、限流或私有仓库无权限，页面会显示“暂未连通”，不影响正常使用。

## 常见情况

- 页面不提示更新：先确认 GitHub Releases 里真的发布了比当前版本更高的 tag。
- tag 写错：版本号建议用 `v1.0.1` 这种格式。
- 更新失败：通常是本地改过代码导致 `git pull --ff-only` 无法快进，或网络连接 GitHub 失败。
- 数据会不会丢：不会。更新脚本不删除 `data/` 和 `.env`。
