# Sakura 做题集

> 一个本地优先的个人学习工作台：管理 PDF 题本、模拟卷、教材精读、错题复习、每日练习、阶段复盘和学习教练。

## 项目入口

- GitHub 仓库：https://github.com/Sakura-Yanxi/sakura-question-bank
- 当前版本：`v1.0.8`
- 发布页：https://github.com/Sakura-Yanxi/sakura-question-bank/releases
- 宣传海报：`docs/poster/sakura-demo-poster.png`
- 保姆级部署教程：`docs/本地到云端部署保姆级教程.md`

Sakura 的目标很直接：做过的题不浪费，错过的知识点不丢，复习节奏有记录，每一轮学习都能留下可回看的证据。

它不是一个只保存截图的题库，也不是一个只聊天的工具。它把“题目、错因、复习、教材、记忆、计划”放在同一个本地工作台里，让学习过程能沉淀下来。

`v1.0.8` 重点更新：

- 增强版本更新和迁移安全，坏的迁移 ZIP 不会生成无用备份。
- 浏览器上传 PDF、教材和迁移 ZIP 时增加大小保护，默认上限 1024 MB。
- 更新备份和迁移备份会自动保留最近几份，减少长期磁盘占用。
- 前端动态下拉选项补充转义，特殊字符不会污染页面结构。
- 每日练习页新增“艾宾浩斯队列”和“最近/今日推送错题”两个可折叠区域，推送过的错题可以直接在页面里回看。
- 优化 iPad 平板横竖屏布局，顶部导航不再撑出大面积空白，规则面板标题和计数徽标不会互相挤压。

## 适合谁

- 想把 PDF 题本、模拟卷、教材页面统一管理的人。
- 想长期维护错题本、复习记录和阶段复盘的人。
- 想让讲解、教材阅读和每日练习围绕自己的真实错题展开的人。
- 想本地保存数据，不希望题库和密钥默认上传到云端的人。
- 想做个人 demo、课程作业、学习作品集或非商业二次开发的人。

## 当前代码状态

后端入口是 `app.py`，当前约 `2744` 行。它主要负责启动服务、路由入口和历史 Handler 装配。

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

## 云端 / 服务器部署教程总入口

这一节只放在 Notion 项目页里，用来给完全没接触过服务器的新手看。后面如果还有其他项目，可以继续在这里新增“项目二”“项目三”，每个项目各自放一套部署步骤。

服务器部署的核心思路是：

```text
本地电脑负责写代码和备份数据
GitHub 负责保存公开代码
云服务器负责 24 小时运行 Sakura
Nginx 负责把公网访问转发到 Sakura
systemd 负责开机自启和异常后重启
```

### 免费 / 低成本服务器参考

如果你还没有服务器，可以先看这个视频了解学生党怎么从 0 到 1 拿一台阿里云服务器，并部署第一个网站：

【从0到1：学生党如何免费拿阿里云服务器，并部署第一个网站-哔哩哔哩】
https://b23.tv/Z8bBgG3

提醒：云厂商活动、免费额度和学生认证规则会变化，实际以阿里云页面显示为准。视频用于理解流程，不要把自己的密码、Key、Webhook 或真实学习资料公开出去。

### 项目一：Sakura 做题集部署到 Ubuntu 服务器

适合场景：

- 想让电脑、iPad、手机都能通过公网访问同一个 Sakura。
- 想让每日练习、提醒、推送和版本更新在服务器上长期运行。
- 想给朋友或老师看 demo，但不想每次都打开自己电脑。

不建议的场景：

- 没有设置登录密码就直接放公网。
- 把真实教材、试卷、题库、API Key 放到公开演示站。
- 用轻量服务器长期跑多人高并发或大量 PDF 处理。

### 1. 准备服务器

推荐配置：

```text
系统：Ubuntu 22.04 / 24.04
CPU：1 核或以上
内存：2 GB 起步，4 GB 更舒服
磁盘：40 GB 起步
端口：22、80、443
项目目录：/opt/sakura-study
运行用户：admin 或 root
```

如果只是 demo，先用公网 IP 访问即可；如果要长期使用，再绑定域名和 HTTPS。

### 2. 用 SSH 连接服务器

Windows PowerShell 示例：

```powershell
ssh admin@你的服务器公网IP
```

如果使用密钥：

```powershell
ssh -i C:\Users\你的用户名\.ssh\你的密钥 admin@你的服务器公网IP
```

第一次连接会询问是否信任服务器，输入 `yes`。如果连不上，先检查阿里云安全组是否放行 22 端口。

### 3. 安装基础依赖

进入服务器后执行：

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip nginx
python3 --version
git --version
```

如果提示没有权限，确认当前用户是否可以使用 `sudo`。如果你用的是 `root`，可以去掉命令前面的 `sudo`。

### 4. 拉取 Sakura 代码

```bash
sudo mkdir -p /opt/sakura-study
sudo chown -R $USER:$USER /opt/sakura-study
cd /opt/sakura-study
git clone https://github.com/Sakura-Yanxi/sakura-question-bank.git .
```

如果目录不是空的，先确认里面没有自己的数据再处理。不要随便删除 `data/`、`.env`、上传 PDF 或数据库。

### 5. 创建 Python 虚拟环境

```bash
cd /opt/sakura-study
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

如果依赖下载慢，可以临时使用镜像：

```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 6. 创建服务器 `.env`

```bash
cp .env.example .env
nano .env
```

服务器最少建议填写：

```env
PORT=8000
APP_PUBLIC_URL=http://你的服务器公网IP
SAKURA_ADMIN_PASSWORD=请改成强密码
SAKURA_AUTH_SECRET=请改成一长串随机字符
SAKURA_DEMO_MODE=0
```

如果要用 AI 讲解，再填：

```env
LLM_API_KEY=你的文字模型 Key
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat

LLM_VISION_MODEL=支持图片输入的视觉模型名
LLM_VISION_API_KEY=可选，留空则沿用 LLM_API_KEY
LLM_VISION_BASE_URL=可选，留空则沿用 LLM_BASE_URL
```

如果要推送每日练习，再按实际渠道填写企业微信、PushPlus 或邮箱 SMTP。所有 Key 只写在服务器 `.env`，不要提交到 GitHub。

### 7. 先手动启动测试

```bash
cd /opt/sakura-study
source .venv/bin/activate
python app.py
```

看到类似下面的信息就说明本机服务起来了：

```text
Sakura demo running at http://127.0.0.1:8000
```

新开一个 SSH 窗口测试：

```bash
curl http://127.0.0.1:8000
```

能返回 HTML 内容就可以继续。测试完按 `Ctrl+C` 停止手动运行，接下来交给 systemd 后台运行。

### 8. 配置 systemd 后台运行

创建服务文件：

```bash
sudo nano /etc/systemd/system/sakura-study.service
```

填入：

```ini
[Unit]
Description=Sakura Study
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/sakura-study
ExecStart=/opt/sakura-study/.venv/bin/python /opt/sakura-study/app.py
Restart=always
RestartSec=3
User=admin
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

如果你的服务器运行用户不是 `admin`，把 `User=admin` 改成实际用户名。然后执行：

```bash
sudo systemctl daemon-reload
sudo systemctl enable sakura-study
sudo systemctl start sakura-study
sudo systemctl status sakura-study
```

查看日志：

```bash
journalctl -u sakura-study -n 100 --no-pager
```

### 9. 配置 Nginx 反向代理

创建配置：

```bash
sudo nano /etc/nginx/sites-available/sakura-study
```

没有域名时先用公网 IP：

```nginx
server {
    listen 80;
    server_name _;

    client_max_body_size 1024m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

启用配置：

```bash
sudo ln -s /etc/nginx/sites-available/sakura-study /etc/nginx/sites-enabled/sakura-study
sudo nginx -t
sudo systemctl reload nginx
```

然后浏览器访问：

```text
http://你的服务器公网IP
```

如果打不开，检查阿里云安全组是否放行 80 端口，服务器防火墙是否拦截，Nginx 是否启动。

### 10. 后续更新服务器

已经用 Git 部署的服务器，后续更新通常这样：

```bash
cd /opt/sakura-study
git pull --ff-only
source .venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart sakura-study
```

也可以使用项目自带脚本：

```bash
cd /opt/sakura-study
bash update.sh
sudo systemctl restart sakura-study
```

更新脚本会尽量保留 `data/`、`.env`、`.venv` 和用户上传文件。Release zip 更新会把旧代码备份到 `data/update_backups/`，默认只保留最近 3 份。

### 11. 本地数据迁移到服务器

推荐在本地 Sakura 页面里导出迁移 ZIP，然后上传到服务器或在云端页面导入。

命令行上传示例：

```powershell
scp .\sakura_backup.zip admin@你的服务器公网IP:/tmp/sakura_backup.zip
```

迁移注意：

- 不要直接把本地 `.env` 覆盖到服务器 `.env`。
- 不要把真实数据放进公开仓库。
- 导入前确认服务器磁盘空间够用。
- 导入后检查题库、教材页图、错题记录和每日练习是否正常。

### 12. 新手排错清单

页面打不开：

- 阿里云安全组是否开放 80。
- `systemctl status sakura-study` 是否 active。
- `sudo nginx -t` 是否通过。
- `journalctl -u sakura-study -n 100 --no-pager` 有没有报错。

依赖安装失败：

- Python 是否是 3.11 或 3.12。
- `.venv` 是否用错了旧 Python。
- 是否需要 `python -m pip install --upgrade pip`。

AI 读取失败：

- 文字模型和视觉模型是否填对。
- 视觉模型是否真的支持图片输入。
- 返回 `402 insufficient_balance` 通常是平台余额、套餐或权限问题。

更新后还是旧版本：

- 是否重启了 `sakura-study` 服务。
- 浏览器是否缓存旧前端文件。
- 服务器是否真的拉到了最新 GitHub 提交。

### 13. 服务器安全提醒

- 公网部署必须设置 `SAKURA_ADMIN_PASSWORD`。
- `SAKURA_AUTH_SECRET` 每台服务器单独生成，不要复制别人的。
- `.env`、`data/`、日志、数据库、备份包不要公开。
- 只开放必要端口，通常是 22、80、443。
- 不要把没有授权的教材、试卷和题库上传到公开演示环境。
- 大陆服务器绑定域名通常需要备案；没有备案时可以先用公网 IP 测试。

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
