# Sakura 做题集

> 一个本地优先的个人学习工作台：管理 PDF 题本、模拟卷、教材精读、错题复习、每日练习、阶段复盘和学习教练。

## 项目入口

- GitHub 仓库：https://github.com/Sakura-Yanxi/sakura-question-bank
- 当前版本：`v1.0.10`
- 发布页：https://github.com/Sakura-Yanxi/sakura-question-bank/releases
- 宣传海报：`docs/poster/sakura-demo-poster.png`
- 保姆级部署教程：`docs/本地到云端部署保姆级教程.md`

Sakura 的目标很直接：做过的题不浪费，错过的知识点不丢，复习节奏有记录，每一轮学习都能留下可回看的证据。

它不是一个只保存截图的题库，也不是一个只聊天的工具。它把“题目、错因、复习、教材、记忆、计划”放在同一个本地工作台里，让学习过程能沉淀下来。

`v1.0.10` 重点更新：

- 每日练习支持更清楚的“当前每日练习队列”，自定义规则会按顺序合并，并受每日总上限控制，避免一次推送过多题。
- 今日已推送错题会单独显示为批次记录，和实时练习队列区分开，减少“是不是推了两份”的误解。
- 错题导出修复同一本练习册多章节选择、iPad 下载 PDF 跳转等问题，导出封面和下载行为更稳定。
- 完整解析优先使用本地 OCR 识别题干；本地识别不到时才提示是否调用视觉 API，避免无意义消耗额度。
- 题目详情里的 AI 解析和变式练习支持展开阅读，长解析不会把页面挤乱。

## 适合谁

- 想把 PDF 题本、模拟卷、教材页面统一管理的人。
- 想长期维护错题本、复习记录和阶段复盘的人。
- 想让讲解、教材阅读和每日练习围绕自己的真实错题展开的人。
- 想本地保存数据，不希望题库和密钥默认上传到云端的人。
- 想做个人 demo、课程作业、学习作品集或非商业二次开发的人。

## 当前代码状态

后端入口是 `app.py`，当前约 `2438` 行。它主要负责启动服务、路由入口和历史 Handler 装配。

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

`Code -> Download ZIP` 下载的是当前 `main` 分支快照，适合临时查看最新代码，但不等于稳定发布版。正式使用建议从 Releases 下载；后续页面内“版本管理”会优先提供一键更新，无法一键更新时再到 Releases 下载最新版压缩包覆盖代码文件。覆盖时保留自己的 `data/`、`.env` 和 `.venv`。

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

可选维护配置：

```env
SAKURA_UPDATE_BACKUP_KEEP=3
SAKURA_MIGRATION_BACKUP_KEEP=3
SAKURA_MAX_UPLOAD_MB=1024
```

含义分别是：保留最近几份更新代码备份、保留最近几份迁移前数据备份、限制单次浏览器上传的最大体积。大教材或大迁移包超过 1024 MB 时，可以把 `SAKURA_MAX_UPLOAD_MB` 调大后重启服务。

### 第七步：启动

Windows 推荐直接双击：

```text
run_server.bat
```

它会自动创建 `.venv`、安装依赖并打开浏览器。

手动命令行启动：

```bash
python app.py
```

如果看到 `No module named 'fitz'`，说明依赖还没安装；请先运行 `run_server.bat`，或执行 `python -m pip install -r requirements.txt`。

浏览器打开：

```text
http://127.0.0.1:8000
```

## 云端 / 服务器部署保姆级教程

如果你还没有服务器，可以先参考下面这个视频，了解怎样从零开始申请一台阿里云服务器，并部署一个简单网站：

【从0到1：学生党如何免费拿阿里云服务器，并部署第一个网站-哔哩哔哩】
https://b23.tv/Z8bBgG3

云厂商的活动、免费额度和学生认证规则经常会变，具体以阿里云页面显示为准。配置过程中注意保护自己的密码、API Key、Webhook、真实学习资料、题库和教材截图，不要随手公开到截图、仓库或演示页面里。

## 项目一：Sakura 做题集从本地部署到云端服务器


这份教程写给第一次接触 Python 项目部署的同学。你不需要提前懂后端、Linux、Nginx 或 systemd，只要按步骤做，就可以把本地能运行的 Sakura 做题集部署到一台 Ubuntu 云服务器上，让电脑和手机都能通过公网访问。

如果你是第一次部署，建议先完整读完“0. 先理解项目由什么组成”和“17. 安全建议”，再开始复制命令。部署不是只把网页跑起来，还包括密码、数据、API Key、备份和版权边界。

本教程默认你使用：

- 本地电脑：Windows
- 服务器系统：Ubuntu 22.04 / 24.04
- 项目目录：`/opt/sakura-study`
- Python 版本：3.11 或 3.12
- Sakura 服务端口：`8000`
- 对外访问方式：Nginx 反向代理到 Python 服务

如果你只是给朋友看一个小样例，可以不迁移真实数据，只部署程序和少量演示文件。如果你要把自己的真实学习数据搬到云端，请认真看“数据迁移与安全”部分。

### 开始前先确认

#### 适合这份教程的人

- 你能打开 Windows PowerShell，但不熟悉命令行。
- 你已经有 Sakura 做题集项目代码，想先本地跑起来。
- 你希望把它部署到一台 Ubuntu 云服务器上，用浏览器或手机访问。
- 你愿意按步骤检查密码、密钥、备份和公网安全。

#### 你需要准备什么

```text
本地电脑：Windows 10 / 11
本地工具：Python、Git、PowerShell、浏览器
云服务器：Ubuntu 22.04 / 24.04
可选账号：GitHub、域名服务商、DeepSeek 或其他讲解接口、企业微信 / PushPlus / 邮箱
```

如果暂时没有域名，也可以先用服务器公网 IP 访问；如果暂时没有 AI Key，也可以先使用题库、错题、每日练习、导入和导出功能。

#### 新手最容易踩的坑

- 不要把 `.env` 上传到 GitHub。
- 不要把 `data/` 上传到 GitHub。
- 不要在截图里露出 API Key、Webhook、邮箱授权码、服务器 IP 和登录密码。
- 不要一上来导入很大的 PDF，先用 3 到 5 页的小文件测试。
- 不要在公网裸奔，服务器上一定设置 `SAKURA_ADMIN_PASSWORD` 和 `SAKURA_AUTH_SECRET`。
- 不要把没有授权的教材、试卷、题库打包到公开仓库或演示站点。

#### 禁止商用提醒

Sakura 做题集当前仅允许个人学习、技术交流和非商业二次开发。公开仓库不代表允许商用；未经 Sakura-Yanxi 明确书面许可，禁止用于商业售卖、付费课程、培训机构产品、SaaS 服务、代部署收费、闭源商业项目或商业宣传物料。

### 0. 先理解项目由什么组成

Sakura 做题集分为三类东西：

```text
代码：app.py、sakura/、static/、requirements.txt、notify_daily.py
数据：data/ 里的 SQLite 数据库、上传 PDF、题图、教材页图
密钥：.env 里的 API Key、登录密码、企业微信 Webhook、PushPlus Token、邮箱授权码
```

部署时请记住一条原则：

```text
代码可以提交 GitHub。
数据用备份包迁移。
密钥只写到服务器 .env，不要提交到 GitHub。
```

当前推荐的代码结构是：

```text
Sakura 项目
├── app.py
├── notify_daily.py
├── requirements.txt
├── .env.example
├── sakura/
│   ├── core/       # 配置、数据库、HTTP、路由、登录
│   ├── content/    # PDF、题库、资料、教材、导入
│   ├── review/     # 错题、每日练习、复盘、提示、记忆曲线
│   ├── ai/         # AI 调用、学习教练、老师记忆、学习档案
│   └── system/     # 推送、邮箱、天气、备份、迁移、设置
├── static/
│   ├── index.html
│   ├── styles.css
│   └── js/
├── docs/
├── deploy/
└── data/           # 本地数据，默认不提交
```

云服务器上的访问链路是：

```text
浏览器 / 手机
  -> http://你的域名 或 http://服务器公网 IP
  -> Nginx 监听 80 / 443
  -> 转发到 127.0.0.1:8000
  -> Python app.py 提供 Sakura 服务
```

### 1. 本地先跑通项目

这一部分在你的 Windows 电脑上做。

#### 1.1 安装 Python

推荐安装 Python 3.11 或 3.12。

下载地址：

```text
https://www.python.org/downloads/
```

Windows 安装时一定勾选：

```text
Add Python to PATH
```

安装完成后打开 PowerShell：

```powershell
python --version
pip --version
```

能看到版本号就说明 Python 安装成功。

#### 1.2 进入项目目录

例如你的项目在桌面：

```powershell
cd C:\Users\你的用户名\Desktop\demo
```

如果不知道路径，可以在项目文件夹空白处按住 `Shift` 右键，选择“在终端中打开”。

#### 1.3 创建虚拟环境

```powershell
python -m venv .venv
```

激活虚拟环境：

```powershell
.\.venv\Scripts\Activate.ps1
```

如果 PowerShell 提示不允许运行脚本，执行：

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

然后重新激活：

```powershell
.\.venv\Scripts\Activate.ps1
```

看到命令行前面出现 `(.venv)` 就说明成功。

#### 1.4 安装依赖

```powershell
pip install --upgrade pip
pip install -r requirements.txt
```

如果下载太慢，可以临时使用清华源：

```powershell
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

#### 1.5 创建 `.env`

```powershell
copy .env.example .env
```

本地最小配置可以先这样：

```env
PORT=8000
APP_PUBLIC_URL=http://127.0.0.1:8000

SAKURA_ADMIN_PASSWORD=
SAKURA_AUTH_SECRET=
SAKURA_DEMO_MODE=0

LLM_API_KEY=
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
```

这些字段的意思：

```text
PORT：Sakura 后端监听的端口，本地默认 8000。
APP_PUBLIC_URL：外部访问地址，本地写 http://127.0.0.1:8000。
SAKURA_ADMIN_PASSWORD：登录密码。本地自己用可以先空着，公网必须填写。
SAKURA_AUTH_SECRET：登录会话加密用的长随机字符串，公网必须填写。
SAKURA_DEMO_MODE：演示模式。0 表示正常可写入，1 表示尽量只读展示。
LLM_API_KEY：文字讲解接口密钥，例如 DeepSeek Key。
LLM_BASE_URL：文字讲解接口地址，例如 https://api.deepseek.com/v1。
LLM_MODEL：文字讲解模型名，例如 deepseek-chat。
```

本地自己用时可以暂时不设置登录密码。部署到公网时必须设置登录保护。

#### 1.6 启动本地服务

```powershell
python app.py
```

浏览器打开：

```text
http://127.0.0.1:8000
```

能看到 Sakura 做题集界面，就说明本地跑通。

### 2. 准备 GitHub 仓库

如果项目已经在 GitHub 上，可以跳过创建仓库部分。

#### 2.1 不要提交这些内容

确保 `.gitignore` 至少包含：

```gitignore
__pycache__/
*.py[cod]
.venv/
venv/

data/
.env
.deploy_keys/
*.log
*.zip
gitdb/
```

这些文件不应该进入 GitHub：

- `.env`
- `data/`
- 上传的 PDF
- 数据库
- 题图
- 日志
- 部署密钥
- 导出的备份包

#### 2.2 提交代码

```powershell
git status
git add README.md .env.example app.py notify_daily.py requirements.txt sakura static docs deploy tests
git commit -m "Update Sakura deployment docs"
git push
```

如果你使用的是独立项目仓库，可以推到：

```powershell
git push origin main
```

### 3. 购买并初始化云服务器

推荐配置：

```text
系统：Ubuntu 22.04 或 Ubuntu 24.04
CPU：1 核即可起步
内存：1 GB 可以跑小样例，2 GB 更舒服
硬盘：20 GB 起步
带宽：1 Mbps 可体验，3 Mbps 以上更舒服
```

如果只是给朋友展示一个小 demo，不要上传大量 PDF 和真实数据。轻量服务器可以用，但不适合大量图片、PDF 和多人同时使用。

#### 3.1 登录服务器

假设你的服务器公网 IP 是 `你的服务器公网IP`，用户名是 `admin` 或 `root`：

```powershell
ssh admin@你的服务器公网IP
```

如果用密钥：

```powershell
ssh -i C:\Users\你的用户名\.ssh\你的密钥 admin@你的服务器公网IP
```

第一次连接会提示是否信任，输入：

```text
yes
```

#### 3.2 更新系统

在服务器里执行：

```bash
sudo apt update
sudo apt upgrade -y
```

#### 3.3 安装基础工具

```bash
sudo apt install -y python3 python3-venv python3-pip git curl unzip nginx
```

检查版本：

```bash
python3 --version
git --version
nginx -v
```

### 4. 把代码部署到服务器

推荐使用 GitHub 拉代码，这样后续更新更方便。

#### 4.1 创建项目目录

```bash
sudo mkdir -p /opt/sakura-study
sudo chown -R $USER:$USER /opt/sakura-study
cd /opt/sakura-study
```

#### 4.2 从 GitHub 拉代码

如果仓库是公开的：

```bash
git clone https://github.com/Sakura-Yanxi/sakura-question-bank.git .
```

如果你后面换成自己的仓库，把 URL 改成自己的仓库地址。

如果目录不是空的，可以先看一下：

```bash
ls -la
```

不要随便删除 `data/` 和 `.env`，它们可能是你的真实数据和密钥。

#### 4.3 创建服务器虚拟环境

```bash
cd /opt/sakura-study
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

如果服务器访问 PyPI 慢：

```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

#### 4.4 创建服务器 `.env`

```bash
cp .env.example .env
nano .env
```

服务器建议至少填写：

```env
PORT=8000
APP_PUBLIC_URL=http://你的服务器公网IP

SAKURA_ADMIN_PASSWORD=请改成你的登录密码
SAKURA_AUTH_SECRET=请改成一串很长的随机字符
SAKURA_DEMO_MODE=0

LLM_API_KEY=
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
LLM_VISION_MODEL=
LLM_VISION_API_KEY=
LLM_VISION_BASE_URL=

WEWORK_BOT_WEBHOOK=
PUSHPLUS_TOKEN=

REMIND_CHECKIN_MODE=wework
```

逐项说明：

```text
PORT=8000
  Python 服务内部端口。Nginx 会把 80/443 转发到这里，通常不用改。

APP_PUBLIC_URL=http://你的服务器公网IP
  对外访问地址。没有域名时写公网 IP；有域名和 HTTPS 后改成 https://你的域名。

SAKURA_ADMIN_PASSWORD=请改成你的登录密码
  公网部署必须填写。不要用 123456、生日、手机号后几位这类弱密码。

SAKURA_AUTH_SECRET=请改成一串很长的随机字符
  用来保护登录会话。每台服务器单独生成，不要复制别人的。

SAKURA_DEMO_MODE=0
  自己真实使用填 0；只给别人看演示可以填 1。

LLM_API_KEY / LLM_BASE_URL / LLM_MODEL
  文字讲解接口。用于 DeepSeek 知识解读、题目解析、AI 学习教练、阶段反思、教材文字页问答。

LLM_VISION_MODEL / LLM_VISION_API_KEY / LLM_VISION_BASE_URL
  视觉读取接口。用于扫描版教材页、页面截图、没有文本层的 PDF。只做文字讲解时可以先空着。

WEWORK_BOT_WEBHOOK / PUSHPLUS_TOKEN
  推送通道。只配置自己要用的那个即可。
```

生成随机 `SAKURA_AUTH_SECRET`：

```bash
python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(48))
PY
```

把输出复制到 `.env`：

```env
SAKURA_AUTH_SECRET=刚才生成的长字符串
```

保存 nano：

```text
Ctrl + O
Enter
Ctrl + X
```

#### 4.5 手动试运行

```bash
cd /opt/sakura-study
source .venv/bin/activate
python app.py
```

新开一个 SSH 窗口，测试：

```bash
curl -I http://127.0.0.1:8000
```

如果你设置了登录保护，返回 `302` 跳转到 `/login` 是正常的。

停止手动运行：

```text
Ctrl + C
```

### 5. 用 systemd 后台运行

systemd 可以让 Sakura 后台运行，服务器重启后自动启动。

#### 5.1 创建服务文件

```bash
sudo nano /etc/systemd/system/sakura-study.service
```

填入：

```ini
[Unit]
Description=Sakura Study Question Bank
After=network.target

[Service]
Type=simple
User=admin
WorkingDirectory=/opt/sakura-study
EnvironmentFile=/opt/sakura-study/.env
ExecStart=/opt/sakura-study/.venv/bin/python /opt/sakura-study/app.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

如果你的服务器用户名不是 `admin`，把：

```ini
User=admin
```

改成你的用户名。可以用下面命令查看：

```bash
whoami
```

#### 5.2 启动服务

```bash
sudo systemctl daemon-reload
sudo systemctl enable sakura-study
sudo systemctl start sakura-study
```

查看状态：

```bash
sudo systemctl status sakura-study --no-pager
```

看到 `active (running)` 就是成功。

看日志：

```bash
journalctl -u sakura-study -n 80 --no-pager
```

重启服务：

```bash
sudo systemctl restart sakura-study
```

### 6. 配置 Nginx 反向代理

Python 服务只监听本机 `127.0.0.1:8000`，Nginx 负责对公网开放 80 / 443。

#### 6.1 创建 Nginx 配置

```bash
sudo nano /etc/nginx/sites-available/sakura-study
```

如果先用 IP 访问：

```nginx
server {
    listen 80;
    server_name _;

    client_max_body_size 200m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

如果你已经有域名，例如 `your-domain.example`：

```nginx
server {
    listen 80;
    server_name your-domain.example;

    client_max_body_size 200m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

#### 6.2 启用配置

```bash
sudo ln -s /etc/nginx/sites-available/sakura-study /etc/nginx/sites-enabled/sakura-study
sudo nginx -t
sudo systemctl reload nginx
```

如果提示 default 配置冲突，可以移除默认站点：

```bash
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
```

#### 6.3 云厂商防火墙

在阿里云、腾讯云、Azure 等控制台里，确认安全组开放：

```text
TCP 22     SSH
TCP 80     HTTP
TCP 443    HTTPS
```

不要随便开放数据库端口。Sakura 使用 SQLite，不需要对外开放数据库。

### 7. 配置域名

如果你使用 Cloudflare 或其他 DNS 服务，把域名解析到服务器公网 IP。

#### 7.1 添加 DNS 记录

示例：

```text
类型：A
名称：your-domain
内容：你的服务器公网 IP
代理状态：仅 DNS 或已代理都可以，但排错时建议先用“仅 DNS”
TTL：Auto
```

如果完整域名是 `your-domain.example`，那就按你的 DNS 平台规则填写主机记录。

#### 7.2 修改 `.env`

域名能访问后，把服务器 `.env` 改成：

```env
APP_PUBLIC_URL=http://你的域名
```

如果配置了 HTTPS：

```env
APP_PUBLIC_URL=https://你的域名
```

修改后重启：

```bash
sudo systemctl restart sakura-study
```

#### 7.3 大陆服务器注意备案

如果服务器在中国大陆，域名访问通常需要备案。没有备案时，可能 IP 能访问，但域名无法正常打开或被拦截。

如果服务器在香港、日本、新加坡等地区，一般不需要大陆备案，但国内访问速度取决于线路质量。

### 8. 配置 HTTPS

如果你有域名，推荐配置 HTTPS。

#### 8.1 安装 Certbot

```bash
sudo apt install -y certbot python3-certbot-nginx
```

#### 8.2 申请证书

把域名换成你的：

```bash
sudo certbot --nginx -d 你的域名
```

按提示输入邮箱，同意条款。

完成后测试：

```bash
curl -I https://你的域名
```

#### 8.3 自动续期

Certbot 通常会自动配置续期。可以测试：

```bash
sudo certbot renew --dry-run
```

### 9. 配置登录保护

公网部署必须开启登录保护，不然别人知道域名就能改你的题库。

服务器 `.env` 里填写：

```env
SAKURA_ADMIN_PASSWORD=你的登录密码
SAKURA_AUTH_SECRET=一串很长的随机字符串
```

重启：

```bash
sudo systemctl restart sakura-study
```

浏览器访问时会先进入登录页面。

如果忘记密码：

```bash
cd /opt/sakura-study
nano .env
```

修改 `SAKURA_ADMIN_PASSWORD` 后重启服务。

### 10. 配置 AI API

Sakura 的 AI 能力分成两条线：文字讲解和视觉读取。新手先记住一句话：

```text
DeepSeek 这类文字模型适合讲解文字内容。
扫描版教材页、图片题图、页面截图，需要支持图片输入的视觉模型。
```

不配置 AI API 时，题库、错题、每日练习、导入、导出、备份和本地统计仍可使用，只是不能调用外部讲解能力。

#### 10.1 文字讲解接口

文字讲解接口用于：

- DeepSeek 知识解读。
- 题目提示和完整解析。
- 变式练习。
- 错因分析。
- AI 学习教练。
- 周/月阶段反思。
- 带文本层教材页的问答。

DeepSeek 示例：

```env
LLM_API_KEY=你的 DeepSeek Key
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
```

小米 MiMo 或其他兼容接口也可以，只要把地址和模型名换成对应平台给你的值：

```env
LLM_API_KEY=对应平台给你的 Key
LLM_BASE_URL=对应平台兼容 OpenAI 调用格式的地址
LLM_MODEL=对应平台支持的文字模型名
```

如果你使用中转站：

```env
LLM_API_KEY=中转站给你的 Key
LLM_BASE_URL=中转站给你的兼容 OpenAI 调用格式的地址
LLM_MODEL=中转站支持的模型名
```

兼容历史变量时，读取优先级是：

```text
LLM_API_KEY > MIMO_API_KEY > DEEPSEEK_API_KEY
```

建议以后统一使用 `LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL`，这样不容易混。

#### 10.2 视觉读取接口

视觉读取接口用于：

- 扫描版教材页。
- 整页图片 PDF。
- 拍照生成的 PDF。
- 教材页截图或题图截图。
- 页面没有可复制文字，但你希望系统直接“看图”解释。

如果文字和视觉用同一家供应商，只要额外填视觉模型名，Key 和地址可以留空复用文字接口：

```env
LLM_API_KEY=你的 Key
LLM_BASE_URL=https://同一家供应商的地址/v1
LLM_MODEL=文字模型名

LLM_VISION_MODEL=支持图片输入的模型名
LLM_VISION_API_KEY=
LLM_VISION_BASE_URL=
```

如果文字用 DeepSeek，视觉用另一家支持图片输入的模型，就单独填写视觉三项：

```env
LLM_API_KEY=你的 DeepSeek Key
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat

LLM_VISION_MODEL=支持图片输入的模型名
LLM_VISION_API_KEY=视觉接口 Key
LLM_VISION_BASE_URL=视觉接口地址
```

注意：

- 视觉模型必须支持图片输入，只填一个普通文字模型名没有用。
- 视觉读取只在你主动点击视觉读取，或教材页没有文本层但你发起教材问答时使用。
- 如果教材 PDF 本身有文本层，系统会优先走文字讲解接口，不一定需要视觉模型。
- 视觉接口通常比文字接口更容易产生费用，请先用一页小样例测试。

#### 10.3 AI 学习教练

AI 学习教练走文字讲解接口，不需要视觉接口。它会读取：

- 学习档案版本。
- 近期错题、半会题、需复习题。
- 到期复习数量和逾期复习数量。
- 薄弱知识点和前置短板。
- 老师记忆。
- 考试日期、每日可用时间、重点科目。

它的作用不是替你自动做题，而是把已有证据整理成下一步行动：

```text
先还逾期/今日到期错题
  -> 再攻坚当前薄弱知识点
  -> 再补前置基础题
  -> 临近考试时加入限时模拟卷
```

每次新增错题洞察、复习状态或教材记忆后，学习档案可以按版本更新；下一次生成计划时，教练会基于新证据重新排序薄弱点和今日任务。

#### 10.4 修改配置后如何生效

修改 `.env` 后重启服务：

```bash
sudo systemctl restart sakura-study
```

查看服务是否启动成功：

```bash
sudo systemctl status sakura-study --no-pager
```

然后到页面里测试：

```text
AI 对话 / API 测试：测试文字讲解接口。
教材精读 / 视觉读取：测试视觉接口。
总结与反思：测试阶段复盘。
AI 学习教练：测试学习档案和计划生成。
```

#### 10.5 常见 AI 错误

```text
401 / invalid_api_key
  Key 错了、过期了，或者复制时多了空格。

402 / insufficient_balance
  对应供应商余额不足，或者这个模型没有开通计费权限。需要到服务商平台充值或开通。

404 / model_not_found
  模型名不存在，或者账号没有调用权限。

429 / rate limit
  调用太频繁，稍等一会儿再试。

教材页问答说“没有文本层”
  说明这一页可能是扫描图片。配置视觉模型后再点视觉读取。

DeepSeek 能文字问答，但读不了教材截图
  这是正常的。DeepSeek 文字模型负责文本讲解，截图要交给支持图片输入的视觉模型。
```

### 11. 配置推送

Sakura 当前支持三种推送：

- 企业微信机器人
- PushPlus
- SMTP 邮箱

#### 11.1 企业微信机器人

推荐优先用企业微信机器人。

步骤：

1. 创建或进入企业微信群。
2. 添加群机器人。
3. 复制机器人 Webhook。
4. 在 Sakura 的“推送通道配置”里填写企业微信机器人 Webhook。
5. 保存配置。
6. 在“提醒与打卡设置”里选择“企业微信打卡”。
7. 点击测试推送。

`.env` 对应字段：

```env
WEWORK_BOT_WEBHOOK=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxxx
REMIND_CHECKIN_MODE=wework
```

不要把真实 Webhook 写到 README、issue 或截图里。

#### 11.2 PushPlus

PushPlus 可作为备用通道：

```env
PUSHPLUS_TOKEN=你的 PushPlus Token
REMIND_CHECKIN_MODE=pushplus
```

如果测试返回：

```text
code: 905
账户未进行实名认证
```

通常表示 PushPlus 账号未完成实名，不是 Sakura 配置丢失。

#### 11.3 QQ 邮箱 SMTP

QQ 邮箱不要填登录密码，要填授权码。

操作步骤：

1. 打开 QQ 邮箱网页版。
2. 进入“设置”。
3. 找到“账号”或“账户安全”。
4. 开启 SMTP 服务。
5. 生成授权码。
6. 在 Sakura 里填写 SMTP 配置。
7. 保存后点击“测试邮箱”。

常用配置：

```env
EMAIL_ENABLED=1
EMAIL_HOST=smtp.qq.com
EMAIL_PORT=465
EMAIL_USE_SSL=1
EMAIL_USE_STARTTLS=0
EMAIL_USER=你的QQ邮箱@qq.com
EMAIL_PASSWORD=QQ邮箱授权码
EMAIL_TO=收件邮箱@qq.com
EMAIL_FROM=你的QQ邮箱@qq.com
EMAIL_FROM_NAME=Sakura 做题集
```

### 12. 配置定时提醒

页面里可以直接设置早晚提醒、天气推送和打卡入口。保存后系统会写入 `.env` 并安装 crontab。

也可以手动在 `.env` 中配置：

```env
REMIND_MORNING_ON=1
REMIND_MORNING_TIME=10:00
REMIND_NIGHT_ON=1
REMIND_NIGHT_TIME=20:00
REMIND_WEATHER_ON=1
REMIND_WEATHER_TIME=22:30
REMIND_CHECKIN_MODE=wework
REMIND_DAILY_SCOPE=due
REMIND_DAILY_LIMIT=20
REMIND_SEND_PDF=1
WEATHER_CITY=北京 海淀区
```

查看当前定时任务：

```bash
crontab -l
```

手动测试早安推送：

```bash
cd /opt/sakura-study
source .venv/bin/activate
python notify_daily.py --morning
```

手动测试天气推送：

```bash
cd /opt/sakura-study
source .venv/bin/activate
python notify_daily.py --weather
```

如果测试按钮能推送，但定时没推送，重点检查：

- 服务器时区是否正确。
- crontab 是否存在 Sakura 任务。
- `.env` 是否保存了开启状态。
- systemd 服务是否正常。

设置中国时区：

```bash
timedatectl
sudo timedatectl set-timezone Asia/Shanghai
timedatectl
```

### 13. 数据迁移

#### 13.1 推荐方式：页面导出备份

在本地 Sakura 页面里：

```text
数据迁移 -> 导出完整备份
```

得到一个 zip 备份包。

然后在云端 Sakura 页面：

```text
数据迁移 -> 导入备份
```

这种方式最安全，因为它会按 Sakura 的规则处理数据库和文件。

#### 13.2 命令行上传备份包

如果备份包较大，可以用 `scp`：

```powershell
scp .\sakura_backup.zip admin@你的服务器公网IP:/tmp/sakura_backup.zip
```

如果 SSH 端口不是 22：

```powershell
scp -P 端口号 .\sakura_backup.zip admin@你的服务器公网IP:/tmp/sakura_backup.zip
```

上传后仍建议在页面里导入，或者按照项目提供的迁移接口恢复。

#### 13.3 不要直接覆盖 `.env`

本地 `.env` 里可能是本地地址和本地密钥，云端 `.env` 里是公网地址和服务器密钥。

迁移数据时不要直接把本地 `.env` 覆盖到服务器。

### 14. 更新服务器代码

后续你在本地修改代码并推到 GitHub 后，服务器更新步骤：

```bash
cd /opt/sakura-study
git fetch origin
git checkout main
git pull origin main
source .venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart sakura-study
```

查看服务是否正常：

```bash
sudo systemctl status sakura-study --no-pager
journalctl -u sakura-study -n 80 --no-pager
```

如果只是改 README 或文档，不需要重启服务。

### 15. 演示模式

如果只是给朋友体验，不想让别人修改你的数据，可以开启演示模式：

```env
SAKURA_DEMO_MODE=1
```

然后重启：

```bash
sudo systemctl restart sakura-study
```

演示环境建议：

- 不导入真实学习数据。
- 不放真实 API Key。
- 开启登录保护。
- 只上传少量演示 PDF。
- 定期清理 `data/`。

### 16. 常见问题

#### 16.1 浏览器打不开

先在服务器检查本机服务：

```bash
curl -I http://127.0.0.1:8000
sudo systemctl status sakura-study --no-pager
```

再检查 Nginx：

```bash
sudo nginx -t
sudo systemctl status nginx --no-pager
curl -I http://127.0.0.1
```

最后检查云厂商防火墙是否开放 80 / 443。

#### 16.2 访问显示 302

如果开启了登录保护，`curl -I` 看到：

```text
HTTP/1.1 302 Found
Location: /login
```

这是正常的，说明服务在把未登录用户引导到登录页。

#### 16.3 上传 PDF 很慢

可能原因：

- 服务器带宽太小。
- PDF 太大。
- PDF 每页图像分辨率太高。
- 服务器内存较小。

建议：

- 先用小文件测试。
- 用页码范围导入。
- 不要一次上传整套超大资料。
- 轻量服务器只适合个人使用和小样例展示。

#### 16.4 页面还是旧样式

先强制刷新：

```text
Ctrl + F5
```

如果还不行，检查服务器是否拉到了最新代码：

```bash
cd /opt/sakura-study
git log -1 --oneline
grep -n "static/js/core/app.js" static/index.html
```

#### 16.5 AI 不回答

检查：

- `LLM_API_KEY` 是否填写。
- `LLM_BASE_URL` 是否正确。
- `LLM_MODEL` 是否是服务商支持的模型。
- 服务器是否能访问对应 API。
- 如果是教材截图或扫描页，是否配置了 `LLM_VISION_MODEL`。
- 如果报 `402 insufficient_balance`，先去供应商后台看余额和模型权限。

测试网络：

```bash
curl -I https://api.deepseek.com
```

如果文字问答正常，但教材视觉读取失败，优先检查：

```text
1. 视觉模型名是否支持图片输入。
2. LLM_VISION_API_KEY 是否属于视觉模型对应平台。
3. LLM_VISION_BASE_URL 是否和该平台文档一致。
4. 当前供应商账户是否有余额。
5. 这一页教材图片是否已经成功生成。
```

#### 16.6 企业微信测试成功，但定时没收到

检查：

```bash
crontab -l
timedatectl
journalctl -u sakura-study -n 80 --no-pager
```

如果手动点击测试能收到，通常说明 Webhook 没问题，问题更可能在定时任务、时区或开关状态。

#### 16.7 PushPlus 报实名认证

如果返回 `code: 905`，一般是 PushPlus 平台要求账号实名认证。企业微信机器人不受这个影响。

#### 16.8 忘记登录密码

服务器上修改：

```bash
cd /opt/sakura-study
nano .env
```

改：

```env
SAKURA_ADMIN_PASSWORD=新密码
```

重启：

```bash
sudo systemctl restart sakura-study
```

### 17. 安全建议

最低限度请做到：

- 公网部署一定设置 `SAKURA_ADMIN_PASSWORD`。
- `SAKURA_AUTH_SECRET` 使用长随机字符串。
- 不提交 `.env`。
- 不提交 `data/`。
- 不在截图里暴露 Webhook、Token、服务器 IP、密码。
- 云服务器只开放必要端口。
- 重要数据定期导出备份。
- 给朋友演示时优先使用 `SAKURA_DEMO_MODE=1`。

如果服务器只用于展示，不要把自己的真实错题库、教材 PDF、AI Key 和推送密钥放进去。

版权和商用边界：

- 不要把没有授权的教材、试卷、题库、PDF、截图或图片放进公开演示站点。
- 不要把真实学生数据、他人题库或课程资料打包成备份包传播。
- Sakura 做题集当前只允许个人学习、技术交流和非商业二次开发。
- 未经 Sakura-Yanxi 明确书面许可，禁止商业售卖、培训机构使用、付费课程包装、SaaS 托管收费、代部署收费、闭源商业复制和商业宣传使用。
- 二次展示或二次开发时必须保留原作者署名和项目来源。

### 18. 一键排查清单

服务状态：

```bash
sudo systemctl status sakura-study --no-pager
```

服务日志：

```bash
journalctl -u sakura-study -n 120 --no-pager
```

Nginx 配置：

```bash
sudo nginx -t
```

Nginx 状态：

```bash
sudo systemctl status nginx --no-pager
```

本机端口：

```bash
curl -I http://127.0.0.1:8000
```

公网端口：

```bash
curl -I http://你的域名
```

当前代码版本：

```bash
cd /opt/sakura-study
git log -1 --oneline
```

服务器资源：

```bash
free -h
df -h
top
```

### 19. 推荐部署流程总结

第一次部署：

```text
本地跑通
  -> 推到 GitHub
  -> 服务器安装 Python / Git / Nginx
  -> clone 项目到 /opt/sakura-study
  -> 创建 .venv 并安装依赖
  -> 写服务器 .env
  -> 手动 python app.py 测试
  -> 配 systemd
  -> 配 Nginx
  -> 配域名和 HTTPS
  -> 配登录保护
  -> 测试 AI / 推送 / 上传
```

后续更新：

```text
本地修改
  -> 测试
  -> git commit
  -> git push
  -> 服务器 git pull
  -> pip install -r requirements.txt
  -> systemctl restart sakura-study
```

数据迁移：

```text
本地页面导出备份
  -> 云端页面导入备份
  -> 检查题库、错题、资料、老师记忆
  -> 测试每日练习和推送
```

做到这里，Sakura 做题集就从本地 demo 变成了一个可以公网访问、可登录保护、可推送提醒、可迁移数据的轻量学习系统。

### 20. 禁止商用与免责声明

#### 20.1 禁止商用

Sakura 做题集当前公开用于个人学习、技术交流和非商业 demo 展示。公开仓库不等于允许商用，也不等于作者放弃著作权。

未经 Sakura-Yanxi 明确书面许可，禁止：

- 将本项目作为商业产品售卖。
- 将本项目包装进付费课程、培训机构系统、商业训练营或收费社群。
- 将本项目部署成收费 SaaS、托管服务、代部署服务或闭源商业服务。
- 删除作者署名后重新发布、重新命名或伪装成完全原创项目。
- 将界面、交互、文档、海报、核心代码或功能结构直接复制到商业项目。
- 使用相似名称、相似 logo、相似页面误导他人认为是官方商业版本。

允许的范围：

- 个人学习和本地自用。
- 非商业技术交流。
- 保留原作者署名和项目来源的非商业二次开发。
- 课程作业、个人作品集或学习记录展示，但必须说明来源，不得用于收费交付。

#### 20.2 免责声明

- 本教程和项目按“现状”提供，不承诺适用于任何特定考试、课程、机构、生产环境或商业场景。
- 部署者需要自行负责服务器安全、登录密码、`.env`、API Key、Webhook、邮箱授权码、日志、备份包和数据库文件的保管。
- 使用外部文字讲解接口、视觉读取接口、天气接口、推送接口产生的费用、余额不足、限流、封禁、服务中断等问题，由对应账号持有人自行承担。
- AI 生成的题目解析、教材解读、学习计划、阶段反思和建议可能存在错误，只能作为学习辅助，不能替代教材、教师、标准答案、考试官方说明或专业判断。
- 请勿上传、传播、打包或公开展示没有授权的 PDF、教材、试卷、题库、图片和课程资料；由此产生的版权、合规或法律风险由使用者自行承担。
- 公网部署需要遵守所在地关于域名、备案、网络安全、版权和数据合规的要求；因部署、开放访问、二次分发或使用不当造成的后果由部署者自行承担。
- 作者不对因误操作、数据丢失、服务器被攻击、密钥泄露、接口费用、资料侵权或第三方服务异常造成的损失承担责任。

一句话总结：

```text
可以学习、可以自用、可以非商业交流；禁止商用，风险自负，资料版权和数据安全自己负责。
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

推荐方式：

在页面里打开“提醒与设置 -> 版本管理”，看到新版本后点击“一键更新”。更新完成后重启 Sakura 服务。

如果页面打不开，也可以直接运行项目自带脚本。脚本会自动判断：是 Git 仓库就拉取代码，不是 Git 仓库就下载最新 Release zip。

```bash
# Windows
update.bat

# Linux / macOS / 服务器
bash update.sh
```

已用 Git 下载的用户也可以手动运行：

```bash
git pull --ff-only
pip install -r requirements.txt
python app.py
```

这些更新方式都会保留 `data/`、`.env`、`.venv`、数据库、题图、教材文件和用户上传文件。

如果手里的旧版本还没有轻量更新器，需要先手动升级到包含新 `update.bat` / `update.sh` 的版本一次；之后再更新就可以直接用脚本或页面一键更新。

不用 Git 且脚本也无法连接 GitHub 时，再到 Release 页面下载最新 zip，覆盖代码文件。覆盖时保留自己的 `data/`、`.env` 和 `.venv`。

Release zip 更新会把旧代码备份到 `data/update_backups/`，默认只保留最近 3 份。需要保留更多时，可以在 `.env` 里设置 `SAKURA_UPDATE_BACKUP_KEEP=5`。

Windows 脚本：

```text
update.bat
```

Linux / macOS / 服务器：

```bash
bash update.sh
```

## 授权说明

仓库包含 `LICENSE` 文件，采用自定义非商业源码授权。

需要说清楚的是：因为项目包含禁止商用条款，它不是 OSI 意义上的宽松开源协议。这里的“开源”指公开源码供学习、交流、个人使用和非商业二次开发。

商业使用、培训机构产品、付费课程、SaaS 服务、代部署收费、闭源商业项目或商业宣传材料，都需要先获得 Sakura-Yanxi 的明确书面许可。

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

迁移导入前会先验证 ZIP 包结构，确认是 Sakura 迁移包后才备份当前数据并开始恢复。当前数据会备份到 `data/migration_backups/`，默认保留最近 3 份；需要保留更多时，可以设置 `SAKURA_MIGRATION_BACKUP_KEEP=5`。

如果服务在导入中途异常退出，`data/migration_uploads/` 里可能留下临时 ZIP。新版本会在下次导入前自动清理 24 小时以前的残留上传包。

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

## 支持作者

如果你感觉本工具有用，想请作者喝杯可乐，欢迎自愿打赏。

<p>
  <img src="donation/wechat-pay.jpg" alt="微信支付打赏码" width="260" />
  <img src="donation/alipay.jpg" alt="支付宝打赏码" width="260" />
</p>
