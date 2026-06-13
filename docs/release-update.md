# Sakura 版本发布与用户更新

这套更新方案走 GitHub Releases：维护者发布 `v1.0.1`、`v1.1.0` 这类版本；已经下载或部署过的人在页面里看到提示后，用更新脚本或下载包升级。程序只提醒，不会自动覆盖正在运行的代码。

## 维护者发布新版本

1. 修改 `sakura/__init__.py`：

   ```python
   __version__ = "1.0.1"
   ```

2. 提交并推送到 GitHub：

   ```bash
   git add .
   git commit -m "Release v1.0.1"
   git push origin demo/sakura-question-bank
   ```

3. 打开 GitHub 仓库的 **Releases** 页面，点击 **Create a new release**。
4. `Choose a tag` 填 `v1.0.1`，目标分支选 `demo/sakura-question-bank`。
5. Release title 可写 `v1.0.1`，说明里写这版改了什么、是否需要重启、是否有迁移。
6. 点击 **Publish release**。用户端下一次检查 `/api/version` 时就能看到新版本。

## 使用者更新

推荐方式是直接运行项目自带脚本：

```bash
# Windows
update.bat

# Linux / macOS / 服务器
bash update.sh
```

脚本只会执行 `git pull --ff-only` 和 `pip install -r requirements.txt`，不会碰 `data/`、`.env`、数据库、题图和用户上传文件。

不用 Git 的用户可以在 Release 页面下载最新 zip，解压后覆盖代码文件。覆盖时保留自己的 `data/` 和 `.env`，然后重启服务。

## 应用内版本提示

- 当前版本来自 `sakura/__init__.py`。
- 最新版本来自 GitHub 最新 Release tag。
- 默认检查仓库是 `Sakura-Yanxi/-`，如果你 fork 或迁移仓库，在 `.env` 设置：

  ```env
  SAKURA_UPDATE_REPO=你的用户名/你的仓库名
  ```

- 检查结果缓存约 6 小时；页面的“版本管理”卡片可以手动刷新。
- 如果 GitHub 还没有发布 Release、网络失败、限流或私有仓库无权限，页面会显示“暂未连通”，不影响正常使用。

