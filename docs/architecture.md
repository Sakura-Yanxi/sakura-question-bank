# Sakura Study OS Architecture Notes

Sakura 做题集是一个本地优先的个人学习工作台。当前代码结构的目标是保持轻量，但避免所有功能继续堆在根目录或单个大文件里。

## Backend Layout

后端入口仍然是 `app.py`。它负责启动 HTTP 服务、承载历史 Handler、装配配置和调用各领域模块。领域逻辑放在 `sakura/` 包内。

```text
sakura/
├── core/
├── content/
├── review/
├── ai/
└── system/
```

### `sakura/core`

基础设施层，尽量不放具体学习业务。

- `auth.py`：登录页面、会话签名、登录保护。
- `config.py`：本地 `.env` 读取和写回。
- `db.py`：数据目录、SQLite 连接、schema 初始化和增量迁移。
- `http.py`：JSON、文本、重定向、静态文件响应。
- `parse.py`：请求参数解析、整数和布尔值规范化。
- `routes.py`：API 路由表、动态路由匹配和 Handler 名称检查。

### `sakura/content`

题库、资料、PDF、教材等内容域。

- `classify.py`：章节清洗、章节识别、导入分类。
- `documents.py`：做题本、模拟卷和资料元数据管理。
- `filters.py`：题库筛选 SQL 和下拉选项。
- `importer.py`：PDF 导入流程中的单页和切片处理。
- `models.py`：题目、资料、错因统计等 JSON shaping。
- `pdf.py`：PDF 渲染、题目切片、跨页续题处理。
- `questions.py`：题目增删改查、章节统计、OCR 文本追加。
- `textbook.py`：教材导入、页面上下文、教材 AI 问答。

### `sakura/review`

复习、错题和周期反思域。

- `daily.py`：每日练习规则、批次生成、手机端反馈。
- `export.py`：错题筛选导出 PDF。
- `hints.py`：启发式提示、完整解析 prompt、变式生成。
- `insights.py`：错题洞察、本地 fallback、AI 洞察归一化。
- `reflection.py`：周/月复盘统计、AI 反思和历史记录。
- `retention.py`：复习间隔、错题状态、元认知标签。

### `sakura/ai`

AI 教练和老师记忆域。

- `client.py`：OpenAI-compatible 调用、JSON 提取、AI 老师 turn 构造。
- `coach.py`：学习教练状态、薄弱点、今日任务、AI 计划。
- `profile.py`：学习档案统计、阶段估计、本地画像和 AI polish。
- `teacher_memory.py`：老师记忆、外部经验库、对话回合持久化。

### `sakura/system`

运行时配置、推送、备份和迁移域。

- `backup.py`：备份导出、恢复、安全路径检查。
- `email.py`：SMTP 配置、邮件发送、公开配置视图。
- `migration.py`：迁移任务状态和后台恢复任务。
- `notifications.py`：企业微信、PushPlus、邮箱推送和提醒正文生成。
- `reminders.py`：提醒配置、打卡入口规范化、crontab 安装。
- `settings.py`：运行时设置视图、密钥脱敏、公网地址规范化。
- `weather.py`：天气地区解析、明日天气查询和 fallback。

## Frontend Layout

前端入口仍是 `static/index.html`，样式在 `static/styles.css`，功能脚本按域放入 `static/js/`。

```text
static/js/
├── core/
├── content/
├── review/
├── ai/
└── system/
```

- `core/app.js`：全局状态、公共 API、视图切换、共享渲染工具。
- `content/`：上传、题库、题目详情、做题本、模拟卷、教材精读。
- `review/`：错题本、每日练习、章节统计、错题导出、周期反思。
- `ai/`：AI 对话测试、学习教练、老师记忆、外部经验库。
- `system/`：提醒推送、天气、打卡、数据备份和迁移。

## Boundaries

- `app.py` 可以继续作为轻量装配层，但新增复杂逻辑应优先进入对应 `sakura/` 子包。
- 前端新增功能应放在 `static/js/<domain>/` 下，不再回到 `static/` 根目录。
- 公开部署必须保护 `.env`、数据库、上传文件、日志、导出包和部署密钥。
- UI 改动要保留现有 DOM `id` 和 `data-view`，因为前端事件绑定依赖这些标识。

## Validation

重构或移动模块后至少运行：

```powershell
python -m py_compile app.py notify_daily.py
Get-ChildItem -Path sakura -Recurse -Filter *.py | ForEach-Object { python -m py_compile $_.FullName }
Get-ChildItem -Path static\js -Recurse -Filter *.js | ForEach-Object { node --check $_.FullName }
python tests\smoke_refactor.py
```
