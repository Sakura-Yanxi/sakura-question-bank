# Sakura 做题集

Sakura 做题集是一个面向个人学习、错题复盘和 AI 辅助讲解的本地优先型学习工作台。它把 PDF 做题本、模拟卷、教材精读、错题复习、每日练习、周期反思、AI 学习教练和提醒推送放在同一个系统里，目标很简单：做过的题不浪费，薄弱知识点不遗漏。

> 当前项目仍属于个人学习 demo 和原型系统，不是商业题库产品。欢迎学习、交流和非商业二次开发，但请尊重原创并保留署名。

## 当前发布

- 当前版本：`v1.0.0`
- 发布页：[GitHub Releases](https://github.com/Sakura-Yanxi/-/releases)
- 推荐更新方式：已用 Git 下载的用户运行 `update.bat` / `update.sh`；下载 zip 的用户覆盖代码文件并保留自己的 `data/` 和 `.env`。
- 应用内会检查 GitHub 最新 Release；当后续发布 `v1.0.1`、`v1.1.0` 等更高版本时，页面顶部会出现更新提示。

## 项目定位

这个项目围绕三个问题设计：

1. 做过的题能不能沉淀下来。
2. 错过的题能不能按错因、知识点和复习周期重新出现。
3. AI 能不能基于真实做题证据给出具体指导，而不是只生成泛泛建议。

因此 Sakura 做题集采用本地优先思路：PDF 拆页、题图保存、题库筛选、错题状态、统计图表、复习队列和数据迁移都优先在本地完成。只有在需要解析、讲解、变式、反思、教材问答或 AI 教练对话时，才调用大模型 API。

## 功能概览

### 资料与题库

- PDF 做题本导入：支持按页拆分题目，保存题图和可提取文本。
- 页码范围导入：可只导入指定起止页，避免整本重复上传。
- 章节识别：优先读取页面右上角章节文本，并清洗重复章节名、水印、公众号、基础篇等干扰内容。
- 做题本编辑：资料名称、科目、类型等信息可后续修正。
- 模拟卷模块：模拟卷和普通做题本同级管理，拥有独立上传入口和题库视图。
- 题库筛选：按科目、资料、知识点、章节、掌握状态、关键词筛选。
- 题图查看：支持放大、双击查看和题目边界微调。
- 错题导出：可按资料、科目、知识点、章节筛选并导出 PDF。

### 错题与复习

- 状态记录：未做、做对、做错、半会、需复习。
- 元认知错因标签：计算失误、公式遗忘、逻辑死角、题意理解偏差。
- 多刷复盘记录：二刷、三刷或每日练习回填时，每次补充都会按日期独立保存为小卡片，不再覆盖旧备注。
- 间隔复习：做错后进入复习队列，后续做对会逐步拉长复习间隔，参考 1 / 3 / 7 / 14 / 30 天节奏。
- 每日练习：默认从错题、半会题、到期复习题和历史薄弱题中生成，不是盲目从原题库抽题。
- 自定义练习规则：可按科目、资料、知识点、章节设置推送范围和题量。
- 知识溯源：章节正确率偏低时，可在练习中穿插前置基础题。
- 统计画像：包含知识点分布、章节正确率、错因统计和错因雷达图。

### AI 学习教练

AI 学习教练不是单纯聊天框，而是结合学习档案、错题证据、复习队列和老师记忆的 tutor agent 雏形。

- API 可用性测试。
- 错题启发式提示：
  - Level 1：只给核心概念或定理。
  - Level 2：给第一步关键变形或切入点。
  - Level 3：生成完整 LaTeX 解析。
- 举一反三变式：
  - Base：换数不换逻辑。
  - Advanced：改变求解目标。
  - Pro：跨章节综合。
- AI 老师对话：支持围绕学习计划、错题复盘、知识点讲解和节奏调整连续追问。
- 老师记忆：可按学科创建、选择、搜索和查看记忆；导入时支持智能压缩和用户自定义归纳要求。
- 记忆压缩模板：可自定义老师记忆的压缩规则，让 AI 老师更像长期了解你的学习助教。
- 外部经验库：可导入他人备考经验，但系统会区分“外部经验”和“个人真实证据”。
- 历史知识归档：可查看、删除历史档案和 AI 记忆。

### 教材精读

- 教材 PDF 上传：按页保存页面截图并提取段落。
- 页码和段落定位：可围绕指定页码、指定段落向 AI 提问。
- 连续追问：支持对同一教材内容进行多轮解释。
- 记忆压缩：可将高价值解释压缩导入老师记忆。
- 公式渲染：前端集成 MathJax，尽量保证 AI 生成的 LaTeX 公式正常显示。

### 总结与反思

- 周复盘：按科目统计本周做题量、正确量、错误量、薄弱章节和错因。
- 月复盘：拉长周期观察知识点稳定性和复习完成情况。
- AI 反思：可调用大模型指出当前不足、阶段重点和后续规划。
- 历史记录：支持查看和删除历史反思记录。

### 提醒与推送

- 企业微信机器人推送。
- PushPlus 推送。
- SMTP 邮箱推送，可作为备用通道。
- 早晚提醒时间可自定义。
- 天气推送地区和时间可自定义。
- 打卡入口可选择企业微信、PushPlus 或本地按钮。
- 企业微信模式只走企业微信机器人，不会误调 PushPlus。
- 推送测试按钮用于检查当前配置是否可用。
- 访问安全：可在推送配置区设置管理员访问密码，并启用登录失败限速、安全事件记录和异常推送告警。
- 登录锁定：1 分钟内 5 次密码错误会触发分级锁定，锁定级别依次为 5 分钟、10 分钟、1 小时、1 年。

### 数据迁移

- 支持本地数据导出。
- 支持从备份恢复。
- 迁移范围包括题库记录、错题状态、标注信息、多刷复盘记录、学习档案、老师记忆、资料元数据和必要的本地文件索引。
- `.env`、API Key、服务器密钥、日志和临时压缩包不应进入 Git 仓库。

## 技术栈

- 后端：Python 标准库 `http.server`
- 数据库：SQLite
- PDF 处理：PyMuPDF
- 图像处理：Pillow
- 前端：原生 HTML / CSS / JavaScript
- 数学公式：MathJax
- 图标：Lucide
- AI 调用：OpenAI SDK，支持 DeepSeek 和 OpenAI Compatible API
- 推送：企业微信机器人、PushPlus、SMTP 邮箱
- 安全：登录密码复杂度校验、失败限速、分级锁定和安全告警

## 目录结构

```text
.
├── app.py                         # 后端入口与 HTTP Handler
├── notify_daily.py                # 定时提醒命令入口
├── requirements.txt               # Python 依赖
├── .env.example                   # 环境变量示例
├── sakura/                        # 后端功能包
│   ├── core/                      # 基础设施：配置、数据库、HTTP、路由、登录、安全、解析
│   ├── content/                   # 内容域：PDF、导入、题库、资料、教材、筛选、模型
│   ├── review/                    # 复习域：每日练习、错题导出、提示、洞察、反思、记忆曲线
│   ├── ai/                        # AI 域：LLM 客户端、学习教练、学习档案、老师记忆
│   └── system/                    # 系统域：备份迁移、推送、邮箱、天气、提醒配置
├── static/
│   ├── index.html                 # 前端页面结构
│   ├── styles.css                 # 前端样式
│   └── js/
│       ├── core/                  # 前端基础状态、导航、公共 API
│       ├── content/               # 做题本、模拟卷、教材、题库、上传、题目详情
│       ├── review/                # 错题、每日练习、复盘、统计、导出
│       ├── ai/                    # AI 对话、学习档案、老师记忆、经验库
│       └── system/                # 提醒推送、天气、打卡、数据迁移
├── tests/
│   └── smoke_refactor.py          # 关键重构烟测
├── docs/
│   ├── architecture.md
│   └── 本地到云端部署保姆级教程.md
├── deploy/
│   ├── azure-vm.md
│   ├── local-to-cloud.md
│   └── novm-mini.md
└── data/                          # 本地数据目录，默认不提交
```

后端不再把一堆 `sakura_*.py` 平铺在根目录，而是按功能放入 `sakura/` 包中：

- `sakura/core`：配置、数据库、路由、HTTP 响应、登录保护、安全限速、请求解析。
- `sakura/content`：PDF 渲染、导入切片、章节识别、资料管理、题库查询、教材精读。
- `sakura/review`：错题洞察、启发式提示、每日练习、错题导出、周期反思、复习间隔。
- `sakura/ai`：大模型调用、学习教练、学习档案、老师记忆、外部经验库。
- `sakura/system`：通知推送、天气、提醒定时、邮箱、备份、迁移、运行时配置。

## 快速开始

### 1. 安装依赖

```powershell
pip install -r requirements.txt
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env`：

```powershell
copy .env.example .env
```

最低限度可以不配置 AI Key。此时系统仍能进行 PDF 导入、题库管理、错题标注、统计和本地复习，但 AI 解析、AI 教练、教材问答和反思总结会降级或不可用。

### 3. 启动服务

```powershell
python app.py
```

### 4. 打开浏览器

```text
http://127.0.0.1:8000
```

## 常用环境变量

```env
PORT=8000
APP_PUBLIC_URL=http://127.0.0.1:8000

SAKURA_ADMIN_PASSWORD=Change-this-Strong#2026
SAKURA_AUTH_SECRET=replace-with-a-long-random-string
SAKURA_DEMO_MODE=0
SAKURA_UPDATE_REPO=Sakura-Yanxi/-

LLM_API_KEY=
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat

WEWORK_BOT_WEBHOOK=
PUSHPLUS_TOKEN=

EMAIL_ENABLED=0
EMAIL_HOST=smtp.qq.com
EMAIL_PORT=465
EMAIL_USE_SSL=1
EMAIL_USE_STARTTLS=0
EMAIL_USER=
EMAIL_PASSWORD=
EMAIL_TO=
EMAIL_FROM=
EMAIL_FROM_NAME=Sakura ???

SAKURA_INTERNAL_SCHEDULER=1
SAKURA_SCHEDULER_POLL_SECONDS=30
REMIND_MORNING_ON=0
REMIND_MORNING_TIME=10:00
REMIND_NIGHT_ON=0
REMIND_NIGHT_TIME=20:00
REMIND_WEATHER_ON=0
REMIND_WEATHER_TIME=22:30
REMIND_CHECKIN_MODE=wework
REMIND_DAILY_SCOPE=due
REMIND_DAILY_LIMIT=20
REMIND_SEND_PDF=1
WEATHER_CITY=??
```

说明：

- `SAKURA_ADMIN_PASSWORD`：公网部署时建议开启，用于登录保护。建议至少 12 位，并包含字母、数字和特殊字符。
- `SAKURA_AUTH_SECRET`：登录签名密钥，应使用足够长的随机字符串。
- `SAKURA_DEMO_MODE=1`：演示模式，写入类接口会被限制，适合给朋友体验。
- `LLM_API_KEY`：大模型 API Key。
- `LLM_BASE_URL`：OpenAI Compatible API 地址，例如 DeepSeek 或中转站地址。
- `LLM_MODEL`：模型名。
- `APP_PUBLIC_URL`：公网访问地址，用于生成手机端回填链接和推送链接。
- `WEWORK_BOT_WEBHOOK`：企业微信群机器人 Webhook。
- `PUSHPLUS_TOKEN`：PushPlus Token。
- `EMAIL_PASSWORD`????????????????
- `SAKURA_INTERNAL_SCHEDULER`??????????????? `1`??????????????????? crontab ???????
- `SAKURA_SCHEDULER_POLL_SECONDS`????????????? `30`???? `10` ???
- `REMIND_CHECKIN_MODE`??? `wework`?`pushplus`?`email`?`local`?
- `REMIND_DAILY_SCOPE`???????????? `due`?`active_wrong`?`all_wrong_history`?
- `REMIND_DAILY_LIMIT`?????????????? `20`?
- `REMIND_SEND_PDF`??????????????? PDF?`1` ????`0` ????

```text
LLM_API_KEY > MIMO_API_KEY > DEEPSEEK_API_KEY
```

## 推送配置说明

### 登录安全与告警

公网部署时建议一定设置访问密码。Sakura 当前的登录安全策略如下：

- 密码复杂度：至少 12 位，必须包含字母、数字、特殊字符，不能包含空格或换行。
- 分级限速：同一来源 IP 在 1 分钟内连续 5 次密码错误会触发锁定。
- 锁定级别：第一次 5 分钟，第二次 10 分钟，第三次 1 小时，之后可锁定 1 年。
- 安全事件：系统会记录登录失败、锁定、锁定拦截、登录成功和密码更新事件。
- 异常告警：首次触发锁定时，会按当前推送优先级发送安全提醒。
- IP 追踪边界：系统只能记录来源 IP、浏览器标识和请求头；如果前面有 Cloudflare、Nginx 或云厂商网关，会优先读取 `CF-Connecting-IP`、`X-Real-IP`、`X-Forwarded-For`。精确定位到个人身份需要结合云厂商、Cloudflare 或反向代理日志，项目本身不会做越界追踪。

也可以在页面“推送通道配置 -> 访问安全”里直接设置新密码。保存后会自动轮换登录签名密钥，旧登录态会失效，需要重新登录。

### 企业微信机器人

适合当前主要推送入口。配置步骤：

1. 在企业微信群里添加群机器人。
2. 复制机器人 Webhook。
3. 在页面“推送通道配置”里填写“企业微信机器人 Webhook”。
4. 保存配置。
5. 在“提醒与打卡设置”里选择“企业微信打卡”。
6. 点击测试推送。

### PushPlus

PushPlus 可作为备用微信推送通道。如果返回 `code: 905`，通常表示 PushPlus 账号没有完成实名认证，不是程序配置丢失。

### QQ 邮箱 SMTP

QQ 邮箱需要使用授权码：

1. 打开 QQ 邮箱网页版。
2. 进入“设置”。
3. 打开“账号”或“账户安全”相关设置。
4. 开启 SMTP 服务。
5. 生成授权码。
6. 在 Sakura 中填写 SMTP Host、SMTP Port、发件邮箱、SMTP 授权码和收件人。
7. 保存后点击“测试邮箱”。

常用配置：

```text
SMTP Host: smtp.qq.com
SMTP Port: 465
加密方式: SSL 465
发件邮箱: 你的 QQ 邮箱
SMTP 授权码: QQ 邮箱生成的授权码
收件人: 可以填一个或多个邮箱，多个用逗号分隔
```

## Token 与费用说明

不会消耗大模型 token 的操作：

- PDF 上传和拆页。
- 本地题图保存。
- 基础文本提取。
- 题库筛选。
- 错题状态记录。
- 知识点和章节统计。
- 本地复习队列计算。
- 数据导入导出。
- 天气查询本身。

会消耗大模型 token 的操作：

- AI 错题分析。
- Full Solution 完整解析。
- 举一反三变式生成。
- AI 学习教练对话。
- 教材精读问答。
- 周期反思复盘。
- 学习档案深度总结。
- 老师记忆压缩。

设计原则是：能用本地规则解决的事情尽量本地完成，真正需要语言理解、讲解和规划时才调用模型。

## 本地测试

```powershell
python -m py_compile app.py notify_daily.py
Get-ChildItem -Path sakura -Recurse -Filter *.py | ForEach-Object { python -m py_compile $_.FullName }
Get-ChildItem -Path static\js -Recurse -Filter *.js | ForEach-Object { node --check $_.FullName }
python tests\smoke_refactor.py
```

如果只改 README 或文档，不一定需要跑完整测试；如果移动模块、改 API、改前端 JS，建议至少跑上面的烟测。

## 更新与发版

Sakura 是本地优先、自托管的工具：每个人把它部署在自己的机器上。代码更新走 Git，数据始终留在本地。

### 使用者：如何更新到新版本

代码（`.py` / `.js` / `.html`）由 Git 管理；你的题库、数据库、题图（`data/`）和密钥配置（`.env`）都在 `.gitignore` 里，**更新代码不会动它们**。

- 用 Git（推荐）：在项目目录执行 `git pull`，依赖有变动时再 `pip install -r requirements.txt`，然后重启服务。
- 一键脚本：Windows 双击 `update.bat`，Linux/macOS 运行 `bash update.sh`——它会自动 `git pull` + 更新依赖，完成后提示你重启。
- 不用 Git：去仓库下载最新 zip，解压后**覆盖代码文件**即可，覆盖时**不要动 `data/` 和 `.env`**。

更新后重启服务（`python app.py`），启动时会自动运行幂等的数据库迁移，给你已有的库补上新字段，不会丢数据。

页面顶部会在检测到新版本时弹出「有新版本，建议更新」横幅（见下「版本提示」）。

### 维护者：如何发布一个新版本

1. 改完代码后，把 `sakura/__init__.py` 里的 `__version__` 往上加一档（如 `1.0.0` → `1.0.1`）。
2. `git commit` 并 `git push`。
3. 在 GitHub 上 **Create a new release**，tag 填成对应版本（如 `v1.0.1`，`v` 前缀可有可无）。
4. 各部署在下次检查（缓存过期后）就会看到更新提示。

更详细的发布/更新流程见 [docs/release-update.md](docs/release-update.md)。

发版纪律（务必遵守，否则会坑到 `git pull` 的老用户）：

- `__version__` 必须和 release tag 对应着**单调递增**（版本号按数字段比较：`1.0.1 < 1.1.0`）。
- 数据库迁移**只用幂等的 `ADD COLUMN` + 启动时迁移**，绝不写删列、改类型、清数据这类破坏性迁移，保证老用户更新后数据不炸。

### 版本提示（in-app 更新通知）

程序会调用 GitHub Releases API 比对最新 tag，有新版时在页面顶部提示并给出下载链接。它**只提示、不自动改代码**。

- 默认检查仓库是 `Sakura-Yanxi/-`。如果你 fork 或迁移仓库，在 `.env` 设 `SAKURA_UPDATE_REPO=你的GitHub用户名/仓库名`（如 `Sakura-Yanxi/sakura-tiku`）。
- 如果仓库还没有发布 Release、网络失败、限流或私有库无权限，检查会静默降级，不影响使用。
- 检查带超时、结果缓存约 6 小时，断网/限流/私有库等任何失败都会静默跳过，不影响使用。
- 用户点「关闭」后，同一版本不再重复提示。

## 部署说明

项目可以本地运行，也可以部署到轻量服务器、Azure 学生服务器或临时演示服务器。

已有部署文档：

- [本地到云端部署保姆级教程](docs/本地到云端部署保姆级教程.md)
- [local-to-cloud](deploy/local-to-cloud.md)
- [azure-vm](deploy/azure-vm.md)
- [novm-mini](deploy/novm-mini.md)

公网部署建议：

1. 配置 `SAKURA_ADMIN_PASSWORD` 和 `SAKURA_AUTH_SECRET`。
2. 不要把 `.env`、数据库、上传 PDF、日志、导出压缩包提交到 GitHub。
3. 演示环境建议开启 `SAKURA_DEMO_MODE=1`。
4. 使用域名时，把 DNS 指向服务器公网 IP，并确认服务商防火墙开放 80 / 443。
5. 如果部署在中国大陆服务器，域名访问通常需要考虑备案要求。

## 数据与安全

本项目默认不提交以下内容：

- `.env`
- `data/`
- SQLite 数据库
- 上传的 PDF
- 拆分后的题图
- 日志文件
- 导出的 zip 或 PDF
- 部署密钥

请不要把自己的 API Key、企业微信 Webhook、PushPlus Token、服务器密码等敏感信息写入 README、代码或公开 issue。

登录安全相关数据保存在本地 SQLite 中：

- `login_rate_limits`：记录来源 IP 的失败次数、锁定级别和锁定到期时间。
- `login_security_events`：记录登录失败、锁定、锁定拦截、登录成功和密码更新事件。
- 这些记录用于你自己排查异常访问，不应公开展示或提交到 GitHub。

错题多刷记录保存在 `question_review_notes` 中，会随题库备份迁移，用于保留每次复盘的日期、状态、错因标签和补充说明。

用户自行上传的 PDF、教材、题库等资料由使用者自行负责版权合规。本项目不提供任何盗版教材、盗版题库或商业资料。

## 开源与使用条款

### 允许

- 个人学习使用。
- 非商业二次开发。
- 在自己的学习项目中修改、扩展和部署。
- 提交 issue、建议或 pull request。
- 在保留原作者信息的前提下进行教学、研究或个人展示。

### 不允许

- 未经授权用于商业销售、商业 SaaS、付费题库或培训机构产品。
- 删除原作者信息后重新发布。
- 将本项目包装成完全原创项目进行宣传。
- 将界面、结构、文档或核心逻辑直接复制到闭源商业项目。
- 上传、传播或打包他人享有版权的 PDF、教材、题库等资料。

### 署名建议

如果你基于本项目进行二次开发或公开展示，请在 README、页面底部或项目说明中标明：

```text
Based on Sakura 做题集 by Sakura-Yanxi.
Original repository: https://github.com/Sakura-Yanxi/-
```

中文可写为：

```text
本项目基于 Sakura-Yanxi 的 Sakura 做题集二次开发。
原项目地址：https://github.com/Sakura-Yanxi/-
```

## 当前状态

当前版本已经形成较完整的个人学习闭环：

```text
PDF / 教材导入
  -> 题目拆分与章节识别
  -> 做题状态记录
  -> 错因标注
  -> 多刷复盘记录
  -> 间隔复习
  -> 每日练习
  -> AI 解析与变式
  -> 周期复盘
  -> 学习档案更新
  -> AI 老师策略调整
```

仍可继续增强的方向：

- 更稳定的模拟卷自动分题。
- 更接近 FSRS 的复习调度算法。
- 多用户账号体系。
- 云端同步和权限隔离。
- 更完整的移动端错题回填体验。
- 更规范的开源许可证文件。
- 更强的 AI 老师评估与自我校准机制。
- 更细的安全审计面板，例如按 IP 汇总、手动解锁和导出安全日志。

## 致谢

Sakura 做题集来自真实学习场景中的连续迭代：PDF 做题本、错题复盘、每日练习、间隔复习、AI tutor、教材精读和云端部署都围绕“题目不浪费，知识点不遗漏”这个目标展开。

欢迎学习、改造和提出建议。请尊重原创，保留署名，不要商用套壳。
