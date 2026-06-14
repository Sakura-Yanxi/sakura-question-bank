# Sakura 做题集架构说明

Sakura 做题集是一个本地优先的个人学习工作台。当前代码结构的目标是保持轻量，同时避免所有功能继续堆在单个大文件里。

## 总体分层

后端入口仍然是 `app.py`。它负责：

- 启动本地 HTTP 服务。
- 装配运行时配置。
- 处理历史 Handler 和路由分发。
- 调用 `sakura/` 包里的领域模块。

主要业务逻辑已经拆到 `sakura/`：

```text
sakura/
├── ai/
├── api/
├── content/
├── core/
├── review/
└── system/
```

当前 `app.py` 约 `2670` 行。继续减少行数不是首要目标，稳定保留现有行为更重要。新增复杂逻辑应优先放进对应模块。

## 后端模块

### `sakura/core`

基础设施层，尽量不放具体学习业务。

- `auth.py`：登录页面、会话签名、登录保护、公开路径判断、Cookie 读取。
- `config.py`：本地 `.env` 读取和写回。
- `db.py`：数据目录、SQLite 连接、schema 初始化和增量迁移。
- `http.py`：JSON、文本、重定向、静态文件响应、附件下载、临时文件流式下载、上传表单读取。
- `parse.py`：请求参数解析、整数和布尔值规范化。
- `routes.py`：API 路由表、动态路由匹配和 Handler 名称检查。
- `security.py`：登录失败记录、锁定策略、安全事件和密码规则。

### `sakura/content`

题库、资料、PDF、教材等内容域。

- `classify.py`：章节清洗、章节识别、导入分类。
- `documents.py`：做题本、模拟卷和资料元数据管理。
- `filters.py`：题库筛选 SQL 和下拉选项。
- `importer.py`：PDF 导入流程中的单页和切片处理。
- `models.py`：题目、资料、题目详情、错因统计等前端 payload 组装。
- `ocr.py`：页面 OCR 文本读取。
- `pdf.py`：PDF 渲染、题目切片、跨页续题处理。
- `questions.py`：题目增删改查、章节统计、OCR 文本追加、复盘备注。
- `textbook.py`：教材导入、页面上下文、段落选择、教材问答辅助逻辑。

### `sakura/api`

把较长的导入和教材流程从 `app.py` 中抽出，作为运行时流程层。

- `document_runtime.py`：普通题本和模拟卷 PDF 导入流程。
- `textbook_runtime.py`：教材 PDF 导入、教材页面上下文、教材文字讲解和视觉读取调用。

### `sakura/review`

复习、错题和周期反思域。

- `daily.py`：每日练习规则、批次生成、手机端反馈。
- `export.py`：错题筛选导出 PDF、每日练习批次 PDF。
- `hints.py`：启发式提示、完整解析提示词、变式练习。
- `insights.py`：错题洞察、本地回退、讲解结果归一化。
- `reflection.py`：周/月复盘统计、智能反思和历史记录。
- `retention.py`：复习间隔、错题状态、元认知标签。

### `sakura/ai`

学习教练、学习档案和老师记忆域。

- `client.py`：兼容 OpenAI 调用格式的请求、JSON 提取、老师对话回合构造。
- `coach.py`：学习教练状态、薄弱点、今日任务、阶段计划。
- `profile.py`：学习档案统计、档案历史读取、阶段估计、本地学习画像。
- `teacher_memory.py`：老师记忆、记忆压缩、外部经验库、老师对话回合持久化。

### `sakura/system`

运行时配置、推送、备份和迁移域。

- `backup.py`：备份导出、临时 zip 构建、恢复、安全路径检查。
- `email.py`：SMTP 配置、邮件发送、公开配置视图。
- `migration.py`：迁移任务状态和后台恢复任务。
- `notifications.py`：企业微信、PushPlus、邮箱推送、按渠道发送、提醒正文生成。
- `practice_pages.py`：手机端快速回填页和打卡成功页渲染。
- `reminders.py`：提醒配置、打卡入口规范化、推送范围和 PDF 开关。
- `scheduler.py`：本地提醒调度循环。
- `settings.py`：运行时设置视图、密钥脱敏、公网地址规范化、设置 payload 解析。
- `update.py`：GitHub Release 检查、版本比较和更新提示数据。
- `weather.py`：天气地区解析、明日天气查询和回退结果。

## 前端结构

前端入口是 `static/index.html`，样式在 `static/styles.css`，功能脚本按域放入 `static/js/`：

```text
static/js/
├── ai/
├── content/
├── core/
├── review/
└── system/
```

- `core/app.js`：全局状态、公共 API、视图切换、共享渲染工具。
- `content/`：上传、题库、题目详情、做题本、模拟卷、教材精读。
- `review/`：错题本、每日练习、章节统计、错题导出、周期反思。
- `ai/`：接口测试、学习教练、老师记忆、外部经验库。
- `system/`：提醒推送、天气、打卡、数据备份、迁移和版本管理。

## 当前边界

- `app.py` 可以继续作为装配层，但不要再把大段业务逻辑写回去。
- 新增后端能力优先放入 `sakura/<domain>/`，Handler 只负责读请求、调用模块、返回响应。
- 前端新增功能应放在 `static/js/<domain>/` 下，不再回到 `static/` 根目录。
- UI 改动要保留现有 DOM `id` 和 `data-view`，因为前端事件绑定依赖这些标识。
- 教材精读、页码、删除页、视觉读取和段落解析是高风险区，改动后必须专项测试。
- 公开部署必须保护 `.env`、数据库、上传文件、日志、导出包和部署密钥。

## 验证命令

重构或移动模块后至少运行：

```powershell
python -m py_compile app.py notify_daily.py
Get-ChildItem -Path sakura -Recurse -Filter *.py | ForEach-Object { python -m py_compile $_.FullName }
Get-ChildItem -Path static\js -Recurse -Filter *.js | ForEach-Object { node --check $_.FullName }
python tests\smoke_refactor.py
git diff --check
```
