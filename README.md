# Sakura 做题集

Sakura 做题集是一个本地优先的个人学习工作台，用来管理 PDF 题本、模拟卷、教材精读、错题复习、每日练习、阶段复盘和学习教练。

它的目标很直接：做过的题不浪费，错过的知识点不丢，复习节奏有记录，每一轮学习都能留下可回看的证据。

> 当前项目是个人学习 demo。欢迎学习、交流和非商业二次开发；未经作者书面许可，禁止商业使用。公开展示或二次开发时请保留 Sakura-Yanxi 署名和原项目地址。

## 当前状态

- 当前版本：`v1.0.6`
- 项目地址：[Sakura-Yanxi/sakura-question-bank](https://github.com/Sakura-Yanxi/sakura-question-bank)
- 发布页：[GitHub Releases](https://github.com/Sakura-Yanxi/sakura-question-bank/releases)
- 更新方式：Git 用户运行 `update.bat` / `update.sh`；下载压缩包的用户覆盖代码文件，并保留自己的 `data/` 和 `.env`。
- 当前代码结构：后端入口 [app.py](app.py) 已收敛为服务装配和 HTTP Handler，主要业务逻辑已经拆到 `sakura/` 各模块；当前 `app.py` 约 `2670` 行。
- 宣传海报：见 [docs/poster/sakura-demo-poster.png](docs/poster/sakura-demo-poster.png)。

## 主要功能

### 资料导入

- 导入 PDF 做题本，按页保存题图和可提取文本。
- 支持只导入指定页码范围。
- 普通题本、模拟卷和教材精读分开管理。
- 教材精读按页保存截图和段落，适合逐段阅读。
- 教材导入时会识别明显像试卷的文件名，例如“模拟卷”“真题卷”“试卷”等，并提示放到对应模块。

### 题库管理

- 按科目、资料、章节、知识点、状态和关键词筛选题目。
- 题图可放大查看，也可以重新裁切题目边界。
- 支持修改资料名称、科目和类型。
- 支持删除资料、删除题目、更新章节和重新扫描章节。
- 支持按条件导出错题 PDF。

### 错题复习

- 记录未做、做对、做错、半会、需复习等状态。
- 可标记计算失误、公式遗忘、逻辑死角、题意理解偏差等错因。
- 多次复盘不会覆盖旧备注，每次练习都保留记录。
- 复习间隔参考 1 / 3 / 7 / 14 / 30 天节奏。
- 错题洞察会进入学习档案，用来生成后续复习建议。

### 每日练习

- 默认从错题、半会题、到期复习题和薄弱章节里生成练习。
- 可按科目、资料、章节和题量自定义练习范围。
- 练习结果会回写到题库和复习记录。
- 推送每日练习时可附带 PDF，手机端也可以快速回填状态。

### 教材精读

- 教材 PDF 会保存为教材库，不和题本、模拟卷混在一起。
- 每页都会生成页面截图，并尽量提取可复制文本。
- 选中段落提问时，优先把当前页文字、选中段落和历史追问交给文字讲解接口。
- 如果页面是扫描件、拍照页或没有文本层，可以手动使用视觉读取，让支持图片输入的模型读取整页截图。
- 教材精读对话可以压缩成老师记忆，记录教材、页码、困惑点、关键理解和后续复习建议。

## 智能讲解与学习教练

这部分是可选能力。不配置外部接口时，资料导入、题库筛选、错题复习、每日练习、备份和导出仍可正常使用。

### 文字讲解接口

文字讲解接口用于：

- 知识点解释、公式来源、解题思路和常见误区。
- 题目提示、关键步骤、完整解析。
- 错因分析、变式练习、阶段反思。
- 教材中可提取文字页面的问答。
- 学习教练的对话、计划和学习档案解读。

DeepSeek、MiMo 或其他兼容 OpenAI 调用格式的文字模型都可以放在这里。以 DeepSeek 为例：

```env
LLM_API_KEY=你的接口密钥
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
```

### 视觉读取接口

视觉读取接口用于读取图片内容，例如：

- 扫描版教材页。
- 没有文本层的 PDF 页面。
- 教材截图里的公式、图表、箭头和版式关系。
- 需要模型直接看图的教材精读场景。

视觉模型必须支持图片输入。它可以和文字讲解接口使用不同供应商：

```env
LLM_VISION_MODEL=支持图片输入的模型名
LLM_VISION_API_KEY=可选，留空则沿用 LLM_API_KEY
LLM_VISION_BASE_URL=可选，留空则沿用 LLM_BASE_URL
```

常见组合：

- 只做文字讲解：填写 `LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL`。
- 文字和视觉用同一家：额外填写 `LLM_VISION_MODEL`，视觉 Key 和视觉地址可以留空。
- 文字和视觉用不同家：文字部分填 DeepSeek 等；视觉部分单独填 `LLM_VISION_MODEL`、`LLM_VISION_API_KEY`、`LLM_VISION_BASE_URL`。

注意：

- DeepSeek 这类文字模型适合解释文本，但不能直接看懂一张教材截图。
- 视觉读取只在你主动触发对应功能时使用，不会后台自动消耗额度。
- 如果返回 `402 insufficient_balance`，通常是对应服务账号余额不足、套餐不可用或模型权限没有开通，不是 Sakura 的页面读取逻辑坏了。

### 学习教练

学习教练不是单纯聊天框。它会读取本地学习证据，再给出贴近当前阶段的建议。

它会用到：

- 最新学习档案。
- 近期错题和错因。
- 待复习题和逾期题。
- 薄弱知识点和前置基础缺口。
- 老师记忆和外部经验库。
- 考试日期、每日可用时间和当前重点科目。

它能做的事：

- 解释当前最该补的知识点。
- 生成今日行动建议。
- 根据复习队列安排先后顺序。
- 根据错因给出训练策略。
- 把高价值对话压缩成长期老师记忆。
- 在新错题、新复习状态、新教材记忆进入系统后，刷新学习档案和计划。

这里的“自主迭代”指的是系统会用新增学习证据更新档案和计划，不是自动替用户上传资料、自动修改题库或自动调用外部接口。教练计划可以清空重算，但不会删除题库、错题证据、老师记忆和历史复盘。

大致链路：

```text
做题 / 复习 / 教材精读
  -> 记录状态、错因、备注和教材记忆
  -> 汇总知识点掌握度、反复误区和前置短板
  -> 生成新的学习档案版本
  -> 排序当前最该处理的薄弱点
  -> 生成今日任务和阶段计划
  -> 下一轮做题后继续更新
```

## 提醒与推送

- 支持企业微信机器人、PushPlus 和 SMTP 邮件。
- 可设置早晚提醒、天气提醒和每日练习推送。
- 公网部署时可开启访问密码和登录失败锁定。
- 版本管理卡片会检查 GitHub Releases；Git 下载和 Release zip 下载的用户都可以在页面内一键更新，重启后生效。

## 本地运行

### 1. 下载项目

```bash
git clone https://github.com/Sakura-Yanxi/sakura-question-bank.git
cd sakura-question-bank
```

### 2. 安装依赖

Windows 最简单的方式是直接双击：

```text
run_server.bat
```

它会自动创建 `.venv`、安装依赖并打开浏览器。手动命令行方式如下：

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

Linux / macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. 创建配置

```bash
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

本地自用可以先不配置讲解接口和推送通道。需要公网访问时，建议至少设置：

```env
SAKURA_ADMIN_PASSWORD=换成强密码
SAKURA_AUTH_SECRET=换成一长串随机字符
```

### 4. 启动服务

Windows 推荐双击：

```text
run_server.bat
```

命令行启动：

```bash
python app.py
```

打开：

```text
http://127.0.0.1:8000
```

如果看到 `No module named 'fitz'`，说明跳过了依赖安装；请运行 `run_server.bat`，或先执行 `python -m pip install -r requirements.txt`。

如果双击 `run_server.bat` 时提示 `No matching distribution found for PyMuPDF>=1.24.0`，通常不是网络问题，而是当前项目里的旧 `.venv` 还在使用过低版本或 32 位 Python。新版 `run_server.bat` 会自动检查并重建旧 `.venv`；如果你手里的旧包还没有这个修复，可以先关闭 Sakura 窗口，删除项目目录下的 `.venv` 文件夹，再重新双击 `run_server.bat`。

## 更新项目

页面内更新：

打开“提醒与设置 -> 版本管理”。如果 GitHub Releases 上有新版本，页面会显示“一键更新”。点击后会自动拉取新版代码或下载 Release zip，保留自己的 `data/`、`.env` 和 `.venv`。更新完成后需要关闭并重新启动 Sakura 服务。

脚本更新：

不会 Git 的用户也可以直接用脚本。脚本会自动判断当前目录是不是 Git 仓库：是 Git 就拉取代码，不是 Git 就下载最新 Release zip 并覆盖代码文件。

Windows 可以双击 `update.bat`。

Linux / macOS / 服务器可以运行：

```bash
bash update.sh
```

脚本同样会保留 `data/`、`.env`、`.venv` 和 `docs/software_copyright/`。这是非 Git 用户最省心的升级方式。

如果是在 systemd 托管的服务器上通过页面内“版本管理”更新，更新完成后服务会自动重启并加载新版本；普通本地窗口运行时，更新后仍需要手动关闭并重新打开 Sakura。

如果你手里的旧版本还没有这个轻量更新器，需要先手动升级到包含新 `update.bat` / `update.sh` 的版本一次；之后再更新就可以直接用脚本或页面一键更新。

如果页面和脚本都无法连接 GitHub，再到 [Releases](https://github.com/Sakura-Yanxi/sakura-question-bank/releases) 手动下载最新压缩包。覆盖时不要动自己的 `data/`、`.env` 和 `.venv`。

## 数据与隐私

默认本地保存数据：

- `data/`：题库、数据库、题图、教材页面、练习记录。
- `.env`：访问密码、讲解接口、推送通道等配置。
- `*.log`：运行日志。

这些内容都已加入 `.gitignore`，不要提交到公开仓库。

只有在你主动配置并使用外部讲解接口、视觉接口、天气接口或推送接口时，相关请求才会发往对应服务。上传的 PDF、题库数据库和本地配置不会因为更新代码而被删除。

## 项目结构

```text
.
├── app.py                    # 本地 HTTP 服务入口和历史 Handler 装配层
├── sakura/                   # 后端模块
│   ├── ai/                   # 学习教练、学习档案、老师记忆、模型调用
│   ├── api/                  # 文档和教材运行时流程
│   ├── content/              # PDF、题库、教材、导入、OCR、筛选
│   ├── core/                 # 配置、数据库、路由、安全、HTTP 工具
│   ├── review/               # 错题、每日练习、复盘、提示、导出
│   └── system/               # 备份、迁移、推送、提醒、天气、更新检查
├── static/                   # 前端页面、样式、图片和脚本
│   ├── assets/
│   └── js/
│       ├── ai/
│       ├── content/
│       ├── core/
│       ├── review/
│       └── system/
├── tests/                    # smoke 测试
├── docs/                     # 架构、部署、海报、软著材料
├── deploy/                   # 云端部署补充说明
├── update.bat                # Windows 更新脚本
└── update.sh                 # Linux / macOS 更新脚本
```

当前拆分原则：

- `app.py` 保留启动、路由入口和 Handler 装配。
- 新增复杂逻辑优先放进 `sakura/` 对应模块。
- 前端功能脚本按 `static/js/<domain>/` 分域维护。
- 教材精读、题库导入、备份迁移这类高风险流程不做大范围重写，只做小步可验证优化。

## 部署

详细步骤见：

- [本地到云端部署保姆级教程](docs/本地到云端部署保姆级教程.md)
- [local-to-cloud](deploy/local-to-cloud.md)
- [azure-vm](deploy/azure-vm.md)
- [novm-mini](deploy/novm-mini.md)

公网部署建议：

1. 设置 `SAKURA_ADMIN_PASSWORD` 和 `SAKURA_AUTH_SECRET`。
2. 不要提交 `.env`、`data/`、日志、数据库、上传 PDF 和导出文件。
3. 演示环境可开启 `SAKURA_DEMO_MODE=1`。
4. 使用域名和服务器时，按当地要求确认备案、HTTPS 和防火墙配置。

## 发布新版本

维护者发布新版本时：

1. 修改 `sakura/__init__.py` 里的 `__version__`，例如 `1.0.0` 改为 `1.0.1`。
2. 提交并推送到 `main`。
3. 在 GitHub Releases 创建同名标签，例如 `v1.0.1`。
4. 用户端下次检查版本时会看到更新提示。

版本号按数字段递增：`1.0.1 < 1.1.0 < 2.0.0`。

更详细的发布说明见 [docs/release-update.md](docs/release-update.md)。

## 授权

本仓库采用自定义非商业源码授权，详见 [LICENSE](LICENSE)。

因为包含禁止商用条款，它不是 OSI 意义上的宽松开源协议。这里的“开源”指公开源码供学习、交流、个人使用和非商业二次开发；商业使用必须先获得 Sakura-Yanxi 的明确书面许可。

## 使用边界

可以：

- 学习代码结构和本地部署方式。
- 个人非商业使用。
- 在保留原作者署名和项目来源的前提下进行非商业二次开发。
- 在课程作业、个人作品集或学习记录中展示，但需要说明来源。

请不要：

- 删除原作者信息后重新发布。
- 将项目包装成完全原创项目宣传。
- 将项目、界面或核心功能直接用于商业售卖、付费课程、培训机构产品或闭源商业服务。
- 将界面、结构、文档或核心逻辑直接复制到闭源商业项目。
- 使用相似名称、相似标识或相似页面误导他人认为是原项目官方版本。
- 上传、传播或打包他人享有版权的 PDF、教材、题库、试卷、图片等资料。

署名建议：

```text
Based on Sakura 做题集 by Sakura-Yanxi.
Original repository: https://github.com/Sakura-Yanxi/sakura-question-bank
```

中文可写为：

```text
本项目基于 Sakura-Yanxi 的 Sakura 做题集二次开发。
原项目地址：https://github.com/Sakura-Yanxi/sakura-question-bank
```

## 禁止商用与免责声明

本项目公开展示不等于放弃著作权，也不等于授权商业使用。除非获得 Sakura-Yanxi 的明确书面许可，否则禁止：

- 将本项目、界面、代码、文档、海报或核心功能用于商业售卖、付费课程、培训机构产品、SaaS 服务、代部署收费、闭源商业项目或商业宣传材料。
- 删除、隐藏或弱化原作者署名后重新发布。
- 以相似名称、相似标识、相似页面或相似功能包装成自己的原创商业产品。
- 将本项目作为商业项目的主要功能模块、演示样板或交付物。

免责声明：

- 本项目按现状提供，主要用于个人学习、技术交流和非商业 demo 展示；作者不承诺适用于任何特定考试、课程、机构或商业场景。
- 使用者需要自行负责本地数据、服务器安全、访问密码、API Key、推送 Token、日志和备份文件的保管。
- 使用外部讲解接口、视觉接口、天气接口或推送接口产生的费用、余额不足、限流、封禁、服务中断等问题，由对应服务账号持有人自行承担。
- 智能讲解、计划、反思和教材解读可能存在错误，只能作为学习辅助，不能替代教材、教师、标准答案或专业判断。
- 请勿上传、传播或打包没有授权的 PDF、教材、题库、试卷、图片等资料；由此产生的版权、合规或法律风险由使用者自行承担。
- 公网部署时请遵守所在地网络安全、备案、域名、版权和数据合规要求；因部署、公开访问或二次分发造成的风险由部署者自行承担。

## 支持作者

如果你感觉本工具有用，想请作者喝杯可乐，欢迎自愿打赏。感谢你的支持，也请先照顾好自己的学习数据、API Key 和本地备份。

<p>
  <img src="docs/donation/wechat-pay.jpg" alt="微信支付打赏码" width="260" />
  <img src="docs/donation/alipay.jpg" alt="支付宝打赏码" width="260" />
</p>
