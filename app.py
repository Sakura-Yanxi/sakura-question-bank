from __future__ import annotations

import json
import hmac
import os
import re
import sqlite3
import shutil
import threading
import traceback
import uuid
from datetime import date, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import urllib.parse

try:
    import fitz
except ModuleNotFoundError as exc:
    if exc.name == "fitz":
        raise SystemExit(
            "\n[Sakura] 缺少依赖 PyMuPDF（模块名 fitz）。\n"
            "Windows 用户请双击 run_server.bat，它会自动创建 .venv 并安装依赖。\n"
            "命令行启动请先运行：python -m pip install -r requirements.txt\n"
            "如果已经创建 .venv，请运行：.\\.venv\\Scripts\\python app.py\n"
        ) from None
    raise
from sakura.content.pdf import (
    crop_image_by_ratio,
    render_page_image,
)
from sakura.ai import client as sakura_ai
from sakura.ai import coach as sakura_coach
from sakura.ai import profile as sakura_profile
from sakura.ai import teacher_memory as sakura_teacher_memory
from sakura.content import classify as sakura_classify
from sakura.content import documents as sakura_documents
from sakura.content import filters as sakura_filters
from sakura.content import models as sakura_models
from sakura.content import ocr as sakura_ocr
from sakura.content import questions as sakura_questions
from sakura.content import textbook as sakura_textbook
from sakura.core import auth as sakura_auth
from sakura.core import config as sakura_config
from sakura.core import db as sakura_db
from sakura.core import http as sakura_http
from sakura.core import parse as sakura_parse
from sakura.core import routes as sakura_routes
from sakura.core import security as sakura_security
from sakura.review import daily as sakura_daily
from sakura.review import export as sakura_export
from sakura.review import hints as sakura_hints
from sakura.review import insights as sakura_insights
from sakura.review import reflection as sakura_reflection
from sakura.review import retention as sakura_retention
from sakura.system import backup as sakura_backup
from sakura.system import email as sakura_email
from sakura.system import migration as sakura_migration
from sakura.system import notifications as sakura_notifications
from sakura.system import practice_pages as sakura_practice_pages
from sakura.system import reminders as sakura_reminders
from sakura.system import scheduler as sakura_scheduler
from sakura.system import settings as sakura_settings
from sakura.system import update as sakura_update
from sakura.system import weather as sakura_weather

from sakura import __version__ as APP_VERSION
from sakura.api import document_runtime as sakura_document_runtime
from sakura.api import textbook_runtime as sakura_textbook_runtime

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
PAGE_DIR = DATA_DIR / "pages"
STATIC_DIR = ROOT / "static"
DB_PATH = DATA_DIR / "gaoshu_demo.sqlite3"

AUTO_RESTART_AFTER_UPDATE_ENV = "SAKURA_AUTO_RESTART_AFTER_UPDATE"
UPDATE_RESTART_DELAY_SECONDS = 2.5

LOCAL_SETTINGS_ENV_KEYS = {
    "APP_PUBLIC_URL",
    "EMAIL_ENABLED",
    "EMAIL_FROM",
    "EMAIL_FROM_NAME",
    "EMAIL_HOST",
    "EMAIL_PASSWORD",
    "EMAIL_PORT",
    "EMAIL_TO",
    "EMAIL_USE_SSL",
    "EMAIL_USE_STARTTLS",
    "EMAIL_USER",
    "LLM_API_KEY",
    "LLM_BASE_URL",
    "LLM_MODEL",
    "LLM_VISION_API_KEY",
    "LLM_VISION_BASE_URL",
    "LLM_VISION_MODEL",
    "PUSHPLUS_TOKEN",
    "REMIND_CHECKIN_MODE",
    "REMIND_DAILY_LIMIT",
    "REMIND_DAILY_SCOPE",
    "REMIND_MORNING_ON",
    "REMIND_MORNING_TIME",
    "REMIND_NIGHT_ON",
    "REMIND_NIGHT_TIME",
    "REMIND_SEND_PDF",
    "REMIND_WEATHER_ON",
    "REMIND_WEATHER_TIME",
    "SAKURA_HOST",
    "WEATHER_CITY",
    "WEWORK_BOT_WEBHOOK",
}

sakura_config.load_local_env(ROOT, override_keys=LOCAL_SETTINGS_ENV_KEYS)

PORT = int(os.getenv("PORT", "8000"))
SAKURA_HOST = os.getenv("SAKURA_HOST", "127.0.0.1").strip() or "127.0.0.1"
ADMIN_PASSWORD = sakura_auth.clean_auth_value(os.getenv("SAKURA_ADMIN_PASSWORD") or os.getenv("APP_PASSWORD") or "")
AUTH_SECRET = sakura_auth.clean_auth_value(os.getenv("SAKURA_AUTH_SECRET") or os.getenv("APP_SECRET") or "")
AUTH_COOKIE_NAME = "sakura_session"
AUTH_MAX_AGE_SECONDS = 60 * 60 * 24 * 14
DEMO_MODE = os.getenv("SAKURA_DEMO_MODE", "0").strip().lower() in {"1", "true", "yes", "on"}

# === AI 接口（OpenAI 兼容）===
# 默认接入小米 MiMo 开放平台（https://platform.xiaomimimo.com 申请 Key）。
# 也可用环境变量切换到 DeepSeek 或任意 OpenAI 兼容端点，无需改代码。
# 密钥优先级：LLM_API_KEY > MIMO_API_KEY > DEEPSEEK_API_KEY（向后兼容旧配置）。
LLM_API_KEY = os.getenv("LLM_API_KEY") or os.getenv("MIMO_API_KEY") or os.getenv("DEEPSEEK_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL") or os.getenv("DEEPSEEK_BASE_URL") or "https://api.xiaomimimo.com/v1"
LLM_MODEL = os.getenv("LLM_MODEL") or os.getenv("DEEPSEEK_MODEL") or "mimo-v2.5-pro"
# Optional multimodal (vision) model for scanned textbook pages that have no text layer.
# Leave the model empty to disable image-based reading. Must accept image input
# (e.g. qwen-vl-max, gpt-4o, gpt-4o-mini, doubao-vision).
# The vision provider can be DIFFERENT from the text model (e.g. text=DeepSeek which has no
# vision, vision=Qwen-VL): it has its own key/base_url, each falling back to the text LLM's
# value when left blank (so a same-provider setup only needs to fill the model name).
LLM_VISION_MODEL = os.getenv("LLM_VISION_MODEL", "").strip()
LLM_VISION_API_KEY = os.getenv("LLM_VISION_API_KEY", "").strip()
LLM_VISION_BASE_URL = os.getenv("LLM_VISION_BASE_URL", "").strip()

# === 微信推送（PushPlus）===
# 在 https://www.pushplus.plus 用微信扫码登录，复制 token 后设环境变量 PUSHPLUS_TOKEN。
PUSHPLUS_TOKEN = os.getenv("PUSHPLUS_TOKEN", "")
WEWORK_BOT_WEBHOOK = os.getenv("WEWORK_BOT_WEBHOOK", "")
EMAIL_ENABLED = os.getenv("EMAIL_ENABLED", "0")
EMAIL_HOST = os.getenv("EMAIL_HOST", "")
EMAIL_PORT = os.getenv("EMAIL_PORT", "465")
EMAIL_USE_SSL = os.getenv("EMAIL_USE_SSL", "1")
EMAIL_USE_STARTTLS = os.getenv("EMAIL_USE_STARTTLS", "0")
EMAIL_USER = os.getenv("EMAIL_USER", "")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "") or os.getenv("EMAIL_AUTH_CODE", "")
EMAIL_TO = os.getenv("EMAIL_TO", "")
EMAIL_FROM = os.getenv("EMAIL_FROM", "")
EMAIL_FROM_NAME = os.getenv("EMAIL_FROM_NAME", "Sakura 做题集")
# 推送正文里的“打开做题集”链接（部署到公网后改成你的域名/IP）
APP_PUBLIC_URL = os.getenv("APP_PUBLIC_URL", "http://127.0.0.1:8000")
WEATHER_CITY = os.getenv("WEATHER_CITY", "北京")
REMIND_MORNING_ON = os.getenv("REMIND_MORNING_ON", "1")
REMIND_MORNING_TIME = os.getenv("REMIND_MORNING_TIME", "10:00")
REMIND_NIGHT_ON = os.getenv("REMIND_NIGHT_ON", "1")
REMIND_NIGHT_TIME = os.getenv("REMIND_NIGHT_TIME", "20:00")
REMIND_WEATHER_ON = os.getenv("REMIND_WEATHER_ON", "1")
REMIND_WEATHER_TIME = os.getenv("REMIND_WEATHER_TIME", "22:30")
REMIND_CHECKIN_MODE = sakura_reminders.normalize_checkin_mode(os.getenv("REMIND_CHECKIN_MODE", "wework"))
REMIND_DAILY_SCOPE = sakura_reminders.normalize_daily_scope(os.getenv("REMIND_DAILY_SCOPE", "due"))
REMIND_DAILY_LIMIT = sakura_reminders.normalize_daily_limit(os.getenv("REMIND_DAILY_LIMIT", "20"))
REMIND_SEND_PDF = sakura_reminders.normalize_onoff(os.getenv("REMIND_SEND_PDF", "1"))
INTERNAL_SCHEDULER_ENABLED = os.getenv("SAKURA_INTERNAL_SCHEDULER", "1").strip().lower() not in {"0", "false", "no", "off"}
# GitHub "owner/repo" used for release checks and one-click updates. Set this to your fork/repo.
UPDATE_REPO = os.getenv("SAKURA_UPDATE_REPO", "Sakura-Yanxi/sakura-question-bank").strip()


def env_int(name: str, default: int, minimum: int | None = None) -> int:
    try:
        value = int(str(os.getenv(name, str(default))).strip())
    except (TypeError, ValueError):
        value = default
    if minimum is not None:
        value = max(minimum, value)
    return value


# Cap at 50s as well as a 10s floor: reminders match an exact HH:MM, so a poll gap >60s could
# straddle and skip a whole target minute. <=50s guarantees at least one poll per minute.
SCHEDULER_POLL_SECONDS = min(env_int("SAKURA_SCHEDULER_POLL_SECONDS", 30, minimum=10), 50)
_scheduler_started = False
_scheduler_lock = threading.Lock()
DEFAULT_SUBJECT = "未分类"
DEFAULT_CATEGORY = "待归类"
DEFAULT_CHAPTER = "未识别章节"
DEFAULT_DOCUMENT_KIND = "做题本"
MOCK_PAPER_KIND = "模拟卷"
DOCUMENT_KINDS = [DEFAULT_DOCUMENT_KIND, MOCK_PAPER_KIND]
MOCK_PAPER_CHAPTER = "整卷"
REVIEW_INTERVAL_DAYS = sakura_retention.REVIEW_INTERVAL_DAYS
META_TAGS = sakura_retention.META_TAGS
WRONGISH_STATUSES = sakura_retention.WRONGISH_STATUSES
EXAM_DATE = date(2026, 12, 20)

# === 学习档案 / 复习规划模型 ===
# L1 洞察的错因枚举（固定 taxonomy，构成严密结构的一部分）
ROOT_CAUSES = ["概念缺失", "计算失误", "方法不会", "审题偏差"]
# 元认知标签 -> 错因枚举的映射（本地 fallback 抽取洞察时用）
META_TAG_TO_ROOT_CAUSE = {
    "计算失误": "计算失误",
    "公式遗忘": "概念缺失",
    "逻辑死角": "方法不会",
    "题意理解偏差": "审题偏差",
}
# 错因 -> 训练处方文案
ROOT_CAUSE_PRESCRIPTIONS = {
    "概念缺失": "回到该知识点的定义与适用条件，先建公式默写卡，默写后再做题。",
    "计算失误": "限时分步演算，每一步写出中间结果，规范草稿，做完回查关键变形。",
    "方法不会": "精读 2-3 道同类范题解析后闭卷重做，并把解题路线讲给自己听。",
    "审题偏差": "审题时圈出关键词，把『已知/求解/隐含条件』分三行写清再动笔。",
}
STUDY_MINUTES_PER_QUESTION = 6
DEFAULT_DAILY_MINUTES = 60
PROFILE_STALE_DAYS = 7
COACH_STATE_ID = "singleton"

# 晚间未打卡时的"狠老师型"激励（严厉但不人身攻击；可自行增改）
NAG_MESSAGES = [
    "今天又打算放弃？考场上可没有重来。现在去做几道。",
    "倒计时还在走，你却停下了。明天的你，会恨今天偷懒的你。",
    "你报名的时候不是这个态度。错题本在等你，别让今天白过。",
    "一道没碰？这就是你想要的结果吗？现在还不晚，去做。",
    "借口谁都会找，分数不会陪你演戏。打开做题集，至少做 3 道。",
    "今天的懒，都会变成考场上的慌。别等到那天才后悔。",
    "你不是没时间，是没把它当回事。现在就去补上今天的份。",
]

MOTIVATIONAL_QUOTES = [
    "You are more than what you have become.",
    "You are more than what you have become. Remember yourself.",
    "每一个不曾起舞的日子，都是对生命的辜负。",
    "当你觉得为时已晚的时候，恰恰是最早的时候。",
    "星光不问赶路人，时光不负有心人。",
    "长风破浪会有时，直挂云帆济沧海。",
    "宝剑锋从磨砺出，梅花香自苦寒来。",
    "The only way to do great work is to love what you do.",
    "It does not matter how slowly you go as long as you do not stop.",
    "千里之行，始于足下。",
    "世上无难事，只要肯登攀。",
    "Believe you can and you are halfway there.",
    "自律给我自由。",
    "路漫漫其修远兮，吾将上下而求索。",
    "What we do in life echoes in eternity.",
]

KNOWLEDGE_DEPENDENCIES = {
    "微分方程": ["不定积分", "导数与微分"],
    "重积分": ["定积分及其应用", "不定积分"],
    "多元函数微分学": ["导数与微分", "函数、极限与连续"],
    "无穷级数": ["函数、极限与连续", "导数与微分"],
    "导数应用": ["导数与微分", "函数、极限与连续"],
    "定积分及其应用": ["不定积分", "函数、极限与连续"],
    "概率统计": ["函数、极限与连续"],
}

KEYWORD_RULES = [
    ("无穷级数", ["级数", "收敛", "发散", "收敛半径", "幂级数", "泰勒", "麦克劳林", "傅里叶", "sum", "∑"]),
    ("函数、极限与连续", ["极限", "连续", "无穷小", "等价", "洛必达", "lim", "趋于"]),
    ("导数与微分", ["导数", "微分", "求导", "偏导", "可导"]),
    ("微分中值定理", ["中值定理", "罗尔", "拉格朗日", "柯西"]),
    ("导数应用", ["单调", "极值", "最值", "凹凸", "拐点", "渐近线"]),
    ("不定积分", ["不定积分", "原函数", "换元积分", "分部积分"]),
    ("定积分及其应用", ["定积分", "面积", "体积", "弧长", "反常积分"]),
    ("多元函数微分学", ["多元", "全微分", "方向导数", "梯度", "条件极值"]),
    ("重积分", ["二重积分", "三重积分", "极坐标", "柱坐标", "球坐标"]),
    ("微分方程", ["微分方程", "通解", "特解", "初值", "齐次方程"]),
    ("向量代数与空间解析几何", ["向量", "平面", "直线", "曲面", "空间", "法向量"]),
    ("线性代数", ["矩阵", "行列式", "特征值", "特征向量", "线性相关", "线性无关", "秩", "向量组"]),
    ("概率统计", ["概率", "随机变量", "分布函数", "密度函数", "期望", "方差", "假设检验", "置信区间"]),
    ("英语阅读", ["reading", "passage", "paragraph", "comprehension", "main idea"]),
    ("英语写作", ["essay", "writing", "translation", "作文", "翻译"]),
    ("政治理论", ["马克思", "毛泽东", "新时代", "中国特色社会主义", "哲学", "史纲"]),
]


def ensure_dirs() -> None:
    sakura_db.ensure_dirs((DATA_DIR, UPLOAD_DIR, PAGE_DIR, STATIC_DIR))


def connect() -> sqlite3.Connection:
    return sakura_db.connect(DB_PATH)


def init_db() -> None:
    sakura_db.init_db(
        db_path=DB_PATH,
        dirs=(DATA_DIR, UPLOAD_DIR, PAGE_DIR, STATIC_DIR),
        default_subject=DEFAULT_SUBJECT,
        default_document_kind=DEFAULT_DOCUMENT_KIND,
        default_chapter=DEFAULT_CHAPTER,
    )


def migrate_db(conn: sqlite3.Connection) -> None:
    sakura_db.migrate_db(
        conn,
        default_subject=DEFAULT_SUBJECT,
        default_document_kind=DEFAULT_DOCUMENT_KIND,
        default_chapter=DEFAULT_CHAPTER,
    )


def to_public_path(path: str | Path) -> str:
    return sakura_http.to_public_path(path, page_dir=PAGE_DIR, static_dir=STATIC_DIR)


def public_file_base_for_path(path: str) -> Path | None:
    return sakura_http.public_file_base_for_path(path, page_dir=PAGE_DIR, static_dir=STATIC_DIR)


def extract_question_no(text: str) -> str:
    return sakura_models.extract_question_no(text)


def row_to_dict(row: sqlite3.Row) -> dict:
    return sakura_models.row_to_dict(
        row,
        to_public_path=to_public_path,
        normalize_document_kind=normalize_document_kind,
        normalize_meta_tags=normalize_meta_tags,
    )


def question_detail_to_dict(conn: sqlite3.Connection, row: sqlite3.Row) -> dict:
    return sakura_models.question_detail_to_dict(
        conn,
        row,
        row_to_dict=row_to_dict,
        load_question_review_notes=sakura_questions.load_question_review_notes,
    )


def document_to_dict(row: sqlite3.Row) -> dict:
    return sakura_models.document_to_dict(row, normalize_document_kind)


def normalize_document_kind(value: str | None) -> str:
    return sakura_models.normalize_document_kind(
        value,
        normalize_label=normalize_label,
        default_document_kind=DEFAULT_DOCUMENT_KIND,
        mock_paper_kind=MOCK_PAPER_KIND,
        document_kinds=DOCUMENT_KINDS,
    )


def schedule_for_status(current: sqlite3.Row | dict | None, status: str, now: datetime | None = None) -> dict:
    return sakura_retention.schedule_for_status(dict(current) if current else None, status, now)


def get_filter_options(conn: sqlite3.Connection) -> dict:
    return sakura_filters.get_filter_options(conn)


def build_question_filters(query: dict, keys: tuple[str, ...]) -> tuple[str, list[str]]:
    return sakura_filters.build_question_filters(query, keys)


def get_scoped_filter_options(conn: sqlite3.Connection, query: dict) -> dict:
    return sakura_filters.get_scoped_filter_options(conn, query)


def json_response(handler: BaseHTTPRequestHandler, payload: dict | list, status: int = 200) -> None:
    sakura_http.json_response(handler, payload, status)


def text_response(handler: BaseHTTPRequestHandler, text: str, status: int = 200, content_type: str = "text/plain") -> None:
    sakura_http.text_response(handler, text, status, content_type)


def redirect_response(handler: BaseHTTPRequestHandler, location: str, status: int = HTTPStatus.FOUND) -> None:
    sakura_http.redirect_response(handler, location, status)


def _env_flag(value: str | None) -> bool | None:
    normalized = (value or "").strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return None


def _running_under_systemd() -> bool:
    if os.name == "nt":
        return False
    configured = _env_flag(os.getenv(AUTO_RESTART_AFTER_UPDATE_ENV))
    if configured is not None:
        return configured
    if os.getenv("INVOCATION_ID") or os.getenv("JOURNAL_STREAM"):
        return True
    try:
        parent_comm = Path(f"/proc/{os.getppid()}/comm").read_text(encoding="utf-8").strip()
    except OSError:
        return False
    return parent_comm == "systemd"


def schedule_restart_after_update() -> dict:
    """Exit after the response so process supervisors can start the updated code."""
    if not _running_under_systemd():
        return {
            "restart_scheduled": False,
            "restart_mode": "manual",
            "restart_message": "更新已完成；请重新启动 Sakura 服务后生效。",
        }

    def _exit_for_supervisor_restart() -> None:
        print("[sakura update] exiting current process so systemd can start the updated code.", flush=True)
        os._exit(0)

    timer = threading.Timer(UPDATE_RESTART_DELAY_SECONDS, _exit_for_supervisor_restart)
    timer.daemon = True
    timer.start()
    return {
        "restart_scheduled": True,
        "restart_mode": "systemd",
        "restart_delay_seconds": UPDATE_RESTART_DELAY_SECONDS,
        "restart_message": "更新已完成；服务器正在自动重启 Sakura 服务。",
    }


def demo_mode_enabled() -> bool:
    return DEMO_MODE


def demo_mode_response(handler: BaseHTTPRequestHandler) -> None:
    return json_response(
        handler,
        {
            "error": "Demo mode is read-only. Mutating actions are disabled on this public showcase.",
            "demo_mode": True,
        },
        HTTPStatus.FORBIDDEN,
    )


def auth_enabled() -> bool:
    return sakura_auth.auth_enabled(ADMIN_PASSWORD)


def auth_secret() -> str:
    return sakura_auth.auth_secret(ADMIN_PASSWORD, AUTH_SECRET)


def sign_session(payload: str) -> str:
    return sakura_auth.sign_session(payload, admin_password=ADMIN_PASSWORD, auth_secret_value=AUTH_SECRET)


def make_session_token() -> str:
    return sakura_auth.make_session_token(
        admin_password=ADMIN_PASSWORD,
        auth_secret_value=AUTH_SECRET,
        max_age_seconds=AUTH_MAX_AGE_SECONDS,
    )


def verify_session_token(token: str) -> bool:
    return sakura_auth.verify_session_token(token, admin_password=ADMIN_PASSWORD, auth_secret_value=AUTH_SECRET)


def login_page(error: str = "") -> str:
    return sakura_auth.login_page(error)


def update_security_runtime_settings(admin_password: str) -> dict:
    updates = sakura_security.security_runtime_updates(admin_password)
    apply_runtime_env_updates(
        updates,
        {
            "SAKURA_ADMIN_PASSWORD": "ADMIN_PASSWORD",
            "SAKURA_AUTH_SECRET": "AUTH_SECRET",
        },
    )
    return sakura_security.security_settings_view(ADMIN_PASSWORD)


def send_login_security_alert(ip: str, user_agent_value: str, result: dict) -> dict:
    title, content = sakura_security.login_security_alert_payload(ip, user_agent_value, result)
    preferred = sakura_reminders.normalize_checkin_mode(REMIND_CHECKIN_MODE)
    if preferred == "local":
        return send_notification_all_channels(title, content)
    result_primary = send_notification(title, content, preferred)
    if result_primary.get("ok"):
        return result_primary
    result_primary["fallback"] = send_notification_all_channels(title, content)
    return result_primary


def classify_by_rules(text: str) -> tuple[str, str, str]:
    return sakura_classify.classify_by_rules(text, KEYWORD_RULES, DEFAULT_CATEGORY)


def normalize_label(value: str, fallback: str) -> str:
    return sakura_classify.normalize_label(value, fallback)


def normalize_chapter(value: str, fallback: str = DEFAULT_CHAPTER) -> str:
    return sakura_classify.normalize_chapter(value, fallback)


def strip_chapter_noise(value: str) -> str:
    return sakura_classify.strip_chapter_noise(value)


def dedupe_repeated_phrase(value: str) -> str:
    return sakura_classify.dedupe_repeated_phrase(value)


def looks_like_chapter(text: str) -> bool:
    return sakura_classify.looks_like_chapter(text)


def extract_chapter_from_page(page: fitz.Page, text: str) -> str:
    return sakura_classify.extract_chapter_from_page(page, text, DEFAULT_CHAPTER)


def new_chapter_state() -> sakura_classify.ChapterCarryState:
    return sakura_classify.ChapterCarryState(DEFAULT_CHAPTER)


def llm_enabled() -> bool:
    """是否已配置 AI 接口密钥。"""
    return bool(LLM_API_KEY)


def llm_settings_view() -> dict:
    return sakura_settings.llm_settings_view(
        LLM_API_KEY,
        LLM_BASE_URL,
        LLM_MODEL,
        LLM_VISION_MODEL,
        LLM_VISION_API_KEY,
        LLM_VISION_BASE_URL,
    )


def vision_api_key() -> str:
    return LLM_VISION_API_KEY or LLM_API_KEY


def vision_base_url() -> str:
    return LLM_VISION_BASE_URL or LLM_BASE_URL


def vision_enabled() -> bool:
    return bool(LLM_VISION_MODEL and vision_api_key())


def call_llm_vision(messages: list[dict], temperature: float = 0.3) -> str:
    """Vision-capable chat call (image + text) using the configured multimodal model.
    The vision provider's key/base_url are independent from the text model's, falling back to
    the text model's values when left blank."""
    return sakura_ai.call_llm(vision_api_key(), vision_base_url(), LLM_VISION_MODEL, messages, temperature)


def current_email_settings() -> sakura_email.EmailSettings:
    return sakura_email.EmailSettings(
        enabled=EMAIL_ENABLED,
        host=EMAIL_HOST,
        port=EMAIL_PORT,
        use_ssl=EMAIL_USE_SSL,
        use_starttls=EMAIL_USE_STARTTLS,
        user=EMAIL_USER,
        password=EMAIL_PASSWORD,
        to=EMAIL_TO,
        from_email=EMAIL_FROM,
        from_name=EMAIL_FROM_NAME,
    )


def notification_channels_configured(checkin_mode: str | None = None) -> bool:
    mode = sakura_reminders.normalize_checkin_mode(checkin_mode or REMIND_CHECKIN_MODE)
    if mode == "wework":
        return bool(WEWORK_BOT_WEBHOOK)
    if mode == "pushplus":
        return bool(PUSHPLUS_TOKEN)
    if mode == "email":
        return sakura_email.is_configured(current_email_settings())
    return bool(
        WEWORK_BOT_WEBHOOK
        or PUSHPLUS_TOKEN
        or sakura_email.is_configured(current_email_settings())
    )


def notification_settings_view() -> dict:
    return sakura_settings.notification_settings_view(
        WEWORK_BOT_WEBHOOK,
        PUSHPLUS_TOKEN,
        APP_PUBLIC_URL,
        sakura_email.settings_public_view(current_email_settings()),
    )


def apply_runtime_env_updates(updates: dict[str, str], global_aliases: dict[str, str] | None = None) -> None:
    global_aliases = global_aliases or {}
    for key, value in updates.items():
        globals()[global_aliases.get(key, key)] = value
        os.environ[key] = value
    if updates:
        sakura_config.write_local_env(ROOT, updates)


def update_llm_runtime_settings(
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    vision_model: str | None = None,
    vision_api_key: str | None = None,
    vision_base_url: str | None = None,
) -> dict:
    updates = sakura_settings.llm_runtime_updates(
        api_key=api_key,
        base_url=base_url,
        model=model,
        vision_model=vision_model,
        vision_api_key=vision_api_key,
        vision_base_url=vision_base_url,
    )
    apply_runtime_env_updates(updates)
    return llm_settings_view()


def update_notification_runtime_settings(
    wework_webhook: str | None = None,
    pushplus_token: str | None = None,
    app_public_url: str | None = None,
    email_enabled: str | None = None,
    email_host: str | None = None,
    email_port: str | None = None,
    email_use_ssl: str | None = None,
    email_use_starttls: str | None = None,
    email_user: str | None = None,
    email_password: str | None = None,
    email_to: str | None = None,
    email_from: str | None = None,
    email_from_name: str | None = None,
) -> dict:
    updates = sakura_settings.notification_runtime_updates(
        wework_webhook=wework_webhook,
        pushplus_token=pushplus_token,
        app_public_url=app_public_url,
        email_enabled=email_enabled,
        email_host=email_host,
        email_port=email_port,
        email_use_ssl=email_use_ssl,
        email_use_starttls=email_use_starttls,
        email_user=email_user,
        email_password=email_password,
        email_to=email_to,
        email_from=email_from,
        email_from_name=email_from_name,
        current_email_port=EMAIL_PORT,
        current_email_use_ssl=EMAIL_USE_SSL,
        current_email_use_starttls=EMAIL_USE_STARTTLS,
    )
    apply_runtime_env_updates(updates)
    return notification_settings_view()


def normalize_public_url(value: str) -> str:
    return sakura_settings.normalize_public_url(value)


def current_reminder_settings() -> sakura_reminders.ReminderSettings:
    return sakura_settings.reminder_settings_from_values(
        morning_on=REMIND_MORNING_ON,
        morning_time=REMIND_MORNING_TIME,
        night_on=REMIND_NIGHT_ON,
        night_time=REMIND_NIGHT_TIME,
        weather_on=REMIND_WEATHER_ON,
        weather_time=REMIND_WEATHER_TIME,
        checkin_mode=REMIND_CHECKIN_MODE,
        daily_scope=REMIND_DAILY_SCOPE,
        daily_limit=REMIND_DAILY_LIMIT,
        send_pdf=REMIND_SEND_PDF,
    )


def reminder_settings_view(cron_status: dict | None = None) -> dict:
    return sakura_settings.reminder_settings_view(
        current_reminder_settings(),
        cron_status,
        scheduler={
            "enabled": INTERNAL_SCHEDULER_ENABLED,
            "poll_seconds": SCHEDULER_POLL_SECONDS,
            "started": _scheduler_started,
            "platform": os.name,
        },
    )


def update_reminder_runtime_settings(payload: dict) -> dict:
    settings, updates = sakura_settings.reminder_runtime_updates(current_reminder_settings(), payload)
    apply_runtime_env_updates(updates)
    cron_status = sakura_reminders.install_crontab(settings, ROOT, DATA_DIR)
    return settings.as_payload(cron_status)


def call_llm(prompt: str, temperature: float = 0.3) -> str:
    """统一的 OpenAI 兼容调用入口（默认小米 MiMo）。失败时抛异常，由调用方决定 fallback。"""
    return sakura_ai.call_llm(
        LLM_API_KEY,
        LLM_BASE_URL,
        LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
    )


def call_llm_messages(messages: list[dict], temperature: float = 0.3) -> str:
    """OpenAI-compatible chat call used by the API test panel."""
    return sakura_ai.call_llm(LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, messages, temperature)


def classify_question_locally(text: str, subject_hint: str = "", chapter_hint: str = "", document_kind: str = DEFAULT_DOCUMENT_KIND) -> dict:
    return sakura_classify.classify_question_locally(
        text,
        subject_hint=subject_hint,
        chapter_hint=chapter_hint,
        document_kind=document_kind,
        keyword_rules=KEYWORD_RULES,
        default_subject=DEFAULT_SUBJECT,
        default_category=DEFAULT_CATEGORY,
        default_chapter=DEFAULT_CHAPTER,
        default_document_kind=DEFAULT_DOCUMENT_KIND,
        mock_paper_kind=MOCK_PAPER_KIND,
    )


# ==========================================================================
# L1 洞察层：分析错题时抽取结构化证据，沉淀进学习者记忆
# ==========================================================================
def guess_root_cause(question: dict) -> str:
    return sakura_insights.guess_root_cause(
        question,
        normalize_meta_tags=normalize_meta_tags,
        meta_tag_to_root_cause=META_TAG_TO_ROOT_CAUSE,
    )


def local_insight(question: dict) -> dict:
    return sakura_insights.local_insight(
        question,
        default_category=DEFAULT_CATEGORY,
        default_chapter=DEFAULT_CHAPTER,
        knowledge_dependencies=KNOWLEDGE_DEPENDENCIES,
        normalize_meta_tags=normalize_meta_tags,
        meta_tag_to_root_cause=META_TAG_TO_ROOT_CAUSE,
    )


def normalize_insight(raw: dict, question: dict) -> dict:
    return sakura_insights.normalize_insight(
        raw,
        question,
        root_causes=ROOT_CAUSES,
        default_category=DEFAULT_CATEGORY,
        default_chapter=DEFAULT_CHAPTER,
        knowledge_dependencies=KNOWLEDGE_DEPENDENCIES,
        normalize_meta_tags=normalize_meta_tags,
        meta_tag_to_root_cause=META_TAG_TO_ROOT_CAUSE,
    )


def analyze_and_extract_with_ai(question: dict) -> tuple[str, dict]:
    return sakura_insights.analyze_and_extract(
        question,
        llm_enabled=llm_enabled(),
        call_llm=call_llm,
        extract_json_block=sakura_ai.extract_json_block,
        default_subject=DEFAULT_SUBJECT,
        default_category=DEFAULT_CATEGORY,
        default_chapter=DEFAULT_CHAPTER,
        root_causes=ROOT_CAUSES,
        knowledge_dependencies=KNOWLEDGE_DEPENDENCIES,
        normalize_meta_tags=normalize_meta_tags,
        meta_tag_to_root_cause=META_TAG_TO_ROOT_CAUSE,
    )


def upsert_insight(conn: sqlite3.Connection, question: dict, insight: dict) -> None:
    sakura_insights.upsert_insight(conn, question, insight, default_subject=DEFAULT_SUBJECT)


def infer_concept_hint(question: dict) -> str:
    return sakura_hints.infer_concept_hint(question, default_category=DEFAULT_CATEGORY)


def infer_key_step_hint(question: dict) -> str:
    return sakura_hints.infer_key_step_hint(question)


def generate_hint_with_ai(question: dict, level: int) -> str:
    return sakura_hints.generate_hint(
        question,
        level,
        llm_enabled=llm_enabled(),
        call_llm=call_llm,
        default_subject=DEFAULT_SUBJECT,
        default_category=DEFAULT_CATEGORY,
        default_chapter=DEFAULT_CHAPTER,
        default_document_kind=DEFAULT_DOCUMENT_KIND,
    )


def vision_ocr_question_text(question: dict) -> str:
    if not vision_enabled():
        return ""
    data_url = sakura_ai.image_to_data_url(question.get("image_path") or "")
    if not data_url:
        return ""
    messages = [
        {
            "role": "system",
            "content": (
                "你是题目图片 OCR 工具。请只转写图片中的题干、选项、条件和公式，"
                "不要解题，不要补充图片外内容，不要输出说明。"
            ),
        },
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "请识别这张题目图片中的原始题目文字。只输出题目文字。"},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        },
    ]
    text = call_llm_vision(messages, temperature=0.05).strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:text|markdown)?\s*|\s*```$", "", text, flags=re.S).strip()
    if any(marker in text for marker in ("无法识别", "不能识别", "看不清", "没有题目")):
        return ""
    return text


def can_use_vision_ocr_for_question(question: dict) -> bool:
    image_path = question.get("image_path") or ""
    return bool(vision_enabled() and image_path and Path(image_path).is_file())


def prepare_question_for_full_solution(
    conn: sqlite3.Connection,
    q_id: str,
    question: dict,
    *,
    allow_vision_ocr: bool = False,
) -> dict:
    local_text = sakura_ocr.image_ocr_text(question.get("image_path") or "", min_score=0.35).strip()
    if sakura_hints.has_question_statement_text(local_text):
        enriched = dict(question)
        enriched["ocr_text"] = local_text
        conn.execute("UPDATE questions SET ocr_text = ? WHERE id = ?", (local_text, q_id))
        return enriched

    if sakura_hints.solution_question_text(question):
        return question

    if allow_vision_ocr:
        try:
            local_text = vision_ocr_question_text(question)
        except Exception as exc:
            enriched = dict(question)
            enriched["_vision_ocr_error"] = str(exc)
            return enriched
    if not sakura_hints.has_question_statement_text(local_text):
        return question

    enriched = dict(question)
    enriched["ocr_text"] = local_text
    conn.execute("UPDATE questions SET ocr_text = ? WHERE id = ?", (local_text, q_id))
    return enriched


def full_solution_hint_response(
    conn: sqlite3.Connection,
    q_id: str,
    question: dict,
    *,
    allow_vision_ocr: bool = False,
) -> dict:
    prepared = prepare_question_for_full_solution(
        conn,
        q_id,
        question,
        allow_vision_ocr=allow_vision_ocr,
    )
    if prepared.get("_vision_ocr_error"):
        hint = sakura_hints.full_solution_vision_error_message(prepared["_vision_ocr_error"])
        return {"level": 3, "hint": hint, "needs_vision_confirm": False}

    if not sakura_hints.solution_question_text(prepared):
        vision_available = can_use_vision_ocr_for_question(question)
        if allow_vision_ocr:
            hint = sakura_hints.full_solution_vision_missing_text_message()
        else:
            hint = sakura_hints.full_solution_missing_text_message()
        response = {
            "level": 3,
            "hint": hint,
            "needs_vision_confirm": bool(vision_available and not allow_vision_ocr),
            "vision_available": vision_available,
        }
        if response["needs_vision_confirm"]:
            response["vision_confirm_message"] = (
                "本地 OCR 没有识别出题干。是否调用视觉 API 识别这张题图？\n\n"
                "确认后会使用你配置的视觉模型，可能产生接口费用。"
            )
        return response

    return {
        "level": 3,
        "hint": generate_hint_with_ai(prepared, 3),
        "needs_vision_confirm": False,
    }


def generate_variations_with_ai(question: dict) -> str:
    return sakura_hints.generate_variations(
        question,
        llm_enabled=llm_enabled(),
        call_llm=call_llm,
        default_subject=DEFAULT_SUBJECT,
        default_category=DEFAULT_CATEGORY,
        default_chapter=DEFAULT_CHAPTER,
        default_document_kind=DEFAULT_DOCUMENT_KIND,
    )


def normalize_meta_tags(value) -> list[str]:
    return sakura_retention.normalize_meta_tags(value)


def question_payload(row: sqlite3.Row) -> dict:
    return sakura_models.question_payload(
        row,
        normalize_document_kind=normalize_document_kind,
        normalize_meta_tags=normalize_meta_tags,
    )


def get_meta_tag_stats(conn: sqlite3.Connection, doc_id: str | None = None) -> list[dict]:
    return sakura_models.get_meta_tag_stats(
        conn,
        meta_tags=META_TAGS,
        normalize_meta_tags=normalize_meta_tags,
        doc_id=doc_id,
    )


def weak_chapter_dependencies(conn: sqlite3.Connection) -> dict[str, list[str]]:
    return sakura_coach.weak_chapter_dependencies(
        conn,
        knowledge_dependencies=KNOWLEDGE_DEPENDENCIES,
        default_subject=DEFAULT_SUBJECT,
        default_document_kind=DEFAULT_DOCUMENT_KIND,
    )


def find_foundation_questions(conn: sqlite3.Connection, subject: str, dependency_categories: list[str], exclude_ids: set[str]) -> list[dict]:
    return sakura_coach.find_foundation_questions(
        conn,
        subject,
        dependency_categories,
        exclude_ids,
        row_to_dict=row_to_dict,
    )


# ==========================================================================
# Learner profile synthesis
# ==========================================================================
# Learner profile synthesis: app.py keeps the legacy public names, while the
# data aggregation, local merge and optional AI polish live in sakura_profile.
# ==========================================================================
def gather_knowledge_stats(conn: sqlite3.Connection, scope: str = "__all__") -> list[dict]:
    return sakura_profile.gather_knowledge_stats(conn, scope)


def load_insight_rows(conn: sqlite3.Connection, scope: str = "__all__") -> list[dict]:
    return sakura_profile.load_insight_rows(conn, scope)


def load_latest_profile(conn: sqlite3.Connection, scope: str = "__all__") -> dict | None:
    return sakura_profile.load_latest_profile(conn, scope)


def mastery_band(score: float, evidence: int) -> str:
    return sakura_profile.mastery_band(score, evidence)


def merge_profile_locally(stats: list[dict], insights: list[dict], prev_profile: dict | None) -> dict:
    return sakura_profile.merge_profile_locally(
        stats,
        insights,
        prev_profile,
        root_causes=ROOT_CAUSES,
    )


def polish_profile_with_ai(base_profile: dict, insights: list[dict]) -> dict:
    return sakura_profile.polish_profile_with_ai(
        base_profile,
        insights,
        llm_enabled=llm_enabled(),
        call_llm=call_llm,
        extract_json_block=sakura_ai.extract_json_block,
    )


def synthesize_profile(conn: sqlite3.Connection, want_ai: bool = True, scope: str = "__all__") -> dict:
    return sakura_profile.synthesize_profile(
        conn,
        want_ai=want_ai,
        scope=scope,
        root_causes=ROOT_CAUSES,
        llm_enabled=llm_enabled(),
        call_llm=call_llm,
        extract_json_block=sakura_ai.extract_json_block,
    )


# ==========================================================================
# Coach state and planning settings
# ==========================================================================
def get_coach_state(conn: sqlite3.Connection) -> dict:
    return sakura_coach.get_coach_state(
        conn,
        coach_state_id=COACH_STATE_ID,
        default_daily_minutes=DEFAULT_DAILY_MINUTES,
        exam_date=EXAM_DATE,
    )


def save_coach_state(conn: sqlite3.Connection, **fields) -> dict:
    return sakura_coach.save_coach_state(
        conn,
        coach_state_id=COACH_STATE_ID,
        default_daily_minutes=DEFAULT_DAILY_MINUTES,
        exam_date=EXAM_DATE,
        fields=fields,
    )


def parse_exam_date(value: str | None) -> date:
    return sakura_coach.parse_exam_date(value, EXAM_DATE)


def load_teacher_memories(conn: sqlite3.Connection, limit: int = 10, subject: str = "", search: str = "") -> list[dict]:
    return sakura_teacher_memory.load_teacher_memories(conn, limit, subject, search)


def save_teacher_memory(conn: sqlite3.Connection, content: str, source: str = "chat", subject: str = "") -> dict:
    return sakura_teacher_memory.save_teacher_memory(conn, content, source, subject)


def load_teacher_memory_subjects(conn: sqlite3.Connection) -> list[str]:
    return sakura_teacher_memory.load_teacher_memory_subjects(conn)


def ensure_teacher_memory_subject(conn: sqlite3.Connection, subject: str) -> str:
    return sakura_teacher_memory.ensure_teacher_memory_subject(conn, subject)


def load_teacher_memory_settings(conn: sqlite3.Connection) -> dict:
    return sakura_teacher_memory.load_teacher_memory_settings(conn)


def save_teacher_memory_settings(conn: sqlite3.Connection, compression_prompt: str) -> dict:
    return sakura_teacher_memory.save_teacher_memory_settings(conn, compression_prompt)


def reset_teacher_memory_settings(conn: sqlite3.Connection) -> dict:
    return sakura_teacher_memory.reset_teacher_memory_settings(conn)


def teacher_memory_prompt(conn: sqlite3.Connection, subject_hint: str = "") -> str:
    return sakura_teacher_memory.teacher_memory_prompt(conn, subject_hint)


def parse_tags(value) -> list[str]:
    return sakura_teacher_memory.parse_tags(value)


def mentor_experience_to_dict(row) -> dict:
    return sakura_teacher_memory.mentor_experience_to_dict(row)


def load_mentor_experiences(conn: sqlite3.Connection, limit: int = 30) -> list[dict]:
    return sakura_teacher_memory.load_mentor_experiences(conn, limit)


def save_mentor_experience(conn: sqlite3.Connection, payload: dict) -> dict:
    return sakura_teacher_memory.save_mentor_experience(conn, payload)


def select_relevant_mentor_experiences(conn: sqlite3.Connection, message: str = "", subject_hint: str = "", limit: int = 5) -> list[dict]:
    return sakura_teacher_memory.select_relevant_mentor_experiences(conn, message, subject_hint, limit)


def recent_learning_evidence(conn: sqlite3.Connection, limit: int = 8) -> list[dict]:
    return sakura_coach.recent_learning_evidence(conn, limit)


def build_ai_teacher_context(conn: sqlite3.Connection, message: str = "") -> dict:
    return sakura_coach.build_ai_teacher_context(
        conn,
        message,
        get_coach_state=get_coach_state,
        load_latest_profile=load_latest_profile,
        parse_exam_date=parse_exam_date,
        gather_knowledge_stats=gather_knowledge_stats,
        teacher_memory_prompt=teacher_memory_prompt,
        select_relevant_mentor_experiences=select_relevant_mentor_experiences,
        default_daily_minutes=DEFAULT_DAILY_MINUTES,
        minutes_per_question=STUDY_MINUTES_PER_QUESTION,
        root_cause_prescriptions=ROOT_CAUSE_PRESCRIPTIONS,
        knowledge_dependencies=KNOWLEDGE_DEPENDENCIES,
        find_foundation_questions=find_foundation_questions,
        mock_paper_kind=MOCK_PAPER_KIND,
    )


# ==========================================================================
# L3 决策层：基于学习档案产出诊断 / 查缺排序 / 复习节奏 / 今日任务 / 容量估算
# ==========================================================================
# AI coach planning
# ==========================================================================
def compute_review_backlog(conn: sqlite3.Connection, today: date) -> dict:
    return sakura_coach.compute_review_backlog(conn, today)


def rank_gaps_from_profile(profile: dict, top_n: int = 6) -> list[dict]:
    return sakura_coach.rank_gaps_from_profile(
        profile,
        top_n,
        root_cause_prescriptions=ROOT_CAUSE_PRESCRIPTIONS,
    )


def build_today_actions(
    conn: sqlite3.Connection,
    gaps: list[dict],
    backlog: dict,
    daily_minutes: int,
    in_sprint: bool,
    focus_subject: str,
) -> list[dict]:
    return sakura_coach.build_today_actions(
        conn,
        gaps,
        backlog,
        daily_minutes,
        in_sprint,
        focus_subject,
        minutes_per_question=STUDY_MINUTES_PER_QUESTION,
        knowledge_dependencies=KNOWLEDGE_DEPENDENCIES,
        find_foundation_questions=find_foundation_questions,
        mock_paper_kind=MOCK_PAPER_KIND,
    )


def coach_narrative_ai(profile: dict, gaps: list[dict], backlog: dict, phases: list[dict], predictions: dict) -> str:
    return sakura_coach.coach_narrative_ai(
        profile,
        gaps,
        backlog,
        phases,
        predictions,
        llm_enabled=llm_enabled(),
        call_llm=call_llm,
        local_narrative=sakura_profile.coach_narrative_local,
    )


def build_coach_plan(conn: sqlite3.Connection, settings: dict, want_ai: bool = False) -> dict:
    return sakura_coach.build_coach_plan(
        conn,
        settings,
        want_ai=want_ai,
        load_latest_profile=load_latest_profile,
        parse_exam_date=parse_exam_date,
        default_daily_minutes=DEFAULT_DAILY_MINUTES,
        minutes_per_question=STUDY_MINUTES_PER_QUESTION,
        root_cause_prescriptions=ROOT_CAUSE_PRESCRIPTIONS,
        knowledge_dependencies=KNOWLEDGE_DEPENDENCIES,
        find_foundation_questions=find_foundation_questions,
        mock_paper_kind=MOCK_PAPER_KIND,
        llm_enabled=llm_enabled(),
        call_llm=call_llm,
    )


# ==========================================================================
# Notification payloads and check-in state
# ==========================================================================
def build_daily_reminder(conn: sqlite3.Connection) -> dict:
    today = date.today()
    return sakura_notifications.build_daily_reminder(
        conn,
        today=today,
        backlog=compute_review_backlog(conn, today),
        state=get_coach_state(conn),
        parse_exam_date=parse_exam_date,
        create_practice_batch=create_practice_batch,
        app_public_url=APP_PUBLIC_URL,
    )


def weather_city_from_state(conn: sqlite3.Connection) -> str:
    return sakura_notifications.weather_city_from_state(
        get_coach_state(conn),
        WEATHER_CITY,
    )


def build_weather_reminder(conn: sqlite3.Connection, city: str | None = None) -> dict:
    return sakura_notifications.build_weather_reminder(
        (city or weather_city_from_state(conn)).strip(),
        fetch_weather=sakura_weather.fetch_tomorrow_weather,
        app_public_url=APP_PUBLIC_URL,
    )


def send_notification(title: str, content: str, checkin_mode: str | None = None) -> dict:
    return sakura_notifications.send_notification_for_mode(
        title,
        content,
        checkin_mode or REMIND_CHECKIN_MODE,
        wework_webhook=WEWORK_BOT_WEBHOOK,
        pushplus_token=PUSHPLUS_TOKEN,
        email_settings=current_email_settings(),
    )


def notification_mode_from_payload(payload: dict) -> str:
    return sakura_reminders.normalize_checkin_mode(payload.get("checkin_mode", REMIND_CHECKIN_MODE))


def notification_response_detail(result: dict) -> object:
    return result.get("detail") or result.get("resp") or result.get("error")


def notification_response_configured(result: dict, mode: str) -> bool:
    return result.get("configured", notification_channels_configured(mode))


def send_reminder_payload(reminder: dict, mode: str, attach_pdf: bool = True) -> tuple[dict, dict | None]:
    result = send_notification(reminder["title"], reminder["content"], mode)
    pdf_result = None
    if attach_pdf:
        pdf_result = send_practice_pdf_if_available(reminder, result.get("selected_channel", mode))
        if pdf_result:
            result["practice_pdf"] = pdf_result
    return result, pdf_result


def reminder_response_payload(kind: str, reminder: dict, result: dict, mode: str, **extra: object) -> dict:
    selected_channel = result.get("selected_channel", mode)
    payload = {
        "ok": bool(result.get("ok")),
        "kind": kind,
        "selected_channel": selected_channel,
        "title": reminder.get("title", ""),
        "detail": notification_response_detail(result),
        "configured": notification_response_configured(result, selected_channel),
    }
    for key in ("batch_id", "practice_url", "practice_pdf"):
        if key in reminder or key in result:
            payload[key] = result.get(key, reminder.get(key, ""))
    payload.update(extra)
    return payload


def send_notification_all_channels(title: str, content: str) -> dict:
    return sakura_notifications.send_notification(
        title,
        content,
        wework_webhook=WEWORK_BOT_WEBHOOK,
        pushplus_token=PUSHPLUS_TOKEN,
        email_settings=current_email_settings(),
    )


def today_quote() -> str:
    return sakura_notifications.today_quote(MOTIVATIONAL_QUOTES)


def is_checked_in(conn: sqlite3.Connection, day: date | None = None) -> bool:
    return sakura_notifications.is_checked_in(conn, day)


def mark_checkin(conn: sqlite3.Connection, day: date | None = None) -> None:
    sakura_notifications.mark_checkin(conn, day)


def build_morning_reminder(conn: sqlite3.Connection) -> dict:
    return sakura_notifications.build_morning_reminder(
        build_daily_reminder(conn),
        quote=today_quote(),
        app_public_url=APP_PUBLIC_URL,
    )


def build_night_check(conn: sqlite3.Connection) -> dict:
    today = date.today()
    return sakura_notifications.build_night_check(
        checked_in=is_checked_in(conn, today),
        quote=today_quote(),
        nag=NAG_MESSAGES[today.toordinal() % len(NAG_MESSAGES)],
        backlog=compute_review_backlog(conn, today),
        app_public_url=APP_PUBLIC_URL,
    )


def reminder_kinds_for_minute(minute: str, schedules: list[tuple[str, str, str]]) -> list[str]:
    return sakura_scheduler.reminder_kinds_for_minute(minute, schedules)


def scheduled_reminder_kinds(now: datetime | None = None) -> list[str]:
    return sakura_scheduler.scheduled_reminder_kinds(
        now,
        [
            ("morning", REMIND_MORNING_ON, REMIND_MORNING_TIME),
            ("night", REMIND_NIGHT_ON, REMIND_NIGHT_TIME),
            ("weather", REMIND_WEATHER_ON, REMIND_WEATHER_TIME),
        ],
    )


def claim_reminder_dispatch(conn: sqlite3.Connection, kind: str, now: datetime) -> bool:
    return sakura_scheduler.claim_reminder_dispatch(conn, kind, now)


def finish_reminder_dispatch(conn: sqlite3.Connection, kind: str, now: datetime, status: str, detail: dict) -> None:
    sakura_scheduler.finish_reminder_dispatch(conn, kind, now, status, detail)


def build_scheduled_reminder(conn: sqlite3.Connection, kind: str) -> dict:
    if kind == "morning":
        return build_morning_reminder(conn)
    if kind == "night":
        return build_night_check(conn)
    if kind == "weather":
        return build_weather_reminder(conn)
    return build_daily_reminder(conn)


def dispatch_scheduled_reminder(kind: str, mode: str | None = None) -> dict:
    return sakura_scheduler.dispatch_scheduled_reminder(
        kind,
        mode=mode,
        default_mode=REMIND_CHECKIN_MODE,
        connect=connect,
        build_payload=build_scheduled_reminder,
        send_payload=send_reminder_payload,
        channels_configured=notification_channels_configured,
        response_detail=notification_response_detail,
        response_configured=notification_response_configured,
        print_exception=traceback.print_exc,
    )


def reminder_scheduler_loop() -> None:
    sakura_scheduler.reminder_scheduler_loop(
        enabled=lambda: INTERNAL_SCHEDULER_ENABLED,
        scheduled_kinds=scheduled_reminder_kinds,
        dispatch=dispatch_scheduled_reminder,
        poll_seconds=SCHEDULER_POLL_SECONDS,
        print_exception=traceback.print_exc,
    )


def start_internal_scheduler() -> None:
    global _scheduler_started
    if not INTERNAL_SCHEDULER_ENABLED:
        print("[sakura scheduler] disabled by SAKURA_INTERNAL_SCHEDULER=0", flush=True)
        return
    with _scheduler_lock:
        if _scheduler_started:
            return
        worker = threading.Thread(target=reminder_scheduler_loop, name="sakura-reminder-scheduler", daemon=True)
        worker.start()
        _scheduler_started = True


def build_mistakes_pdf(conn: sqlite3.Connection, query: dict, mistakes_only: bool = True) -> tuple[bytes, int]:
    return sakura_export.build_filtered_mistakes_pdf(
        conn,
        query,
        mistakes_only=mistakes_only,
        build_question_filters=build_question_filters,
        normalize_meta_tags=normalize_meta_tags,
    )


def build_practice_batch_pdf(conn: sqlite3.Connection, batch_id: str) -> tuple[bytes, int]:
    return sakura_export.build_practice_batch_pdf(conn, batch_id, normalize_meta_tags)


def send_practice_pdf_if_available(reminder: dict, mode: str) -> dict | None:
    return sakura_notifications.send_practice_pdf_if_available(
        reminder,
        mode,
        send_pdf_enabled=REMIND_SEND_PDF,
        connect=connect,
        build_practice_batch_pdf=build_practice_batch_pdf,
        wework_webhook=WEWORK_BOT_WEBHOOK,
        current_email_settings=current_email_settings,
    )


def load_daily_rules(conn: sqlite3.Connection, enabled_only: bool = False) -> list[dict]:
    return sakura_daily.load_daily_rules(conn, enabled_only)


def save_daily_rule(conn: sqlite3.Connection, payload: dict) -> dict:
    return sakura_daily.save_daily_rule(conn, payload)


def get_daily_rule_options(conn: sqlite3.Connection, query: dict) -> dict:
    return sakura_daily.get_daily_rule_options(conn, query, document_to_dict)


def build_daily_payload(conn: sqlite3.Connection) -> dict:
    return sakura_daily.build_daily_payload(
        conn,
        row_to_dict=row_to_dict,
        weak_chapter_dependencies=weak_chapter_dependencies,
        find_foundation_questions=find_foundation_questions,
        default_subject=DEFAULT_SUBJECT,
        default_document_kind=DEFAULT_DOCUMENT_KIND,
        daily_scope=REMIND_DAILY_SCOPE,
        daily_limit=int(REMIND_DAILY_LIMIT),
    )


def create_practice_batch(conn: sqlite3.Connection, source: str = "push") -> dict:
    return sakura_daily.create_practice_batch(conn, build_daily_payload, source)


def practice_batch_payload(conn: sqlite3.Connection, batch_id: str) -> dict | None:
    return sakura_daily.practice_batch_payload(conn, batch_id, row_to_dict)


def latest_daily_push_batch_payload(conn: sqlite3.Connection) -> dict | None:
    return sakura_daily.latest_daily_push_batch_payload(conn, row_to_dict)


def apply_practice_feedback(conn: sqlite3.Connection, batch_id: str, q_id: str, status: str, note: str = "") -> dict:
    def insert_daily_review_note(db, question_id, **kwargs):
        return sakura_questions.insert_question_review_note(
            db,
            question_id,
            normalize_meta_tags=normalize_meta_tags,
            **kwargs,
        )

    return sakura_daily.apply_practice_feedback(
        conn,
        batch_id,
        q_id,
        status,
        note,
        normalize_label,
        schedule_for_status,
        row_to_dict,
        insert_daily_review_note,
    )


def import_textbook_pdf(filename: str, pdf_bytes: bytes, title: str = "", subject: str = "") -> dict:
    return sakura_textbook_runtime.import_textbook_pdf(
        filename,
        pdf_bytes,
        title=title,
        subject=subject,
        upload_dir=UPLOAD_DIR,
        connect=connect,
        normalize_label=normalize_label,
        default_subject=DEFAULT_SUBJECT,
    )


def build_textbook_context(
    conn: sqlite3.Connection,
    textbook_id: str,
    page_number: int,
    paragraph_index: int = 0,
    *,
    full_page_ocr: bool = True,
) -> tuple[dict, dict]:
    return sakura_textbook_runtime.build_textbook_context(
        conn,
        textbook_id,
        page_number,
        paragraph_index,
        to_public_path=to_public_path,
        page_dir=PAGE_DIR,
        render_page_image=render_page_image,
        ocr_image_text=sakura_ocr.image_ocr_text,
        full_page_ocr=full_page_ocr,
    )


def explain_textbook_with_ai(book: dict, page: dict, message: str, history: list[dict]) -> str:
    return sakura_textbook_runtime.explain_textbook_with_ai(
        book,
        page,
        message,
        history,
        llm_enabled=llm_enabled(),
        call_llm_messages=call_llm_messages,
        vision_enabled=vision_enabled(),
        call_llm_vision=call_llm_vision,
        image_to_data_url=sakura_ai.image_to_data_url,
    )


def explain_textbook_page_with_vision(book: dict, page: dict, message: str = "") -> str:
    return sakura_textbook_runtime.explain_textbook_page_with_vision(
        book,
        page,
        message,
        vision_enabled=vision_enabled(),
        call_llm_vision=call_llm_vision,
        image_to_data_url=sakura_ai.image_to_data_url,
    )


def parse_positive_int(value: str, fallback: int | None = None) -> int | None:
    return sakura_parse.positive_int(value, fallback)


def import_pdf(
    filename: str,
    pdf_bytes: bytes,
    title: str = "",
    subject: str = "",
    document_kind: str = DEFAULT_DOCUMENT_KIND,
    start_page: int | None = None,
    end_page: int | None = None,
    split_questions: bool = False,
) -> dict:
    return sakura_document_runtime.import_pdf(
        filename,
        pdf_bytes,
        title=title,
        subject=subject,
        document_kind=document_kind,
        start_page=start_page,
        end_page=end_page,
        split_questions=split_questions,
        upload_dir=UPLOAD_DIR,
        page_dir=PAGE_DIR,
        connect=connect,
        normalize_label=normalize_label,
        normalize_document_kind=normalize_document_kind,
        classify_question=classify_question_locally,
        new_chapter_state=new_chapter_state,
        default_subject=DEFAULT_SUBJECT,
        default_chapter=DEFAULT_CHAPTER,
        mock_paper_kind=MOCK_PAPER_KIND,
        mock_paper_chapter=MOCK_PAPER_CHAPTER,
    )


def unlink_if_inside_data(path_value: str) -> None:
    sakura_documents.unlink_if_inside(DATA_DIR, path_value)


def set_migration_job(job_id: str, **updates) -> None:
    sakura_migration.set_job(job_id, **updates)


def get_migration_job(job_id: str) -> dict | None:
    return sakura_migration.get_job(job_id)


def run_migration_import_job(job_id: str, upload_path: Path) -> None:
    sakura_migration.run_import_job(
        job_id,
        upload_path,
        root=ROOT,
        db_path=DB_PATH,
        folders={"uploads": UPLOAD_DIR, "pages": PAGE_DIR},
        ensure_dirs=ensure_dirs,
        init_db=init_db,
    )


class DemoHandler(BaseHTTPRequestHandler):
    server_version = f"SakuraStudy/{APP_VERSION}"

    def log_message(self, format: str, *args) -> None:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {format % args}")

    def is_public_path(self, path: str) -> bool:
        return sakura_auth.is_public_path(path)

    def get_cookie(self, name: str) -> str:
        return sakura_auth.cookie_value(self.headers.get("Cookie") or "", name)

    def client_ip(self) -> str:
        return sakura_security.client_ip(self.headers, self.client_address)

    def user_agent(self) -> str:
        return sakura_security.user_agent(self.headers)

    def is_authenticated(self) -> bool:
        if not auth_enabled():
            return True
        return verify_session_token(self.get_cookie(AUTH_COOKIE_NAME))

    def require_auth(self, path: str) -> bool:
        if self.is_public_path(path) or self.is_authenticated():
            return True
        if path.startswith("/api/"):
            return json_response(self, {"error": "请先登录 Sakura 做题集。", "login_required": True}, HTTPStatus.UNAUTHORIZED)
        return redirect_response(self, "/login")

    def handle_login_get(self) -> None:
        if self.is_authenticated():
            return redirect_response(self, "/")
        return text_response(self, login_page(), content_type="text/html")

    def handle_login_post(self) -> None:
        try:
            raw = sakura_http.read_limited_body(
                self.headers,
                self.rfile,
                max_bytes=sakura_http.MAX_FORM_BODY_BYTES,
            ).decode("utf-8")
        except (sakura_http.BadRequestError, UnicodeDecodeError) as exc:
            return text_response(self, login_page(f"登录请求格式错误：{exc}"), HTTPStatus.BAD_REQUEST, "text/html")
        fields = parse_qs(raw)
        password = fields.get("password", [""])[0]
        ip = self.client_ip()
        ua = self.user_agent()
        if not auth_enabled():
            return redirect_response(self, "/")
        with connect() as conn:
            locked = sakura_security.current_lock(conn, ip)
            if locked["locked"]:
                blocked = sakura_security.record_login_failure(conn, ip, ua)
                return text_response(
                    self,
                    login_page(sakura_security.login_failure_message(blocked)),
                    HTTPStatus.TOO_MANY_REQUESTS,
                    "text/html",
                )
        if not hmac.compare_digest(password, ADMIN_PASSWORD):
            with connect() as conn:
                result = sakura_security.record_login_failure(conn, ip, ua)
            if result.get("alert"):
                send_login_security_alert(ip, ua, result)
            status = HTTPStatus.TOO_MANY_REQUESTS if result.get("locked") else HTTPStatus.UNAUTHORIZED
            return text_response(self, login_page(sakura_security.login_failure_message(result)), status, "text/html")
        with connect() as conn:
            sakura_security.record_login_success(conn, ip, ua)
        token = make_session_token()
        self.send_response(HTTPStatus.FOUND)
        self.send_header("Location", "/")
        self.send_header(
            "Set-Cookie",
            f"{AUTH_COOKIE_NAME}={urllib.parse.quote(token)}; Path=/; Max-Age={AUTH_MAX_AGE_SECONDS}; HttpOnly; SameSite=Lax",
        )
        self.end_headers()

    def do_GET(self) -> None:
        try:
            parsed = urlparse(self.path)
            if parsed.path == "/login":
                return self.handle_login_get()
            if not self.require_auth(parsed.path):
                return
            if parsed.path == "/":
                return self.serve_file(STATIC_DIR / "index.html")
            if parsed.path.startswith("/practice/"):
                batch_id = parsed.path.split("/")[-1]
                return self.handle_practice_page(batch_id)
            if parsed.path == "/api/health":
                return json_response(self, {"ok": True, "date": date.today().isoformat(), "demo_mode": demo_mode_enabled()})
            route = sakura_routes.route_for(parsed.path, sakura_routes.GET_ROUTES)
            if route:
                return self.dispatch_route(route, parse_qs(parsed.query))
            route = sakura_routes.get_dynamic_route(parsed.path)
            if route:
                return self.dispatch_route(route, parse_qs(parsed.query))
            base = public_file_base_for_path(parsed.path)
            if base:
                candidate = (ROOT / parsed.path.lstrip("/")).resolve()
                try:
                    candidate.relative_to(base.resolve())
                except ValueError:
                    return text_response(self, "Not found", HTTPStatus.NOT_FOUND)
                return self.serve_file(candidate)
            return text_response(self, "Not found", HTTPStatus.NOT_FOUND)
        except Exception as exc:
            traceback.print_exc()
            return json_response(self, {"error": str(exc)}, 500)

    def do_HEAD(self) -> None:
        try:
            parsed = urlparse(self.path)
            if parsed.path == "/api/health":
                self.send_response(HTTPStatus.OK)
            elif parsed.path == "/login":
                self.send_response(HTTPStatus.OK)
            elif not self.require_auth(parsed.path):
                return
            else:
                self.send_response(HTTPStatus.OK)
            self.end_headers()
        except Exception:
            traceback.print_exc()
            self.send_response(HTTPStatus.INTERNAL_SERVER_ERROR)
            self.end_headers()

    def do_POST(self) -> None:
        try:
            parsed = urlparse(self.path)
            if parsed.path == "/login":
                return self.handle_login_post()
            if not self.require_auth(parsed.path):
                return
            if demo_mode_enabled():
                return demo_mode_response(self)
            route = sakura_routes.route_for(parsed.path, sakura_routes.POST_ROUTES)
            if route:
                return self.dispatch_route(route)
            route = sakura_routes.post_dynamic_route(parsed.path)
            if route:
                return self.dispatch_route(route)
            return text_response(self, "Not found", HTTPStatus.NOT_FOUND)
        except sakura_http.PayloadTooLargeError as exc:
            return json_response(self, {"error": str(exc)}, HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
        except sakura_http.BadRequestError as exc:
            return json_response(self, {"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            traceback.print_exc()
            return json_response(self, {"error": str(exc)}, 500)

    def do_DELETE(self) -> None:
        try:
            parsed = urlparse(self.path)
            if not self.require_auth(parsed.path):
                return
            if demo_mode_enabled():
                return demo_mode_response(self)
            route = sakura_routes.route_for(parsed.path, sakura_routes.DELETE_ROUTES)
            if route:
                return self.dispatch_route(route)
            route = sakura_routes.delete_dynamic_route(parsed.path)
            if route:
                return self.dispatch_route(route)
            return text_response(self, "Not found", HTTPStatus.NOT_FOUND)
        except Exception as exc:
            traceback.print_exc()
            return json_response(self, {"error": str(exc)}, 500)

    def do_PATCH(self) -> None:
        try:
            parsed = urlparse(self.path)
            if not self.require_auth(parsed.path):
                return
            if demo_mode_enabled():
                return demo_mode_response(self)
            route = sakura_routes.patch_dynamic_route(parsed.path)
            if route:
                return self.dispatch_route(route)
            return text_response(self, "Not found", HTTPStatus.NOT_FOUND)
        except sakura_http.BadRequestError as exc:
            return json_response(self, {"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            traceback.print_exc()
            return json_response(self, {"error": str(exc)}, 500)

    def dispatch_route(self, route: sakura_routes.RouteTarget, query: dict | None = None) -> None:
        handler = getattr(self, route.handler)
        if route.with_query:
            return handler(query or {})
        return handler(*route.args)

    def read_json(self) -> dict:
        return sakura_http.read_json_body(self.headers, self.rfile)

    def serve_file(self, path: Path) -> None:
        return sakura_http.serve_file(self, path, ROOT)

    def handle_upload(self) -> None:
        form = sakura_http.read_multipart_form(self.headers, self.rfile)
        file_item = sakura_http.first_form_file(form, "file")
        if file_item is None or not sakura_http.uploaded_filename(file_item):
            return json_response(self, {"error": "请上传 PDF 文件。"}, 400)
        if not sakura_http.uploaded_file_has_suffix(file_item, ".pdf"):
            return json_response(self, {"error": "当前 demo 只支持 PDF。"}, 400)
        title = form.getfirst("title", "")
        subject = form.getfirst("subject", "")
        document_kind = form.getfirst("document_kind", DEFAULT_DOCUMENT_KIND)
        start_page = parse_positive_int(form.getfirst("start_page", ""), None)
        end_page = parse_positive_int(form.getfirst("end_page", ""), None)
        split_questions = sakura_parse.bool_flag(form.getfirst("split_questions", ""))
        result = import_pdf(sakura_http.uploaded_filename(file_item), file_item.file.read(), title, subject, document_kind, start_page, end_page, split_questions)
        return json_response(self, result)

    def handle_textbook_upload(self) -> None:
        form = sakura_http.read_multipart_form(self.headers, self.rfile)
        file_item = sakura_http.first_form_file(form, "file")
        if file_item is None or not sakura_http.uploaded_filename(file_item):
            return json_response(self, {"error": "请上传教材 PDF。"}, 400)
        if not sakura_http.uploaded_file_has_suffix(file_item, ".pdf"):
            return json_response(self, {"error": "教材精读目前只支持 PDF。"}, 400)
        title = form.getfirst("title", "")
        subject = form.getfirst("subject", "")
        try:
            result = import_textbook_pdf(sakura_http.uploaded_filename(file_item), file_item.file.read(), title, subject)
        except sakura_textbook.TextbookImportError as exc:
            return json_response(self, {"error": str(exc)}, 400)
        return json_response(self, result)

    def handle_textbooks(self) -> None:
        with connect() as conn:
            rows = sakura_textbook.load_textbooks(conn)
        return json_response(self, {"textbooks": [sakura_textbook.textbook_to_dict(row) for row in rows]})

    def handle_textbook_page(self, textbook_id: str, page_number: int) -> None:
        with connect() as conn:
            book, page = build_textbook_context(conn, textbook_id, page_number)
        return json_response(self, {"textbook": book, "page": page})

    def handle_delete_textbook(self, textbook_id: str) -> None:
        with connect() as conn:
            deleted = sakura_textbook.delete_textbook(conn, textbook_id, delete_file=unlink_if_inside_data)
            if not deleted:
                return json_response(self, {"error": "教材不存在。"}, 404)
            unlink_if_inside_data(str(PAGE_DIR / f"{textbook_id}_textbook_current.png"))
        return json_response(self, {"ok": True})

    def handle_delete_textbook_page(self, textbook_id: str, page_number: int) -> None:
        with connect() as conn:
            result = sakura_textbook.delete_textbook_page(
                conn,
                textbook_id,
                page_number,
                delete_file=unlink_if_inside_data,
            )
            if not result:
                return json_response(self, {"error": "教材页不存在。"}, 404)
            unlink_if_inside_data(str(PAGE_DIR / f"{textbook_id}_textbook_current.png"))
        return json_response(self, result)

    def handle_textbook_chat(self) -> None:
        request = sakura_textbook.parse_textbook_request(self.read_json(), parse_positive_int=parse_positive_int)
        textbook_id = request["textbook_id"]
        requested_page = request["page_number"]
        paragraph_index = request["paragraph_index"]
        selected_paragraph_text = request["selected_paragraph_text"]
        message = request["message"]
        history = request["history"]
        if not textbook_id or not message:
            return json_response(self, {"error": "请选择教材并输入问题。"}, 400)
        with connect() as conn:
            if paragraph_index > 0 and selected_paragraph_text:
                book, page = sakura_textbook.build_textbook_selected_paragraph_context(
                    conn,
                    textbook_id,
                    requested_page,
                    paragraph_index,
                    selected_paragraph_text,
                    to_public_path=to_public_path,
                )
            else:
                book, page = build_textbook_context(conn, textbook_id, requested_page, paragraph_index)
            pdf_page_number = int(page.get("pdf_page_number") or page.get("page_number") or requested_page)
            sakura_textbook.save_textbook_chat_message(
                conn,
                textbook_id=textbook_id,
                page_number=pdf_page_number,
                role="user",
                content=message,
                content_limit=4000,
            )
            try:
                answer = explain_textbook_with_ai(book, page, message, history)
            except Exception as exc:
                traceback.print_exc()
                return json_response(self, {"error": f"AI 精读失败：{exc}"}, 500)
            sakura_textbook.save_textbook_chat_message(
                conn,
                textbook_id=textbook_id,
                page_number=pdf_page_number,
                role="assistant",
                content=answer,
                content_limit=8000,
            )
        return json_response(self, {"answer": answer, "textbook": book, "page": page, "has_key": llm_enabled()})

    def handle_textbook_vision(self) -> None:
        request = sakura_textbook.parse_textbook_request(self.read_json(), parse_positive_int=parse_positive_int)
        textbook_id = request["textbook_id"]
        requested_page = request["page_number"]
        message = request["message"]
        if not textbook_id:
            return json_response(self, {"error": "请选择教材。"}, 400)
        with connect() as conn:
            book, page = build_textbook_context(conn, textbook_id, requested_page, 0, full_page_ocr=False)
            vision_ok = False
            try:
                answer = explain_textbook_page_with_vision(book, page, message)
                vision_ok = vision_enabled()
            except Exception as exc:
                traceback.print_exc()
                answer = f"视觉模型读取失败：{exc}"
            if vision_ok:
                pdf_page_number = int(page.get("pdf_page_number") or page.get("page_number") or requested_page)
                sakura_textbook.save_textbook_chat_message(
                    conn,
                    textbook_id=textbook_id,
                    page_number=pdf_page_number,
                    role="assistant",
                    content=answer,
                    content_limit=8000,
                )
        return json_response(self, {
            "answer": answer,
            "textbook": book,
            "page": page,
            "has_vision": vision_ok,
        })

    def handle_textbook_memory(self) -> None:
        request = sakura_textbook.parse_textbook_request(self.read_json(), parse_positive_int=parse_positive_int)
        textbook_id = request["textbook_id"]
        requested_page = request["page_number"]
        paragraph_index = request["paragraph_index"]
        selected_paragraph_text = request["selected_paragraph_text"]
        history = request["history"]
        if not textbook_id:
            return json_response(self, {"error": "请选择教材。"}, 400)
        with connect() as conn:
            try:
                book, _page = sakura_textbook.resolve_textbook_page_row(conn, textbook_id, requested_page)
            except ValueError:
                return json_response(self, {"error": "教材页不存在。"}, 404)
            selected = selected_paragraph_text or "未指定"
            display_page = int(requested_page)
            if llm_enabled() and history:
                prompt = (
                    "请把下面教材精读对话压缩成一条长期学习记忆，100-180字，包含教材、页码、困惑、关键理解和后续复习建议。\n"
                    f"教材：{book.get('title')}；页码：{display_page}；段落：{selected}\n"
                    + json.dumps(history[-10:], ensure_ascii=False)
                )
                try:
                    content = call_llm(prompt, temperature=0.2)
                except Exception:
                    traceback.print_exc()
                    content = ""
            else:
                last_user = next((item.get("content", "") for item in reversed(history) if item.get("role") == "user"), "")
                content = f"教材精读：{book.get('title')} 第{display_page}页。困惑：{last_user or '未记录'}。关键段落：{selected[:160]}。后续复习时优先回看该页概念与例题。"
            memory = save_teacher_memory(conn, content, "textbook", str(book.get("subject") or ""))
        return json_response(self, {"memory": memory})

    def handle_documents(self) -> None:
        with connect() as conn:
            rows = sakura_documents.load_documents(conn, data_dir=DATA_DIR)
            options = get_filter_options(conn)
        return json_response(self, {"documents": [document_to_dict(row) for row in rows], **options})

    def handle_update_document(self, doc_id: str) -> None:
        payload = self.read_json()
        title = str(payload.get("title", "")).strip()
        subject = str(payload.get("subject", "")).strip() or DEFAULT_SUBJECT
        document_kind = normalize_document_kind(payload.get("document_kind"))
        if not title:
            return json_response(self, {"error": "做题本名称不能为空。"}, 400)
        if len(title) > 120:
            return json_response(self, {"error": "做题本名称不能超过 120 个字符。"}, 400)
        if len(subject) > 60:
            return json_response(self, {"error": "科目名称不能超过 60 个字符。"}, 400)

        with connect() as conn:
            updated = sakura_documents.update_document(
                conn,
                doc_id,
                title=title,
                subject=subject,
                document_kind=document_kind,
            )
            if not updated:
                return json_response(self, {"error": "做题本不存在。"}, 404)
        return json_response(self, {"ok": True, "document": document_to_dict(updated)})

    def handle_questions(self, query: dict) -> None:
        where, params = build_question_filters(
            query,
            ("category", "status", "status_group", "document_id", "chapter", "subject", "document_kind", "search"),
        )
        with connect() as conn:
            rows, stats, subject_stats = sakura_questions.load_question_index(conn, where, params)
            options = get_scoped_filter_options(conn, query)
        return json_response(
            self,
            {
                "questions": [row_to_dict(row) for row in rows],
                "stats": [dict(row) for row in stats],
                "subject_stats": [dict(row) for row in subject_stats],
                **options,
            },
        )

    def handle_question_detail(self, q_id: str) -> None:
        with connect() as conn:
            row = sakura_questions.load_question_detail(conn, q_id)
            if not row:
                return json_response(self, {"error": "题目不存在。"}, 404)
            payload = question_detail_to_dict(conn, row)
        return json_response(self, payload)

    def handle_delete_question(self, q_id: str) -> None:
        with connect() as conn:
            result = sakura_documents.delete_question(conn, q_id, data_dir=DATA_DIR)
            if not result:
                return json_response(self, {"error": "题目不存在。"}, 404)
        return json_response(self, result)

    def handle_delete_document(self, doc_id: str) -> None:
        with connect() as conn:
            deleted = sakura_documents.delete_document(conn, doc_id, data_dir=DATA_DIR)
            if not deleted:
                return json_response(self, {"error": "做题本不存在。"}, 404)
        return json_response(self, {"ok": True})

    def handle_delete_reflection(self, ref_id: str) -> None:
        with connect() as conn:
            deleted = sakura_reflection.delete_reflection(conn, ref_id)
            if not deleted:
                return json_response(self, {"error": "历史知识归档不存在。"}, 404)
        return json_response(self, {"ok": True, "id": ref_id})

    def handle_clear_coach_plan(self) -> None:
        """只清除学习档案页当前建议，不删除档案版本、错题证据或做题记录。"""
        with connect() as conn:
            get_coach_state(conn)
            conn.execute(
                """
                UPDATE coach_state
                SET last_plan_at = NULL,
                    plan_json = '{}'
                WHERE id = ?
                """,
                (COACH_STATE_ID,),
            )
        return json_response(self, {
            "ok": True,
            "cleared": "coach_plan",
        })

    def handle_rescan_chapters(self, doc_id: str) -> None:
        with connect() as conn:
            try:
                result = sakura_questions.rescan_document_chapters(
                    conn,
                    doc_id,
                    normalize_document_kind=normalize_document_kind,
                    extract_text_and_chapters=extract_text_and_chapters,
                    classify_by_rules=classify_by_rules,
                    default_category=DEFAULT_CATEGORY,
                    default_chapter=DEFAULT_CHAPTER,
                    mock_paper_kind=MOCK_PAPER_KIND,
                )
            except sakura_questions.QuestionServiceError as exc:
                return json_response(self, {"error": str(exc)}, exc.status)
        return json_response(self, result)

    def handle_update_question(self, q_id: str) -> None:
        payload = self.read_json()
        review_note = str(payload.get("review_note") or "").strip()
        should_append_note = bool(payload.get("append_review_note")) and bool(review_note)
        with connect() as conn:
            try:
                row = sakura_questions.update_question(
                    conn,
                    q_id,
                    payload,
                    normalize_meta_tags=normalize_meta_tags,
                    wrongish_statuses=WRONGISH_STATUSES,
                    schedule_for_status=schedule_for_status,
                )
                if should_append_note:
                    sakura_questions.insert_question_review_note(
                        conn,
                        q_id,
                        status=row["status"],
                        note=review_note,
                        meta_tags=payload.get("meta_tags", row["meta_tags"]),
                        source=str(payload.get("review_note_source") or "detail"),
                        normalize_meta_tags=normalize_meta_tags,
                    )
                    row = sakura_questions.load_question_detail(conn, q_id)
            except sakura_questions.QuestionUpdateError as exc:
                return json_response(self, {"error": str(exc)}, exc.status)
            result = question_detail_to_dict(conn, row)
        return json_response(self, result)

    def handle_question_review_notes_get(self, q_id: str) -> None:
        with connect() as conn:
            row = sakura_questions.load_question_detail(conn, q_id)
            if not row:
                return json_response(self, {"error": "题目不存在。"}, 404)
            notes = question_detail_to_dict(conn, row)["review_notes"]
        return json_response(self, {"question_id": q_id, "review_notes": notes})

    def handle_question_review_notes_post(self, q_id: str) -> None:
        payload = self.read_json()
        with connect() as conn:
            try:
                row = sakura_questions.load_question_detail(conn, q_id)
                if not row:
                    return json_response(self, {"error": "题目不存在。"}, 404)
                note = sakura_questions.insert_question_review_note(
                    conn,
                    q_id,
                    status=str(payload.get("status") or row["status"] or ""),
                    note=str(payload.get("note") or ""),
                    meta_tags=payload.get("meta_tags", row["meta_tags"]),
                    source=str(payload.get("source") or "detail"),
                    normalize_meta_tags=normalize_meta_tags,
                )
            except sakura_questions.QuestionUpdateError as exc:
                return json_response(self, {"error": str(exc)}, exc.status)
        if not note:
            return json_response(self, {"error": "复盘记录不能为空。"}, 400)
        return json_response(self, {"ok": True, "review_note": note})

    def handle_analyze(self, q_id: str) -> None:
        with connect() as conn:
            row = sakura_questions.load_question_for_ai(conn, q_id)
            if not row:
                return json_response(self, {"error": "题目不存在。"}, 404)
            question = question_payload(row)
            analysis, insight = analyze_and_extract_with_ai(question)
            conn.execute("UPDATE questions SET ai_analysis = ? WHERE id = ?", (analysis, q_id))
            upsert_insight(conn, question, insight)
        return json_response(self, {"ai_analysis": analysis, "insight": insight})

    def handle_hint(self, q_id: str) -> None:
        payload = self.read_json()
        level = sakura_parse.clamped_int(payload.get("level", "1"), minimum=1, maximum=3, fallback=1)
        raw_allow_vision = payload.get("allow_vision_ocr")
        allow_vision_ocr = raw_allow_vision is True or str(raw_allow_vision or "").lower() in {"1", "true", "yes", "on"}
        with connect() as conn:
            row = sakura_questions.load_question_for_ai(conn, q_id)
            if not row:
                return json_response(self, {"error": "题目不存在。"}, 404)
            question = question_payload(row)
            if level == 3:
                response = full_solution_hint_response(
                    conn,
                    q_id,
                    question,
                    allow_vision_ocr=allow_vision_ocr,
                )
                conn.execute("UPDATE questions SET ai_hint = ? WHERE id = ?", (response["hint"], q_id))
                return json_response(self, response)
            hint = generate_hint_with_ai(question, level)
            conn.execute("UPDATE questions SET ai_hint = ? WHERE id = ?", (hint, q_id))
        return json_response(self, {"level": level, "hint": hint, "needs_vision_confirm": False})

    def handle_variations(self, q_id: str) -> None:
        with connect() as conn:
            row = sakura_questions.load_question_for_ai(conn, q_id)
            if not row:
                return json_response(self, {"error": "题目不存在。"}, 404)
            variations = generate_variations_with_ai(question_payload(row))
            conn.execute("UPDATE questions SET ai_variations = ? WHERE id = ?", (variations, q_id))
        return json_response(self, {"ai_variations": variations})

    def handle_crop_question(self, q_id: str) -> None:
        payload = self.read_json()
        crop = payload.get("crop") or {}
        with connect() as conn:
            row = conn.execute("SELECT image_path FROM questions WHERE id = ?", (q_id,)).fetchone()
            if not row:
                return json_response(self, {"error": "题目不存在。"}, 404)
            image_path = Path(row["image_path"])
            if not image_path.exists():
                return json_response(self, {"error": "题图文件不存在。"}, 404)
            try:
                crop_image_by_ratio(image_path, crop)
            except ImportError:
                return json_response(self, {"error": "裁剪功能需要安装 Pillow：pip install -r requirements.txt"}, 500)
            except Exception as exc:
                return json_response(self, {"error": f"裁剪失败：{exc}"}, 400)
            updated = sakura_questions.load_question_detail(conn, q_id)
        return json_response(self, row_to_dict(updated))

    def handle_chapter_stats(self, doc_id: str) -> None:
        with connect() as conn:
            doc, stats = sakura_questions.load_chapter_stats(conn, doc_id)
            if not doc:
                return json_response(self, {"error": "做题本不存在。"}, 404)
            meta_stats = get_meta_tag_stats(conn, doc_id)
        return json_response(self, {"document": document_to_dict(doc), "chapters": stats, "meta_tags": meta_stats})

    def handle_reflection_preview(self, query: dict) -> None:
        period = query.get("period", ["week"])[0]
        if period not in {"week", "month"}:
            period = "week"
        with connect() as conn:
            payload = sakura_reflection.build_reflection_payload(conn, period)
        return json_response(self, payload)

    def handle_reflection(self) -> None:
        payload = self.read_json()
        period = payload.get("period", "week")
        if period not in {"week", "month"}:
            period = "week"
        with connect() as conn:
            reflection_payload = sakura_reflection.build_reflection_payload(conn, period)
        if reflection_payload["total"] == 0:
            return json_response(self, {"reflection": "本周期暂无可复盘内容。先完成一些做题记录，再生成总结与反思。", "summary": reflection_payload, "id": None})
        reflection = sakura_reflection.generate_reflection(
            reflection_payload,
            llm_enabled=llm_enabled(),
            call_llm=call_llm,
        )
        with connect() as conn:
            ref_id = sakura_reflection.save_reflection(conn, period, reflection_payload, reflection)
        return json_response(self, {"reflection": reflection, "summary": reflection_payload, "id": ref_id})

    def handle_countdown(self) -> None:
        today = date.today()
        days_left = (EXAM_DATE - today).days
        return json_response(self, {
            "today": today.isoformat(),
            "today_formatted": f"{today.month}月{today.day}日",
            "exam_date": EXAM_DATE.isoformat(),
            "exam_date_formatted": f"{EXAM_DATE.month}月{EXAM_DATE.day}日",
            "days_left": days_left,
            "weekday": ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][today.weekday()],
        })

    def handle_quote(self) -> None:
        today = date.today()
        quote = MOTIVATIONAL_QUOTES[today.toordinal() % len(MOTIVATIONAL_QUOTES)]
        return json_response(self, {"quote": quote, "date": today.isoformat(), "count": len(MOTIVATIONAL_QUOTES)})

    def handle_version(self, query: dict | None = None) -> None:
        force_value = (query or {}).get("force", ["0"])
        if isinstance(force_value, list):
            force_value = force_value[0] if force_value else "0"
        force = str(force_value).lower() in {"1", "true", "yes"}
        info = sakura_update.check_for_update(APP_VERSION, UPDATE_REPO, force=force)
        auto_update = sakura_update.update_capability(ROOT, info)
        if demo_mode_enabled():
            auto_update = sakura_update.disabled_capability(
                "演示模式不可更新",
                "当前为只读演示模式，不允许从页面覆盖代码；请在自己的部署环境中更新。",
                "demo",
            )
        return json_response(self, {"app": "Sakura 做题集", **info, "auto_update": auto_update})

    def handle_version_update(self) -> None:
        if demo_mode_enabled():
            return json_response(self, {"ok": False, "error": "演示模式不允许自动更新。"}, 403)
        result = sakura_update.apply_update(ROOT, APP_VERSION, UPDATE_REPO)
        if result.get("ok") and result.get("restart_required"):
            result.update(schedule_restart_after_update())
        return json_response(self, result, 200 if result.get("ok") else 400)

    # === 学习档案 ===
    def _coach_settings_view(self, state: dict) -> dict:
        return {
            "daily_minutes": state.get("daily_minutes", DEFAULT_DAILY_MINUTES),
            "exam_date": state.get("exam_date") or EXAM_DATE.isoformat(),
            "cadence": state.get("cadence", "immediate"),
            "focus_subject": state.get("focus_subject", ""),
            "weather_city": state.get("weather_city", "") or WEATHER_CITY,
            "last_profile_at": state.get("last_profile_at"),
            "last_plan_at": state.get("last_plan_at"),
        }

    def _profile_needs_refresh(self, conn: sqlite3.Connection, state: dict) -> bool:
        latest = load_latest_profile(conn)
        if not latest:
            return True
        # 有新洞察尚未并入档案
        pending = conn.execute(
            "SELECT COUNT(*) c FROM insights WHERE updated_at > COALESCE(?, '')",
            (state.get("last_profile_at"),),
        ).fetchone()["c"]
        if pending > 0:
            return True
        if state.get("cadence") == "weekly" and state.get("last_profile_at"):
            try:
                last = datetime.fromisoformat(state["last_profile_at"]).date()
                if (date.today() - last).days >= PROFILE_STALE_DAYS:
                    return True
            except ValueError:
                return True
        return False

    def handle_coach_settings_get(self) -> None:
        with connect() as conn:
            state = get_coach_state(conn)
        return json_response(self, self._coach_settings_view(state))

    def handle_coach_settings_post(self) -> None:
        payload = self.read_json()
        fields = {}
        if "daily_minutes" in payload:
            fields["daily_minutes"] = parse_positive_int(str(payload.get("daily_minutes")), DEFAULT_DAILY_MINUTES) or DEFAULT_DAILY_MINUTES
        if "exam_date" in payload:
            fields["exam_date"] = parse_exam_date(payload.get("exam_date")).isoformat()
        if "cadence" in payload:
            fields["cadence"] = "weekly" if str(payload.get("cadence")) == "weekly" else "immediate"
        if "focus_subject" in payload:
            fields["focus_subject"] = str(payload.get("focus_subject", "")).strip()[:60]
        with connect() as conn:
            state = save_coach_state(conn, **fields)
        return json_response(self, self._coach_settings_view(state))

    def handle_weather_settings_get(self) -> None:
        with connect() as conn:
            city = weather_city_from_state(conn)
        return json_response(self, {"city": city, "default_city": WEATHER_CITY})

    def handle_weather_settings_post(self) -> None:
        payload = self.read_json()
        city = str(payload.get("city", "")).strip()[:80]
        if not city:
            return json_response(self, {"error": "请填写城市名称"}, 400)
        with connect() as conn:
            save_coach_state(conn, weather_city=city)
        return json_response(self, {"city": city})

    def handle_weather_preview(self, query: dict) -> None:
        city = (query.get("city", [""])[0] or "").strip()
        with connect() as conn:
            if not city:
                city = weather_city_from_state(conn)
            info = sakura_weather.fetch_tomorrow_weather(city)
        return json_response(self, {"weather": info})

    def handle_weather_reminder_preview(self) -> None:
        payload_in = self.read_json()
        with connect() as conn:
            payload = build_weather_reminder(conn, str(payload_in.get("city", "")).strip() or None)
        return json_response(self, {
            "ok": True,
            "title": payload["title"],
            "content": payload["content"],
            "weather": payload["weather"],
            "will_send": False,
        })

    def handle_ai_memory_get(self, query: dict) -> None:
        subject = (query.get("subject", [""])[0] or "").strip()
        search = (query.get("q", [""])[0] or "").strip()
        limit = sakura_parse.clamped_int(query.get("limit", ["30"])[0], minimum=1, maximum=200, fallback=30)
        with connect() as conn:
            memories = load_teacher_memories(conn, limit=limit, subject=subject, search=search)
            subjects = load_teacher_memory_subjects(conn)
            memory_settings = load_teacher_memory_settings(conn)
        return json_response(self, {
            "memories": memories,
            "subjects": subjects,
            "memory_settings": memory_settings,
            **llm_settings_view(),
        })

    def handle_ai_memory_settings_get(self) -> None:
        with connect() as conn:
            settings = load_teacher_memory_settings(conn)
        return json_response(self, settings)

    def handle_ai_memory_subjects_get(self) -> None:
        with connect() as conn:
            subjects = load_teacher_memory_subjects(conn)
        return json_response(self, {"subjects": subjects})

    def handle_llm_settings_get(self) -> None:
        return json_response(self, llm_settings_view())

    def handle_llm_settings_post(self) -> None:
        try:
            updates = sakura_settings.parse_llm_settings_payload(self.read_json())
        except ValueError as exc:
            return json_response(self, {"error": str(exc)}, 400)
        settings = update_llm_runtime_settings(**updates)
        return json_response(self, {
            **settings,
            "message": "已保存到本地 .env，并已更新当前运行中的服务。",
        })

    def handle_notification_settings_get(self) -> None:
        return json_response(self, notification_settings_view())

    def handle_security_settings_get(self) -> None:
        with connect() as conn:
            events = sakura_security.recent_security_events(conn)
        return json_response(self, {
            **sakura_security.security_settings_view(ADMIN_PASSWORD),
            "recent_events": events,
        })

    def handle_reminder_settings_get(self) -> None:
        return json_response(self, reminder_settings_view())

    def handle_reminder_settings_post(self) -> None:
        settings = update_reminder_runtime_settings(self.read_json())
        return json_response(self, {
            **settings,
            "message": settings.get("cron", {}).get("message") or "提醒时间已保存。",
        })

    def handle_notification_settings_post(self) -> None:
        try:
            updates = sakura_settings.parse_notification_settings_payload(self.read_json())
        except ValueError as exc:
            return json_response(self, {"error": str(exc)}, 400)
        settings = update_notification_runtime_settings(**updates)
        return json_response(self, {
            **settings,
            "message": "已保存到本地 .env，并已更新当前运行中的推送配置。",
        })

    def handle_security_settings_post(self) -> None:
        payload = self.read_json()
        password = str(payload.get("admin_password", "")).strip()
        confirm = str(payload.get("admin_password_confirm", "")).strip()
        if not password:
            return json_response(self, {"error": "请填写新的访问密码。"}, 400)
        if confirm and password != confirm:
            return json_response(self, {"error": "两次输入的密码不一致。"}, 400)
        try:
            settings = update_security_runtime_settings(password)
        except ValueError as exc:
            return json_response(self, {"error": str(exc), "policy": sakura_security.password_policy_view()}, 400)
        with connect() as conn:
            sakura_security.record_security_event(
                conn,
                self.client_ip(),
                self.user_agent(),
                "password_updated",
                {"source": "settings_panel"},
            )
        return json_response(self, {
            **settings,
            "message": "访问密码已保存，旧登录态已失效。请刷新页面并使用新密码重新登录。",
        })

    def handle_email_test(self) -> None:
        result = sakura_email.send_email(
            current_email_settings(),
            "Sakura 邮箱推送测试",
            (
                "### Sakura 邮箱推送测试\n\n"
                "如果你收到这封邮件，说明 SMTP 邮箱通道已经配置成功。\n\n"
                f"[打开 Sakura 做题集]({APP_PUBLIC_URL.rstrip('/')})"
            ),
        )
        status = 200 if result.get("ok") else 400
        return json_response(self, {
            "ok": result.get("ok", False),
            "configured": result.get("configured", True),
            "error": result.get("error", ""),
            "detail": result,
        }, status)

    def handle_ai_memory_compress(self) -> None:
        payload = self.read_json()
        content = str(payload.get("content", "")).strip()
        subject = str(payload.get("subject", "")).strip()
        source = str(payload.get("source", "chat")).strip() or "chat"
        instruction = str(payload.get("instruction", "")).strip()
        if not content:
            return json_response(self, {"error": "原始内容不能为空"}, 400)
        with connect() as conn:
            settings = load_teacher_memory_settings(conn)
        result = sakura_teacher_memory.compress_memory_content(
            content=content,
            subject=subject,
            source=source,
            instruction=instruction,
            settings=settings,
            llm_enabled=llm_enabled(),
            call_llm=call_llm,
            on_error=lambda exc: traceback.print_exc(),
        )
        return json_response(self, result)

    def handle_ai_memory_post(self) -> None:
        payload = self.read_json()
        try:
            with connect() as conn:
                memory = save_teacher_memory(
                    conn,
                    str(payload.get("content", "")),
                    str(payload.get("source", "chat")),
                    str(payload.get("subject", "")),
                )
        except ValueError as exc:
            return json_response(self, {"error": str(exc)}, 400)
        return json_response(self, {"memory": memory})

    def handle_ai_memory_settings_post(self) -> None:
        payload = self.read_json()
        with connect() as conn:
            if payload.get("reset"):
                settings = reset_teacher_memory_settings(conn)
            else:
                settings = save_teacher_memory_settings(conn, str(payload.get("compression_prompt", "")))
        return json_response(self, settings)

    def handle_ai_memory_subjects_post(self) -> None:
        payload = self.read_json()
        subject = str(payload.get("subject", "")).strip()
        if not subject:
            return json_response(self, {"error": "学科名称不能为空"}, 400)
        with connect() as conn:
            normalized = ensure_teacher_memory_subject(conn, subject)
            subjects = load_teacher_memory_subjects(conn)
        return json_response(self, {"subject": normalized, "subjects": subjects})

    def handle_ai_memory_delete(self, memory_id: str) -> None:
        with connect() as conn:
            deleted = sakura_teacher_memory.delete_teacher_memory(conn, memory_id)
            if not deleted:
                return json_response(self, {"error": "记忆不存在"}, 404)
        return json_response(self, {"ok": True})

    def handle_mentor_experience_get(self) -> None:
        with connect() as conn:
            experiences = load_mentor_experiences(conn, limit=50)
        return json_response(self, {"experiences": experiences})

    def handle_mentor_experience_post(self) -> None:
        payload = self.read_json()
        try:
            with connect() as conn:
                item = save_mentor_experience(conn, payload)
        except ValueError as exc:
            return json_response(self, {"error": str(exc)}, 400)
        return json_response(self, {"experience": item})

    def handle_mentor_experience_delete(self, exp_id: str) -> None:
        with connect() as conn:
            deleted = sakura_teacher_memory.delete_mentor_experience(conn, exp_id)
            if not deleted:
                return json_response(self, {"error": "经验不存在"}, 404)
        return json_response(self, {"ok": True})

    def handle_ai_chat(self) -> None:
        payload = self.read_json()
        message = str(payload.get("message", "")).strip()
        if not message:
            return json_response(self, {"error": "请输入要测试的问题"}, 400)
        if not llm_enabled():
            return json_response(self, {
                "error": "未配置 LLM_API_KEY / MIMO_API_KEY / DEEPSEEK_API_KEY，无法调用真实 AI。",
                "has_key": False,
                "model": LLM_MODEL,
                "base_url": LLM_BASE_URL,
            }, 400)
        with connect() as conn:
            context = build_ai_teacher_context(conn, message)
        try:
            with connect() as conn:
                response = sakura_teacher_memory.run_teacher_chat_turn(
                    conn,
                    message=message,
                    context=context,
                    call_llm_messages=call_llm_messages,
                    model=LLM_MODEL,
                    base_url=LLM_BASE_URL,
                )
        except Exception as exc:
            traceback.print_exc()
            return json_response(self, {"error": f"AI 调用失败：{exc}", "has_key": True}, 500)
        return json_response(self, response)

    def handle_coach_get(self) -> None:
        """纯读记忆：返回设置 + 最新档案摘要 + 缓存计划 + 是否需要刷新。零 token。"""
        with connect() as conn:
            state = get_coach_state(conn)
            latest = load_latest_profile(conn)
            needs_refresh = self._profile_needs_refresh(conn, state)
            cached_plan = sakura_coach.cached_plan_from_state(state)
            insight_count = conn.execute("SELECT COUNT(*) c FROM insights").fetchone()["c"]
        profile_summary = sakura_coach.profile_summary_from_latest(latest)
        return json_response(self, {
            "settings": self._coach_settings_view(state),
            "profile_summary": profile_summary,
            "insight_count": insight_count,
            "needs_refresh": needs_refresh,
            "cached_plan": cached_plan or None,
            "has_key": llm_enabled(),
        })

    def handle_profile_refresh(self) -> None:
        payload = self.read_json()
        want_ai = bool(payload.get("want_ai", True))
        with connect() as conn:
            result = synthesize_profile(conn, want_ai=want_ai)
            save_coach_state(conn, last_profile_at=datetime.now().isoformat(timespec="seconds"))
        return json_response(self, {
            "version": result["version"],
            "profile": result["profile"],
            "created_at": result["created_at"],
        })

    def handle_profile_history(self) -> None:
        with connect() as conn:
            profiles = sakura_profile.load_profile_history(conn)
        return json_response(self, {"profiles": profiles})

    def handle_coach_post(self) -> None:
        payload = self.read_json()
        want_ai = bool(payload.get("want_ai", False))
        with connect() as conn:
            state = get_coach_state(conn)
            # 计划生成前，若有未并入的新洞察则先迭代一次档案
            if self._profile_needs_refresh(conn, state):
                synthesize_profile(conn, want_ai=want_ai)
                state = save_coach_state(conn, last_profile_at=datetime.now().isoformat(timespec="seconds"))
            plan = build_coach_plan(conn, state, want_ai=want_ai)
            save_coach_state(conn, plan_json=json.dumps(plan, ensure_ascii=False), last_plan_at=plan["generated_at"])
        return json_response(self, plan)

    def handle_practice_page(self, batch_id: str) -> None:
        safe_batch = re.sub(r"[^a-fA-F0-9]", "", batch_id)
        if not safe_batch:
            return text_response(self, "Invalid practice batch.", HTTPStatus.BAD_REQUEST)
        html = sakura_practice_pages.render_practice_page(safe_batch)
        return text_response(self, html, content_type="text/html")

    def handle_practice_batch_get(self, batch_id: str) -> None:
        with connect() as conn:
            payload = practice_batch_payload(conn, batch_id)
        if not payload:
            return json_response(self, {"error": "批次不存在"}, 404)
        return json_response(self, payload)

    def handle_practice_feedback(self, batch_id: str, q_id: str) -> None:
        payload = self.read_json()
        try:
            with connect() as conn:
                result = apply_practice_feedback(
                    conn,
                    batch_id,
                    q_id,
                    str(payload.get("status") or ""),
                    str(payload.get("note") or ""),
                )
        except ValueError as exc:
            return json_response(self, {"error": str(exc)}, 400)
        return json_response(self, {"ok": True, "question": result})

    def handle_push_daily(self) -> None:
        payload_in = self.read_json()
        mode = notification_mode_from_payload(payload_in)
        if payload_in.get("scheduled"):
            result = dispatch_scheduled_reminder("daily", mode)
            status = 200 if result["ok"] else 400
            return json_response(self, result, status)
        with connect() as conn:
            reminder = build_daily_reminder(conn)
        result, pdf_result = send_reminder_payload(reminder, mode)
        status = 200 if result["ok"] else 400
        response = reminder_response_payload(
            "daily",
            reminder,
            result,
            mode,
            due_total=reminder.get("due_total", 0),
            days_left=reminder.get("days_left", 0),
            practice_pdf=pdf_result,
        )
        return json_response(self, response, status)

    def handle_push_morning(self) -> None:
        payload_in = self.read_json()
        mode = notification_mode_from_payload(payload_in)
        if payload_in.get("scheduled"):
            result = dispatch_scheduled_reminder("morning", mode)
            status = 200 if result["ok"] else 400
            return json_response(self, result, status)
        with connect() as conn:
            reminder = build_morning_reminder(conn)
        result, pdf_result = send_reminder_payload(reminder, mode)
        status = 200 if result["ok"] else 400
        response = reminder_response_payload("morning", reminder, result, mode, practice_pdf=pdf_result)
        return json_response(self, response, status)

    def handle_push_night(self) -> None:
        payload_in = self.read_json()
        mode = notification_mode_from_payload(payload_in)
        if payload_in.get("scheduled"):
            result = dispatch_scheduled_reminder("night", mode)
            status = 200 if result["ok"] else 400
            return json_response(self, result, status)
        with connect() as conn:
            checked = is_checked_in(conn)
            payload = build_night_check(conn)
        result, _ = send_reminder_payload(payload, mode, attach_pdf=False)
        status = 200 if result["ok"] else 400
        response = reminder_response_payload("night", payload, result, mode, checked_in=checked)
        return json_response(self, response, status)

    def handle_push_weather(self) -> None:
        payload_in = self.read_json()
        mode = notification_mode_from_payload(payload_in)
        if payload_in.get("scheduled"):
            result = dispatch_scheduled_reminder("weather", mode)
            status = 200 if result["ok"] else 400
            return json_response(self, result, status)
        with connect() as conn:
            payload = build_weather_reminder(conn, str(payload_in.get("city", "")).strip() or None)
        result, _ = send_reminder_payload(payload, mode, attach_pdf=False)
        status = 200 if result["ok"] else 400
        response = reminder_response_payload("weather", payload, result, mode, weather=payload["weather"])
        return json_response(self, response, status)

    def handle_today_done(self) -> None:
        with connect() as conn:
            mark_checkin(conn)
        html = sakura_practice_pages.render_today_done_page(APP_PUBLIC_URL)
        return text_response(self, html, content_type="text/html")

    def handle_today_status(self) -> None:
        with connect() as conn:
            checked = is_checked_in(conn)
        return json_response(self, {"date": date.today().isoformat(), "checked_in": checked})

    def handle_export_mistakes(self, query: dict) -> None:
        mistakes_only = next(iter(sakura_filters.query_values(query, "mistakes_only")), "1") != "0"
        with connect() as conn:
            pdf_bytes, count = build_mistakes_pdf(conn, query, mistakes_only=mistakes_only)
        if count == 0:
            return json_response(self, {"error": "当前范围没有可导出的错题。"}, 404)
        filename = f"mistakes_{date.today().isoformat()}_{count}q.pdf"
        download = next(iter(sakura_filters.query_values(query, "download")), "")
        content_type = "application/octet-stream" if download == "1" else "application/pdf"
        return sakura_http.send_attachment_bytes(
            self,
            pdf_bytes,
            filename=filename,
            content_type=content_type,
        )

    def handle_daily_rules_get(self) -> None:
        with connect() as conn:
            rules = load_daily_rules(conn)
        return json_response(self, {"rules": rules})

    def handle_daily_rule_options(self, query: dict) -> None:
        with connect() as conn:
            options = get_daily_rule_options(conn, query)
        return json_response(self, options)

    def handle_daily_rule_save(self) -> None:
        payload = self.read_json()
        with connect() as conn:
            rule = save_daily_rule(conn, payload)
        return json_response(self, {"rule": rule})

    def handle_daily_rule_delete(self, rule_id: str) -> None:
        with connect() as conn:
            deleted = sakura_daily.delete_daily_rule(conn, rule_id)
            if not deleted:
                return json_response(self, {"error": "规则不存在"}, 404)
        return json_response(self, {"ok": True})

    def handle_backup_export(self, query: dict) -> None:
        try:
            tmp_path, filename = sakura_backup.build_backup_export_file(
                query,
                DB_PATH,
                {"uploads": UPLOAD_DIR, "pages": PAGE_DIR},
            )
        except ValueError as exc:
            return json_response(self, {"error": str(exc)}, 400)
        try:
            return sakura_http.stream_attachment_file(
                self,
                tmp_path,
                filename=filename,
                content_type="application/zip",
            )
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass

    def handle_backup_import(self) -> None:
        print("[migration] request received", flush=True)
        form = sakura_http.read_multipart_form(self.headers, self.rfile)
        file_item = sakura_http.first_form_file(form, "backup", "file")
        filename = sakura_http.uploaded_filename(file_item)
        if file_item is None or not filename:
            return json_response(self, {"error": "请上传 Sakura 迁移 ZIP 包。"}, 400)
        if not sakura_http.uploaded_file_has_suffix(file_item, ".zip"):
            return json_response(self, {"error": "迁移导入只支持 .zip 备份包。"}, 400)
        job_id = uuid.uuid4().hex
        upload_dir = DATA_DIR / "migration_uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        sakura_migration.cleanup_stale_uploads(upload_dir)
        upload_path = upload_dir / f"{job_id}.zip"
        with upload_path.open("wb") as out:
            shutil.copyfileobj(file_item.file, out, length=1024 * 1024)
        size = upload_path.stat().st_size
        print(f"[migration] uploaded file: {filename}, {size} bytes, job={job_id}", flush=True)
        now = datetime.now().isoformat(timespec="seconds")
        set_migration_job(
            job_id,
            id=job_id,
            status="queued",
            message="Backup uploaded. Waiting to restore...",
            filename=filename,
            size=size,
            created_at=now,
        )
        worker = threading.Thread(target=run_migration_import_job, args=(job_id, upload_path), daemon=True)
        worker.start()
        return json_response(self, {"ok": True, "job_id": job_id, "status": "queued", "size": size}, 202)

    def handle_backup_import_status(self, query: dict) -> None:
        job_id = (query.get("id") or [""])[0]
        if not job_id:
            return json_response(self, {"error": "Missing import job id."}, 400)
        job = get_migration_job(job_id)
        if not job:
            return json_response(self, {"error": "Import job not found. The service may have restarted."}, 404)
        return json_response(self, job)

    def handle_reflection_history(self) -> None:
        with connect() as conn:
            items = sakura_reflection.list_reflections(conn)
        return json_response(self, {"title": "历史知识归档", "reflections": items})

    def handle_reflection_download(self, ref_id: str) -> None:
        with connect() as conn:
            download = sakura_reflection.build_reflection_download(conn, ref_id)
        if not download:
            return json_response(self, {"error": "反思记录不存在"}, 404)
        filename, text = download
        return sakura_http.send_attachment_bytes(
            self,
            text.encode("utf-8"),
            filename=filename,
            content_type="text/plain; charset=utf-8",
        )

    def handle_daily(self) -> None:
        with connect() as conn:
            payload = build_daily_payload(conn)
            payload["latest_push_batch"] = latest_daily_push_batch_payload(conn)
        return json_response(self, payload)


def main() -> None:
    init_db()
    start_internal_scheduler()
    server = ThreadingHTTPServer((SAKURA_HOST, PORT), DemoHandler)
    shown_host = "127.0.0.1" if SAKURA_HOST in {"", "0.0.0.0", "::"} else SAKURA_HOST
    print(f"Sakura demo running at http://{shown_host}:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
