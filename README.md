# Sakura 做题集

Sakura 做题集是一个本地优先的个人学习工作台，用来管理 PDF 题本、模拟卷、教材页面、错题复习、每日练习和阶段复盘。

它的目标很简单：做过的题不浪费，错过的知识点不遗漏，每一次练习都留下证据。

> 当前项目是个人学习 demo。欢迎学习、交流和非商业二次开发；公开展示或二次开发时请保留 Sakura-Yanxi 署名。

## 当前发布

- 当前版本：`v1.0.0`
- 项目地址：[Sakura-Yanxi/sakura-question-bank](https://github.com/Sakura-Yanxi/sakura-question-bank)
- 发布页：[GitHub Releases](https://github.com/Sakura-Yanxi/sakura-question-bank/releases)
- 更新方式：已用 Git 下载的用户运行 `update.bat` / `update.sh`；下载压缩包的用户覆盖代码文件，并保留自己的 `data/` 和 `.env`。

## 主要功能

### 资料导入

- 导入 PDF 做题本，按页保存题图和文本。
- 支持只导入指定页码范围。
- 模拟卷与普通做题本分开管理。
- 教材精读按页保存截图和段落，适合逐段阅读。

### 题库管理

- 按科目、资料、章节、知识点和状态筛选题目。
- 题图可放大查看，也可以微调题目边界。
- 支持修改资料名称、科目和类型。
- 支持按条件导出错题 PDF。

### 错题复习

- 记录未做、做对、做错、半会、需复习等状态。
- 可标记计算失误、公式遗忘、逻辑死角、题意理解偏差等错因。
- 多次复盘不会覆盖旧备注，每次练习都保留记录。
- 复习间隔参考 1 / 3 / 7 / 14 / 30 天节奏。

### 每日练习

- 默认从错题、半会题、到期复习题和薄弱章节里生成练习。
- 可按科目、资料、章节和题量自定义练习范围。
- 练习结果会回写到题库和复习记录。

### 智能讲解与学习助手

这部分是可选能力。不配置外部讲解接口时，资料导入、题库筛选、错题复习、每日练习和导出仍可正常使用。

- 题目讲解：围绕当前题目给出提示、关键步骤和完整解析，适合从“先想一想”过渡到“看懂答案”。
- 变式练习：可基于原题生成换数字、换问法或同知识点练习，帮助确认自己是真的会了，而不是只记住这一题。
- 错因分析：结合做题状态、错因标签和备注，辅助整理计算失误、公式遗忘、审题偏差、知识点不熟等问题。
- 教材精读：可围绕教材当前页、选中段落或扫描页面提问，用来解释定义、公式、例题和推导过程。
- 视觉读取：当教材页没有可复制文本时，可单独配置支持图片读取的接口，让系统尝试从页面截图中理解内容。
- 学习记忆：支持保存个人偏好、常见误区、近期薄弱点和复盘记录，让后续讲解更贴合自己的学习习惯。
- 阶段反思：可根据错题、章节正确率、复习队列和每日练习记录生成周/月复盘，并给出下一步练习建议。
- 使用边界：接口地址、模型名称和密钥都保存在本地 `.env`；只有在主动点击讲解、变式、反思、教材问答或视觉读取时才会调用外部服务。

### 提醒与推送

- 支持企业微信机器人、PushPlus 和 SMTP 邮箱。
- 可设置早晚提醒、天气提醒和每日练习推送。
- 公网部署时可以开启访问密码和登录失败锁定。

## 本地运行

### 1. 下载项目

```bash
git clone https://github.com/Sakura-Yanxi/sakura-question-bank.git
cd sakura-question-bank
```

### 2. 安装依赖

Windows:

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

智能讲解也是可选配置。如果需要题目讲解、变式练习、阶段反思或教材问答，可以在 `.env` 中填写兼容 OpenAI 调用格式的接口：

```env
LLM_API_KEY=你的接口密钥
LLM_BASE_URL=https://你的接口地址/v1
LLM_MODEL=文本讲解模型名称
```

如果还需要读取扫描版教材页或题图截图，可以单独配置视觉读取接口。视觉接口可以和文字讲解接口不同；留空时会默认沿用上面的密钥和地址。

```env
LLM_VISION_MODEL=支持图片读取的模型名称
LLM_VISION_API_KEY=可选，留空则沿用 LLM_API_KEY
LLM_VISION_BASE_URL=可选，留空则沿用 LLM_BASE_URL
```

没有配置这些内容时，页面不会自动调用外部服务；只是不显示或不能使用对应的智能讲解能力。

### 4. 启动服务

```bash
python app.py
```

打开：

```text
http://127.0.0.1:8000
```

Windows 也可以直接双击 `run_server.bat`。

## 更新项目

已用 Git 下载的用户：

```bash
git pull
pip install -r requirements.txt
python app.py
```

Windows 可以双击 `update.bat`。Linux / macOS / 服务器可以运行：

```bash
bash update.sh
```

不用 Git 的用户可以到 [Releases](https://github.com/Sakura-Yanxi/sakura-question-bank/releases) 下载最新压缩包，覆盖代码文件即可。覆盖时不要动自己的 `data/` 和 `.env`。

程序会检查 GitHub 最新发布版本。如果发现更高版本，页面顶部会显示更新提示；它只提示，不会自动覆盖代码。

## 数据与隐私

本项目默认本地保存数据：

- `data/`：题库、题图、教材页面、练习记录。
- `.env`：访问密码、讲解接口、推送通道等配置。
- `*.log`：运行日志。

这些内容都已加入 `.gitignore`，不要提交到公开仓库。

只有在你主动配置并使用外部讲解接口、推送接口或天气接口时，相关请求才会发往对应服务。上传的 PDF、题库数据库和本地配置不会因为更新代码而被删除。

## 项目结构

```text
.
├── app.py                    # 本地服务入口
├── sakura/                   # 后端模块
│   ├── api/                  # 文档和教材运行时逻辑
│   ├── content/              # PDF、题库、教材、导入与分类
│   ├── core/                 # 配置、数据库、路由、安全和 HTTP 工具
│   ├── review/               # 错题、练习、复盘、导出
│   └── system/               # 备份、推送、天气、更新检查
├── static/                   # 前端页面、样式和脚本
├── tests/                    # 烟测
├── docs/
│   └── 本地到云端部署保姆级教程.md
├── deploy/                   # 云端部署补充说明
├── update.bat                # Windows 更新脚本
└── update.sh                 # Linux / macOS 更新脚本
```

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
2. 提交并推送代码。
3. 在 GitHub Releases 创建同名标签，例如 `v1.0.1`。
4. 用户端下次检查版本时会看到更新提示。

版本号按数字段递增：`1.0.1 < 1.1.0 < 2.0.0`。

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
- 上传、传播或打包他人享有版权的 PDF、教材、题库等资料。

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

## 状态

当前版本已经形成个人学习闭环：

```text
PDF / 教材导入
  -> 题库整理
  -> 错题标记
  -> 间隔复习
  -> 每日练习
  -> 阶段反思
  -> 下一轮练习
```

后续会继续优化代码结构、页面体验、导入稳定性和部署流程。
