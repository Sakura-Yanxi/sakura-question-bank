# Sakura 做题集

> 一个本地优先的个人学习工作台：管理 PDF 题本、模拟卷、教材精读、错题复习、每日练习、阶段复盘和学习教练。

## 项目入口

- GitHub 仓库：https://github.com/Sakura-Yanxi/sakura-question-bank
- 当前版本：`v1.0.0`
- 发布页：https://github.com/Sakura-Yanxi/sakura-question-bank/releases
- 宣传海报：`docs/poster/sakura-demo-poster.png`
- 保姆级部署教程：`docs/本地到云端部署保姆级教程.md`

Sakura 的目标很直接：做过的题不浪费，错过的知识点不丢，复习节奏有记录，每一轮学习都能留下可回看的证据。

它不是一个只保存截图的题库，也不是一个只聊天的工具。它把“题目、错因、复习、教材、记忆、计划”放在同一个本地工作台里，让学习过程能沉淀下来。

## 适合谁

- 想把 PDF 题本、模拟卷、教材页面统一管理的人。
- 想长期维护错题本、复习记录和阶段复盘的人。
- 想让讲解、教材阅读和每日练习围绕自己的真实错题展开的人。
- 想本地保存数据，不希望题库和密钥默认上传到云端的人。
- 想做个人 demo、课程作业、学习作品集或非商业二次开发的人。

## 当前代码状态

后端入口是 `app.py`，当前约 `2670` 行。它主要负责启动服务、路由入口和历史 Handler 装配。

主要逻辑已经拆到 `sakura/`：

```text
sakura/
├── ai/        学习教练、学习档案、老师记忆、模型调用
├── api/       文档和教材运行时流程
├── content/   PDF、题库、教材、导入、OCR、筛选
├── core/      配置、数据库、路由、安全、HTTP 工具
├── review/    错题、每日练习、复盘、提示、导出
└── system/    备份、迁移、推送、提醒、天气、更新检查
```

前端在 `static/`：

```text
static/
├── index.html
├── styles.css
├── assets/
└── js/
    ├── ai/
    ├── content/
    ├── core/
    ├── review/
    └── system/
```

## 主要功能

### 1. 资料导入

- 导入 PDF 做题本，按页保存题图和可提取文本。
- 支持只导入指定页码范围。
- 普通题本、模拟卷和教材精读分开管理。
- 教材导入时，如果文件名明显像试卷，例如“模拟卷”“真题卷”“试卷”，会提示放到对应模块。

### 2. 题库管理

- 按科目、资料、章节、知识点、状态和关键词筛选。
- 题图可放大查看，也可以重新裁切题目边界。
- 支持修改资料名称、科目和类型。
- 支持删除资料、删除题目、更新章节和重新扫描章节。
- 支持按条件导出错题 PDF。

### 3. 错题复习

- 状态包括未做、做对、做错、半会、需复习。
- 可标记计算失误、公式遗忘、逻辑死角、题意理解偏差等错因。
- 多次复盘不会覆盖旧备注，每次练习都保留记录。
- 复习间隔参考 1 / 3 / 7 / 14 / 30 天节奏。
- 错题洞察会进入学习档案，用来生成后续复习建议。

### 4. 每日练习

- 默认从错题、半会题、到期复习题和薄弱章节里生成。
- 可按科目、资料、章节和题量自定义范围。
- 练习结果会回写到题库和复习记录。
- 推送每日练习时可附带 PDF，手机端可以快速回填状态。

### 5. 教材精读

- 教材 PDF 会保存为教材库，不和题本、模拟卷混在一起。
- 每页都会生成截图，并尽量提取可复制文本。
- 选中段落提问时，优先把当前页文字、选中段落和历史追问交给文字讲解接口。
- 如果页面是扫描件、拍照页或没有文本层，可以手动使用视觉读取，让支持图片输入的模型读取整页截图。
- 教材精读对话可以压缩成老师记忆，记录教材、页码、困惑点、关键理解和后续复习建议。

### 6. 学习教练

学习教练会读取本地学习证据，再给出建议。它会用到：

- 最新学习档案。
- 近期错题和错因。
- 待复习题和逾期题。
- 薄弱知识点和前置基础缺口。
- 老师记忆和外部经验库。
- 考试日期、每日可用时间和当前重点科目。

它能做：

- 解释当前最该补的知识点。
- 生成今日行动建议。
- 根据复习队列安排先后顺序。
- 根据错因给出训练策略。
- 把高价值对话压缩成长期老师记忆。
- 在新错题、新复习状态、新教材记忆进入系统后，刷新学习档案和计划。

这里的“自主迭代”指的是：系统会用新增学习证据更新档案和计划，不是自动替用户上传资料、自动修改题库或自动调用外部接口。

```text
做题 / 复习 / 教材精读
  -> 记录状态、错因、备注和教材记忆
  -> 汇总知识点掌握度、反复误区和前置短板
  -> 生成新的学习档案版本
  -> 排序当前最该处理的薄弱点
  -> 生成今日任务和阶段计划
  -> 下一轮做题后继续更新
```

## 保姆级本地配置教程

### 第一步：安装 Python

建议安装 Python 3.11 或 3.12。

Windows 用户安装时记得勾选：

```text
Add Python to PATH
```

安装后打开终端检查：

```bash
python --version
```

能看到版本号就可以继续。

### 第二步：下载项目

会用 Git 的用户：

```bash
git clone https://github.com/Sakura-Yanxi/sakura-question-bank.git
cd sakura-question-bank
```

不会用 Git 的用户：

1. 打开 GitHub Releases：https://github.com/Sakura-Yanxi/sakura-question-bank/releases
2. 找到最新版本，例如 `v1.0.0`、`v1.0.1`。
3. 下载该版本里的压缩包。如果没有单独上传安装包，就下载 `Source code (zip)`。
4. 解压到一个固定目录。
5. 进入解压后的项目文件夹。

`Code -> Download ZIP` 下载的是当前 `main` 分支快照，适合临时查看最新代码，但不等于稳定发布版，也不能自动同步更新。不会用 Git 的用户想升级时，需要重新到 Releases 下载最新版压缩包，再覆盖代码文件；覆盖时保留自己的 `data/` 和 `.env`。

### 第三步：创建虚拟环境

Windows：

```powershell
python -m venv .venv
.\.venv\Scripts\activate
```

Linux / macOS：

```bash
python3 -m venv .venv
source .venv/bin/activate
```

看到命令行前面出现 `(.venv)`，说明虚拟环境已经启用。

### 第四步：安装依赖

```bash
pip install -r requirements.txt
```

如果下载慢，可以换镜像源：

```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 第五步：创建配置文件

复制示例配置：

Windows PowerShell：

```powershell
Copy-Item .env.example .env
```

Linux / macOS：

```bash
cp .env.example .env
```

`.env` 是本地配置文件，用来保存访问密码、讲解接口、推送 Token 等内容。不要把它上传到公开仓库。

### 第六步：最小可运行配置

本地自己用，可以先不填模型和推送。建议至少保留：

```env
PORT=8000
APP_PUBLIC_URL=http://127.0.0.1:8000
SAKURA_DEMO_MODE=0
```

如果以后要公网访问，请设置：

```env
SAKURA_ADMIN_PASSWORD=换成强密码
SAKURA_AUTH_SECRET=换成一长串随机字符
```

### 第七步：启动

```bash
python app.py
```

浏览器打开：

```text
http://127.0.0.1:8000
```

Windows 用户也可以双击：

```text
run_server.bat
```

## 文字讲解接口配置

文字讲解接口用于知识解释、题目解析、变式练习、错因分析、阶段复盘、教材文字页问答和学习教练。

以 DeepSeek 为例：

```env
LLM_API_KEY=你的 DeepSeek Key
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
```

也可以换成 MiMo 或其他兼容 OpenAI 调用格式的平台：

```env
LLM_API_KEY=对应平台给你的 Key
LLM_BASE_URL=对应平台兼容 OpenAI 调用格式的地址
LLM_MODEL=对应平台支持的文字模型名
```

填好后重启服务，再到页面里的 AI 设置或接口测试区试一下。

## 视觉读取接口配置

视觉读取接口用于读取图片内容，例如扫描版教材页、没有文本层的 PDF 页面、教材截图里的公式和图表。

视觉模型必须支持图片输入。文字讲解和视觉读取可以使用不同供应商。

```env
LLM_VISION_MODEL=支持图片输入的模型名
LLM_VISION_API_KEY=可选，留空则沿用 LLM_API_KEY
LLM_VISION_BASE_URL=可选，留空则沿用 LLM_BASE_URL
```

三种常见情况：

1. 只做文字讲解：只填 `LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL`。
2. 文字和视觉用同一家：额外填 `LLM_VISION_MODEL`，视觉 Key 和视觉地址可以留空。
3. 文字和视觉用不同家：文字部分填 DeepSeek 等；视觉部分单独填 `LLM_VISION_MODEL`、`LLM_VISION_API_KEY`、`LLM_VISION_BASE_URL`。

注意：

- DeepSeek 这类文字模型不能直接看懂教材截图。
- 视觉读取只在主动触发时使用，不会后台自动消耗额度。
- 如果返回 `402 insufficient_balance`，通常是服务账号余额不足、套餐不可用或模型权限没开通。

## 推送提醒配置

### 企业微信机器人

```env
WEWORK_BOT_WEBHOOK=你的企业微信机器人 Webhook
REMIND_CHECKIN_MODE=wework
```

### PushPlus

```env
PUSHPLUS_TOKEN=你的 PushPlus Token
REMIND_CHECKIN_MODE=pushplus
```

### 邮箱 SMTP

```env
EMAIL_ENABLED=1
EMAIL_HOST=smtp.qq.com
EMAIL_PORT=465
EMAIL_USE_SSL=1
EMAIL_USE_STARTTLS=0
EMAIL_USER=你的邮箱
EMAIL_PASSWORD=邮箱授权码
EMAIL_TO=接收邮箱
EMAIL_FROM=发件邮箱
EMAIL_FROM_NAME=Sakura Study
REMIND_CHECKIN_MODE=email
```

提醒时间示例：

```env
SAKURA_INTERNAL_SCHEDULER=1
REMIND_MORNING_ON=1
REMIND_MORNING_TIME=10:00
REMIND_NIGHT_ON=1
REMIND_NIGHT_TIME=20:00
REMIND_WEATHER_ON=1
REMIND_WEATHER_TIME=22:30
REMIND_DAILY_SCOPE=due
REMIND_DAILY_LIMIT=20
REMIND_SEND_PDF=1
WEATHER_CITY=Beijing
```

## 版本更新

已用 Git 下载的用户：

```bash
git pull
pip install -r requirements.txt
python app.py
```

也可以直接运行：

Windows：

```text
update.bat
```

Linux / macOS / 服务器：

```bash
bash update.sh
```

这些脚本只会拉取代码和更新依赖，不会删除 `data/`、`.env`、数据库、题图、教材文件和用户上传文件。

不用 Git 的用户可以在 Release 页面下载最新 zip，覆盖代码文件。覆盖时保留自己的 `data/` 和 `.env`。

## 备份和迁移

建议定期备份：

- 数据库。
- 题图。
- 教材页截图。
- 上传 PDF。
- `.env` 配置。

页面里有备份导出和备份导入功能。迁移到新电脑时，推荐：

1. 旧电脑导出备份。
2. 新电脑安装 Sakura。
3. 新电脑导入备份。
4. 检查题库、教材、图片和记录是否正常。

## 常见问题

### 页面打不开

检查终端里是否显示：

```text
Sakura demo running at http://127.0.0.1:8000
```

如果端口被占用，可以在 `.env` 改：

```env
PORT=8001
```

### 导入 PDF 没反应

先确认：

- 文件是不是 PDF。
- PDF 是否太大。
- 依赖是否安装完整。
- 终端有没有报错。

### 视觉读取失败

常见原因：

- 没填 `LLM_VISION_MODEL`。
- 视觉模型不支持图片输入。
- Key 或 Base URL 填错。
- 服务账号余额不足，返回 `402 insufficient_balance`。
- 供应商没有给当前模型开通权限。

### 更新失败

常见原因：

- 网络连接 GitHub 失败。
- 本地代码被手动改过，`git pull --ff-only` 无法快进。
- 当前目录不是 Git 仓库。

数据一般不会丢，因为更新脚本不碰 `data/` 和 `.env`。

## 使用边界

可以：

- 个人非商业使用。
- 学习代码结构和本地部署方式。
- 在保留原作者署名和项目来源的前提下进行非商业二次开发。
- 在课程作业、个人作品集或学习记录中展示，并说明来源。

请不要：

- 删除原作者信息后重新发布。
- 将项目包装成完全原创项目宣传。
- 将项目、界面或核心功能直接用于商业售卖、付费课程、培训机构产品或闭源商业服务。
- 将界面、结构、文档或核心逻辑直接复制到闭源商业项目。
- 上传、传播或打包没有授权的 PDF、教材、题库、试卷、图片等资料。

署名建议：

```text
Based on Sakura 做题集 by Sakura-Yanxi.
Original repository: https://github.com/Sakura-Yanxi/sakura-question-bank
```

## 禁止商用与免责声明

本项目公开展示不等于放弃著作权，也不等于授权商业使用。除非获得 Sakura-Yanxi 的明确书面许可，否则禁止商业使用。

免责声明：

- 本项目按现状提供，主要用于个人学习、技术交流和非商业 demo 展示。
- 使用者需要自行负责本地数据、服务器安全、访问密码、API Key、推送 Token、日志和备份文件的保管。
- 使用外部讲解接口、视觉接口、天气接口或推送接口产生的费用、余额不足、限流、封禁、服务中断等问题，由对应服务账号持有人自行承担。
- 智能讲解、计划、反思和教材解读可能存在错误，只能作为学习辅助，不能替代教材、教师、标准答案或专业判断。
- 请勿上传、传播或打包没有授权的 PDF、教材、题库、试卷、图片等资料。
