# Sakura 版本发布与用户更新

Sakura 的更新提示走 GitHub Releases。维护者发布 `v1.0.1`、`v1.1.0` 这类版本后，已经下载或部署过的人会在页面里看到提示，再用更新脚本或下载包升级。

程序只提醒，不会自动覆盖正在运行的代码。

## 当前仓库

- 仓库：`Sakura-Yanxi/sakura-question-bank`
- 默认分支：`main`
- 发布页：[https://github.com/Sakura-Yanxi/sakura-question-bank/releases](https://github.com/Sakura-Yanxi/sakura-question-bank/releases)
- 应用内当前版本来自 `sakura/__init__.py`

## 维护者发布新版本

1. 修改 `sakura/__init__.py`：

   ```python
   __version__ = "1.0.3"
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
   git commit -m "Release v1.0.3"
   git push origin main
   ```

5. 打开 GitHub 仓库的 **Releases** 页面，点击 **Create a new release**。

6. `Choose a tag` 填 `v1.0.3`，目标分支选 `main`。

7. Release title 写 `v1.0.3`。说明里建议写：

   ```text
   - 主要新增功能
   - 修复的问题
   - 是否需要重启
   - 是否需要重新安装依赖
   - 是否涉及数据迁移
   ```

8. 点击 **Publish release**。用户端下一次检查版本时就能看到新版本。

## 使用者更新

推荐方式是直接运行项目自带脚本：

```bash
# Windows
update.bat

# Linux / macOS / 服务器
bash update.sh
```

脚本只会执行：

```bash
git pull --ff-only
.venv/bin/python -m pip install -r requirements.txt
```

它不会碰 `data/`、`.env`、数据库、题图、教材文件和用户上传文件。

不用 Git 的用户可以在 Release 页面下载最新 zip，解压后覆盖代码文件。覆盖时保留自己的 `data/` 和 `.env`，然后重启服务。

## 应用内版本提示

- 当前版本来自 `sakura/__init__.py`。
- 最新版本来自 GitHub 最新 Release tag。
- 默认检查仓库是 `Sakura-Yanxi/sakura-question-bank`。
- 如果你 fork 或迁移仓库，在 `.env` 设置：

  ```env
  SAKURA_UPDATE_REPO=你的用户名/你的仓库名
  ```

- 检查结果缓存约 6 小时；页面的“版本管理”卡片可以手动刷新。
- 如果 GitHub 还没有发布 Release、网络失败、限流或私有仓库无权限，页面会显示“暂未连通”，不影响正常使用。

## 常见情况

- 页面不提示更新：先确认 GitHub Releases 里真的发布了比当前版本更高的 tag。
- tag 写错：版本号建议用 `v1.0.1` 这种格式。
- 更新失败：通常是本地改过代码导致 `git pull --ff-only` 无法快进，或网络连接 GitHub 失败。
- 数据会不会丢：不会。更新脚本不删除 `data/` 和 `.env`。
