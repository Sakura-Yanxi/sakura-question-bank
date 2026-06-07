from __future__ import annotations

import json
import hmac
import os
import re
import sqlite3
import shutil
import sys
import tempfile
import threading
import traceback
import uuid
import warnings
from datetime import date, datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import urllib.parse

warnings.filterwarnings("ignore", message="'cgi' is deprecated.*", category=DeprecationWarning)
import cgi

import fitz
from sakura_pdf import (
    PreviousQuestionState,
    crop_image_by_ratio,
    page_range,
    render_page_image,
    save_uploaded_pdf,
)
import sakura_notifications
import sakura_weather
import sakura_reminders
import sakura_config
import sakura_settings
import sakura_ai
import sakura_profile
import sakura_coach
import sakura_migration
import sakura_export
import sakura_backup
import sakura_reflection
import sakura_daily
import sakura_textbook
import sakura_filters
import sakura_documents
import sakura_retention
import sakura_models
import sakura_auth
import sakura_db
import sakura_classify
import sakura_http
import sakura_parse
import sakura_questions
import sakura_insights
import sakura_hints
import sakura_teacher_memory
import sakura_import
import sakura_routes

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
PAGE_DIR = DATA_DIR / "pages"
STATIC_DIR = ROOT / "static"
DB_PATH = DATA_DIR / "gaoshu_demo.sqlite3"

sakura_config.load_local_env(ROOT)

PORT = int(os.getenv("PORT", "8000"))
ADMIN_PASSWORD = os.getenv("SAKURA_ADMIN_PASSWORD") or os.getenv("APP_PASSWORD") or ""
AUTH_SECRET = os.getenv("SAKURA_AUTH_SECRET") or os.getenv("APP_SECRET") or ""
AUTH_COOKIE_NAME = "sakura_session"
AUTH_MAX_AGE_SECONDS = 60 * 60 * 24 * 14

# === AI 接口（OpenAI 兼容）===
# 默认接入小米 MiMo 开放平台（https://platform.xiaomimimo.com 申请 Key）。
# 也可用环境变量切换到 DeepSeek 或任意 OpenAI 兼容端点，无需改代码。
# 密钥优先级：LLM_API_KEY > MIMO_API_KEY > DEEPSEEK_API_KEY（向后兼容旧配置）。
LLM_API_KEY = os.getenv("LLM_API_KEY") or os.getenv("MIMO_API_KEY") or os.getenv("DEEPSEEK_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL") or os.getenv("DEEPSEEK_BASE_URL") or "https://api.xiaomimimo.com/v1"
LLM_MODEL = os.getenv("LLM_MODEL") or os.getenv("DEEPSEEK_MODEL") or "mimo-v2.5-pro"

# === 微信推送（PushPlus）===
# 在 https://www.pushplus.plus 用微信扫码登录，复制 token 后设环境变量 PUSHPLUS_TOKEN。
PUSHPLUS_TOKEN = os.getenv("PUSHPLUS_TOKEN", "")
WEWORK_BOT_WEBHOOK = os.getenv("WEWORK_BOT_WEBHOOK", "")
# 推送正文里的“打开做题集”链接（部署到公网后改成你的域名/IP）
APP_PUBLIC_URL = os.getenv("APP_PUBLIC_URL", "http://127.0.0.1:8000")
WEATHER_CITY = os.getenv("WEATHER_CITY", "北京")
REMIND_MORNING_ON = os.getenv("REMIND_MORNING_ON", "1")
REMIND_MORNING_TIME = os.getenv("REMIND_MORNING_TIME", "10:00")
REMIND_NIGHT_ON = os.getenv("REMIND_NIGHT_ON", "1")
REMIND_NIGHT_TIME = os.getenv("REMIND_NIGHT_TIME", "20:00")
REMIND_WEATHER_ON = os.getenv("REMIND_WEATHER_ON", "1")
REMIND_WEATHER_TIME = os.getenv("REMIND_WEATHER_TIME", "22:30")
REMIND_CHECKIN_MODE = os.getenv("REMIND_CHECKIN_MODE", "cloud")
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
    absolute = Path(path).resolve()
    return "/" + absolute.relative_to(ROOT).as_posix()


def extract_question_no(text: str) -> str:
    return sakura_models.extract_question_no(text)


def row_to_dict(row: sqlite3.Row) -> dict:
    return sakura_models.row_to_dict(
        row,
        to_public_path=to_public_path,
        normalize_document_kind=normalize_document_kind,
        normalize_meta_tags=normalize_meta_tags,
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
    return sakura_settings.llm_settings_view(LLM_API_KEY, LLM_BASE_URL, LLM_MODEL)


def notification_settings_view() -> dict:
    return sakura_settings.notification_settings_view(WEWORK_BOT_WEBHOOK, PUSHPLUS_TOKEN, APP_PUBLIC_URL)


def update_llm_runtime_settings(api_key: str | None = None, base_url: str | None = None, model: str | None = None) -> dict:
    global LLM_API_KEY, LLM_BASE_URL, LLM_MODEL
    updates = {}
    if api_key is not None and api_key.strip():
        LLM_API_KEY = api_key.strip()
        os.environ["LLM_API_KEY"] = LLM_API_KEY
        updates["LLM_API_KEY"] = LLM_API_KEY
    if base_url is not None and base_url.strip():
        LLM_BASE_URL = base_url.strip().rstrip("/")
        os.environ["LLM_BASE_URL"] = LLM_BASE_URL
        updates["LLM_BASE_URL"] = LLM_BASE_URL
    if model is not None and model.strip():
        LLM_MODEL = model.strip()
        os.environ["LLM_MODEL"] = LLM_MODEL
        updates["LLM_MODEL"] = LLM_MODEL
    if updates:
        sakura_config.write_local_env(ROOT, updates)
    return llm_settings_view()


def update_notification_runtime_settings(
    wework_webhook: str | None = None,
    pushplus_token: str | None = None,
    app_public_url: str | None = None,
) -> dict:
    global WEWORK_BOT_WEBHOOK, PUSHPLUS_TOKEN, APP_PUBLIC_URL
    updates = {}
    if wework_webhook is not None and wework_webhook.strip():
        WEWORK_BOT_WEBHOOK = wework_webhook.strip()
        os.environ["WEWORK_BOT_WEBHOOK"] = WEWORK_BOT_WEBHOOK
        updates["WEWORK_BOT_WEBHOOK"] = WEWORK_BOT_WEBHOOK
    if pushplus_token is not None and pushplus_token.strip():
        PUSHPLUS_TOKEN = pushplus_token.strip()
        os.environ["PUSHPLUS_TOKEN"] = PUSHPLUS_TOKEN
        updates["PUSHPLUS_TOKEN"] = PUSHPLUS_TOKEN
    if app_public_url is not None and app_public_url.strip():
        APP_PUBLIC_URL = app_public_url.strip().rstrip("/")
        os.environ["APP_PUBLIC_URL"] = APP_PUBLIC_URL
        updates["APP_PUBLIC_URL"] = APP_PUBLIC_URL
    if updates:
        sakura_config.write_local_env(ROOT, updates)
    return notification_settings_view()


def normalize_public_url(value: str) -> str:
    return sakura_settings.normalize_public_url(value)


def reminder_settings_view(cron_status: dict | None = None) -> dict:
    return sakura_reminders.ReminderSettings(
        morning_on=REMIND_MORNING_ON,
        morning_time=REMIND_MORNING_TIME,
        night_on=REMIND_NIGHT_ON,
        night_time=REMIND_NIGHT_TIME,
        weather_on=REMIND_WEATHER_ON,
        weather_time=REMIND_WEATHER_TIME,
        checkin_mode=REMIND_CHECKIN_MODE,
    ).as_payload(cron_status)


def update_reminder_runtime_settings(payload: dict) -> dict:
    global REMIND_MORNING_ON, REMIND_MORNING_TIME, REMIND_NIGHT_ON, REMIND_NIGHT_TIME
    global REMIND_WEATHER_ON, REMIND_WEATHER_TIME, REMIND_CHECKIN_MODE
    current = sakura_reminders.ReminderSettings(
        morning_on=REMIND_MORNING_ON,
        morning_time=REMIND_MORNING_TIME,
        night_on=REMIND_NIGHT_ON,
        night_time=REMIND_NIGHT_TIME,
        weather_on=REMIND_WEATHER_ON,
        weather_time=REMIND_WEATHER_TIME,
        checkin_mode=REMIND_CHECKIN_MODE,
    )
    settings = sakura_reminders.merge_settings(current, payload)
    REMIND_MORNING_ON = settings.morning_on
    REMIND_MORNING_TIME = settings.morning_time
    REMIND_NIGHT_ON = settings.night_on
    REMIND_NIGHT_TIME = settings.night_time
    REMIND_WEATHER_ON = settings.weather_on
    REMIND_WEATHER_TIME = settings.weather_time
    REMIND_CHECKIN_MODE = settings.checkin_mode
    updates = settings.as_env()
    for key, value in updates.items():
        os.environ[key] = value
    sakura_config.write_local_env(ROOT, updates)
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
    rows = conn.execute(
        """
        SELECT d.subject, d.document_kind, COALESCE(NULLIF(d.title, ''), d.filename) document_title, q.document_id,
               q.chapter, q.category,
               SUM(CASE WHEN q.status = '做对' THEN 1 ELSE 0 END) correct,
               SUM(CASE WHEN q.status IN ('做对', '做错', '半会', '需复习') THEN 1 ELSE 0 END) done
        FROM questions q
        JOIN documents d ON d.id = q.document_id
        GROUP BY d.subject, d.document_kind, document_title, q.document_id, q.chapter, q.category
        HAVING done >= 2 AND (correct * 1.0 / done) < 0.5
        """
    ).fetchall()
    mapping: dict[str, list[str]] = {}
    for row in rows:
        deps = []
        for key in (row["category"], row["chapter"]):
            deps.extend(KNOWLEDGE_DEPENDENCIES.get(key, []))
        if deps:
            group_key = f"{row['subject'] or DEFAULT_SUBJECT} / {row['document_kind'] or DEFAULT_DOCUMENT_KIND} / {row['document_title'] or '做题本'}"
            mapping.setdefault(group_key, [])
            for dep in deps:
                if dep not in mapping[group_key]:
                    mapping[group_key].append(dep)
    return mapping


def find_foundation_questions(conn: sqlite3.Connection, subject: str, dependency_categories: list[str], exclude_ids: set[str]) -> list[dict]:
    if not dependency_categories:
        return []
    placeholders = ",".join("?" for _ in dependency_categories)
    params = [subject, *dependency_categories]
    rows = conn.execute(
        f"""
        SELECT q.*, d.filename, d.title document_title, d.subject, d.document_kind
        FROM questions q
        JOIN documents d ON d.id = q.document_id
        WHERE d.subject = ?
          AND q.category IN ({placeholders})
          AND q.id NOT IN ({",".join("?" for _ in exclude_ids) if exclude_ids else "''"})
        ORDER BY
          CASE q.status WHEN '未做' THEN 0 WHEN '做对' THEN 1 ELSE 2 END,
          q.created_at ASC,
          q.page_number ASC
        LIMIT 3
        """,
        params + list(exclude_ids),
    ).fetchall()
    return [row_to_dict(row) | {"daily_kind": "foundation"} for row in rows]


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


def load_teacher_memories(conn: sqlite3.Connection, limit: int = 10) -> list[dict]:
    return sakura_teacher_memory.load_teacher_memories(conn, limit)


def save_teacher_memory(conn: sqlite3.Connection, content: str, source: str = "chat") -> dict:
    return sakura_teacher_memory.save_teacher_memory(conn, content, source)


def teacher_memory_prompt(conn: sqlite3.Connection) -> str:
    return sakura_teacher_memory.teacher_memory_prompt(conn)


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


def send_notification(title: str, content: str) -> dict:
    return sakura_notifications.send_notification(
        title,
        content,
        wework_webhook=WEWORK_BOT_WEBHOOK,
        pushplus_token=PUSHPLUS_TOKEN,
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


def build_mistakes_pdf(conn: sqlite3.Connection, query: dict, mistakes_only: bool = True) -> tuple[bytes, int]:
    return sakura_export.build_filtered_mistakes_pdf(
        conn,
        query,
        mistakes_only=mistakes_only,
        build_question_filters=build_question_filters,
        normalize_meta_tags=normalize_meta_tags,
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
    )


def create_practice_batch(conn: sqlite3.Connection, source: str = "push") -> dict:
    return sakura_daily.create_practice_batch(conn, build_daily_payload, source)


def practice_batch_payload(conn: sqlite3.Connection, batch_id: str) -> dict | None:
    return sakura_daily.practice_batch_payload(conn, batch_id, row_to_dict)


def apply_practice_feedback(conn: sqlite3.Connection, batch_id: str, q_id: str, status: str, note: str = "") -> dict:
    return sakura_daily.apply_practice_feedback(
        conn,
        batch_id,
        q_id,
        status,
        note,
        normalize_label,
        schedule_for_status,
        row_to_dict,
    )


def split_textbook_paragraphs(text: str) -> list[str]:
    return sakura_textbook.split_textbook_paragraphs(text)


def textbook_to_dict(row: sqlite3.Row) -> dict:
    return sakura_textbook.textbook_to_dict(row)


def textbook_page_to_dict(row: sqlite3.Row) -> dict:
    return sakura_textbook.textbook_page_to_dict(row, to_public_path)


def import_textbook_pdf(filename: str, pdf_bytes: bytes, title: str = "", subject: str = "") -> dict:
    return sakura_textbook.import_textbook_pdf(
        filename,
        pdf_bytes,
        title=title,
        subject=subject,
        upload_dir=UPLOAD_DIR,
        page_dir=PAGE_DIR,
        connect=connect,
        render_page_image=render_page_image,
        normalize_label=normalize_label,
        default_subject=DEFAULT_SUBJECT,
    )


def build_textbook_context(conn: sqlite3.Connection, textbook_id: str, page_number: int, paragraph_index: int = 0) -> tuple[dict, dict]:
    return sakura_textbook.build_textbook_context(
        conn,
        textbook_id,
        page_number,
        paragraph_index,
        to_public_path=to_public_path,
    )


def explain_textbook_with_ai(book: dict, page: dict, message: str, history: list[dict]) -> str:
    return sakura_textbook.explain_textbook(
        book,
        page,
        message,
        history,
        llm_enabled=llm_enabled(),
        call_llm_messages=call_llm_messages,
    )


def extract_text_and_chapters(pdf_path: Path, document_kind: str = DEFAULT_DOCUMENT_KIND) -> list[dict]:
    return sakura_classify.extract_text_and_chapters(
        pdf_path,
        document_kind,
        default_chapter=DEFAULT_CHAPTER,
        mock_paper_kind=MOCK_PAPER_KIND,
        mock_paper_chapter=MOCK_PAPER_CHAPTER,
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
    doc_id = uuid.uuid4().hex
    pdf_path = save_uploaded_pdf(UPLOAD_DIR, doc_id, filename, pdf_bytes)
    metadata = sakura_documents.import_metadata(
        filename=filename,
        title=title,
        subject=subject,
        document_kind=document_kind,
        normalize_label=normalize_label,
        normalize_document_kind=normalize_document_kind,
        default_subject=DEFAULT_SUBJECT,
    )
    title = metadata["title"]
    subject = metadata["subject"]
    document_kind = metadata["document_kind"]

    now = datetime.now().isoformat(timespec="seconds")
    inserted = []
    pdf = fitz.open(pdf_path)
    chapters = new_chapter_state()
    try:
        with connect() as conn:
            sakura_documents.insert_document(
                conn,
                doc_id=doc_id,
                title=title,
                subject=subject,
                document_kind=document_kind,
                filename=filename,
                stored_path=pdf_path,
                page_count=pdf.page_count,
                created_at=now,
            )
            page_start, page_end = page_range(pdf.page_count, start_page, end_page)
            seq_no = 0
            previous_question = PreviousQuestionState()
            for index in range(page_start, page_end + 1):
                page = pdf[index - 1]
                seq_no, page_inserted = sakura_import.process_import_page(
                    conn,
                    page=page,
                    page_dir=PAGE_DIR,
                    doc_id=doc_id,
                    page_number=index,
                    seq_no=seq_no,
                    subject=subject,
                    document_kind=document_kind,
                    split_questions=split_questions,
                    chapters=chapters,
                    previous_question=previous_question,
                    created_at=now,
                    default_chapter=DEFAULT_CHAPTER,
                    mock_paper_kind=MOCK_PAPER_KIND,
                    mock_paper_chapter=MOCK_PAPER_CHAPTER,
                    classify_question=classify_question_locally,
                )
                inserted.extend(page_inserted)
    finally:
        pdf.close()

    return sakura_documents.imported_document_payload(
        doc_id=doc_id,
        title=title,
        subject=subject,
        document_kind=document_kind,
        filename=filename,
        questions=inserted,
    )


def unlink_if_inside_data(path_value: str) -> None:
    sakura_documents.unlink_if_inside(DATA_DIR, path_value)


def prune_empty_documents(conn: sqlite3.Connection) -> int:
    return sakura_documents.prune_empty_documents(conn, data_dir=DATA_DIR)


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
    server_version = "GaoshuDemo/0.1"

    def log_message(self, format: str, *args) -> None:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {format % args}")

    def is_public_path(self, path: str) -> bool:
        return (
            path in {"/login", "/api/health"}
            or path.startswith("/practice/")
            or path.startswith("/api/practice/")
        )

    def get_cookie(self, name: str) -> str:
        for part in (self.headers.get("Cookie") or "").split(";"):
            if "=" not in part:
                continue
            key, value = part.strip().split("=", 1)
            if key == name:
                return urllib.parse.unquote(value)
        return ""

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
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8") if length else ""
        fields = parse_qs(raw)
        password = fields.get("password", [""])[0]
        if not auth_enabled():
            return redirect_response(self, "/")
        if not hmac.compare_digest(password, ADMIN_PASSWORD):
            return text_response(self, login_page("密码不正确，请重新输入。"), HTTPStatus.UNAUTHORIZED, "text/html")
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
                return json_response(self, {"ok": True, "date": date.today().isoformat()})
            route = sakura_routes.route_for(parsed.path, sakura_routes.GET_ROUTES)
            if route:
                handler = getattr(self, route.handler)
                if route.with_query:
                    return handler(parse_qs(parsed.query))
                return handler()
            if parsed.path.startswith("/api/textbooks/") and "/pages/" in parsed.path:
                parts = parsed.path.split("/")
                return self.handle_textbook_page(parts[3], int(parts[5]))
            if parsed.path.startswith("/api/documents/") and parsed.path.endswith("/chapter-stats"):
                doc_id = parsed.path.split("/")[-2]
                return self.handle_chapter_stats(doc_id)
            if parsed.path.startswith("/api/practice/"):
                batch_id = parsed.path.split("/")[-1]
                return self.handle_practice_batch_get(batch_id)
            if parsed.path.startswith("/api/reflections/") and parsed.path.endswith("/download"):
                ref_id = parsed.path.split("/")[-2]
                return self.handle_reflection_download(ref_id)
            if parsed.path.startswith("/api/questions/"):
                q_id = parsed.path.split("/")[-1]
                return self.handle_question_detail(q_id)
            if parsed.path.startswith("/static/") or parsed.path.startswith("/data/"):
                return self.serve_file(ROOT / parsed.path.lstrip("/"))
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
            route = sakura_routes.route_for(parsed.path, sakura_routes.POST_ROUTES)
            if route:
                return getattr(self, route.handler)()
            if parsed.path.startswith("/api/documents/") and parsed.path.endswith("/rescan-chapters"):
                doc_id = parsed.path.split("/")[-2]
                return self.handle_rescan_chapters(doc_id)
            if parsed.path.startswith("/api/questions/") and parsed.path.endswith("/analyze"):
                q_id = parsed.path.split("/")[-2]
                return self.handle_analyze(q_id)
            if parsed.path.startswith("/api/questions/") and parsed.path.endswith("/hint"):
                q_id = parsed.path.split("/")[-2]
                return self.handle_hint(q_id)
            if parsed.path.startswith("/api/questions/") and parsed.path.endswith("/variations"):
                q_id = parsed.path.split("/")[-2]
                return self.handle_variations(q_id)
            if parsed.path.startswith("/api/questions/") and parsed.path.endswith("/crop"):
                q_id = parsed.path.split("/")[-2]
                return self.handle_crop_question(q_id)
            if parsed.path.startswith("/api/practice/") and "/questions/" in parsed.path:
                parts = parsed.path.strip("/").split("/")
                return self.handle_practice_feedback(parts[2], parts[4])
            return text_response(self, "Not found", HTTPStatus.NOT_FOUND)
        except Exception as exc:
            traceback.print_exc()
            return json_response(self, {"error": str(exc)}, 500)

    def do_DELETE(self) -> None:
        try:
            parsed = urlparse(self.path)
            if not self.require_auth(parsed.path):
                return
            route = sakura_routes.route_for(parsed.path, sakura_routes.DELETE_ROUTES)
            if route:
                return getattr(self, route.handler)()
            if parsed.path.startswith("/api/textbooks/"):
                book_id = parsed.path.split("/")[-1]
                return self.handle_delete_textbook(book_id)
            if parsed.path.startswith("/api/documents/"):
                doc_id = parsed.path.split("/")[-1]
                return self.handle_delete_document(doc_id)
            if parsed.path.startswith("/api/questions/"):
                q_id = parsed.path.split("/")[-1]
                return self.handle_delete_question(q_id)
            if parsed.path.startswith("/api/reflections/"):
                ref_id = parsed.path.split("/")[-1]
                return self.handle_delete_reflection(ref_id)
            if parsed.path.startswith("/api/daily/rules/"):
                rule_id = parsed.path.split("/")[-1]
                return self.handle_daily_rule_delete(rule_id)
            if parsed.path.startswith("/api/ai-chat/memory/"):
                memory_id = parsed.path.split("/")[-1]
                return self.handle_ai_memory_delete(memory_id)
            if parsed.path.startswith("/api/mentor-experience/"):
                exp_id = parsed.path.split("/")[-1]
                return self.handle_mentor_experience_delete(exp_id)
            return text_response(self, "Not found", HTTPStatus.NOT_FOUND)
        except Exception as exc:
            traceback.print_exc()
            return json_response(self, {"error": str(exc)}, 500)

    def do_PATCH(self) -> None:
        try:
            parsed = urlparse(self.path)
            if not self.require_auth(parsed.path):
                return
            if parsed.path.startswith("/api/documents/"):
                doc_id = parsed.path.split("/")[-1]
                return self.handle_update_document(doc_id)
            if parsed.path.startswith("/api/questions/"):
                q_id = parsed.path.split("/")[-1]
                return self.handle_update_question(q_id)
            return text_response(self, "Not found", HTTPStatus.NOT_FOUND)
        except Exception as exc:
            traceback.print_exc()
            return json_response(self, {"error": str(exc)}, 500)

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def serve_file(self, path: Path) -> None:
        return sakura_http.serve_file(self, path, ROOT)

    def handle_upload(self) -> None:
        form = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ={"REQUEST_METHOD": "POST"})
        file_item = form["file"] if "file" in form else None
        if file_item is None or not file_item.filename:
            return json_response(self, {"error": "请上传 PDF 文件。"}, 400)
        if not file_item.filename.lower().endswith(".pdf"):
            return json_response(self, {"error": "当前 demo 只支持 PDF。"}, 400)
        title = form.getfirst("title", "")
        subject = form.getfirst("subject", "")
        document_kind = form.getfirst("document_kind", DEFAULT_DOCUMENT_KIND)
        start_page = parse_positive_int(form.getfirst("start_page", ""), None)
        end_page = parse_positive_int(form.getfirst("end_page", ""), None)
        split_questions = sakura_parse.bool_flag(form.getfirst("split_questions", ""))
        result = import_pdf(file_item.filename, file_item.file.read(), title, subject, document_kind, start_page, end_page, split_questions)
        return json_response(self, result)

    def handle_textbook_upload(self) -> None:
        form = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ={"REQUEST_METHOD": "POST"})
        file_item = form["file"] if "file" in form else None
        if file_item is None or not file_item.filename:
            return json_response(self, {"error": "请上传教材 PDF。"}, 400)
        if not file_item.filename.lower().endswith(".pdf"):
            return json_response(self, {"error": "教材精读目前只支持 PDF。"}, 400)
        title = form.getfirst("title", "")
        subject = form.getfirst("subject", "")
        result = import_textbook_pdf(file_item.filename, file_item.file.read(), title, subject)
        return json_response(self, result)

    def handle_textbooks(self) -> None:
        with connect() as conn:
            rows = sakura_textbook.load_textbooks(conn)
        return json_response(self, {"textbooks": [textbook_to_dict(row) for row in rows]})

    def handle_textbook_page(self, textbook_id: str, page_number: int) -> None:
        with connect() as conn:
            book, page = build_textbook_context(conn, textbook_id, page_number)
        return json_response(self, {"textbook": book, "page": page})

    def handle_delete_textbook(self, textbook_id: str) -> None:
        with connect() as conn:
            deleted = sakura_textbook.delete_textbook(conn, textbook_id, delete_file=unlink_if_inside_data)
            if not deleted:
                return json_response(self, {"error": "教材不存在。"}, 404)
        return json_response(self, {"ok": True})

    def handle_textbook_chat(self) -> None:
        request = sakura_textbook.parse_textbook_request(self.read_json(), parse_positive_int=parse_positive_int)
        textbook_id = request["textbook_id"]
        page_number = request["page_number"]
        paragraph_index = request["paragraph_index"]
        message = request["message"]
        history = request["history"]
        if not textbook_id or not message:
            return json_response(self, {"error": "请选择教材并输入问题。"}, 400)
        with connect() as conn:
            book, page = build_textbook_context(conn, textbook_id, page_number, paragraph_index)
            sakura_textbook.save_textbook_chat_message(
                conn,
                textbook_id=textbook_id,
                page_number=page_number,
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
                page_number=page_number,
                role="assistant",
                content=answer,
                content_limit=8000,
            )
        return json_response(self, {"answer": answer, "textbook": book, "page": page, "has_key": llm_enabled()})

    def handle_textbook_memory(self) -> None:
        request = sakura_textbook.parse_textbook_request(self.read_json(), parse_positive_int=parse_positive_int)
        textbook_id = request["textbook_id"]
        page_number = request["page_number"]
        paragraph_index = request["paragraph_index"]
        history = request["history"]
        if not textbook_id:
            return json_response(self, {"error": "请选择教材。"}, 400)
        with connect() as conn:
            book, page = build_textbook_context(conn, textbook_id, page_number, paragraph_index)
            selected = page.get("selected_paragraph") or "未指定"
            if llm_enabled() and history:
                prompt = (
                    "请把下面教材精读对话压缩成一条长期学习记忆，100-180字，包含教材、页码、困惑、关键理解和后续复习建议。\n"
                    f"教材：{book.get('title')}；页码：{page_number}；段落：{selected}\n"
                    + json.dumps(history[-10:], ensure_ascii=False)
                )
                try:
                    content = call_llm(prompt, temperature=0.2)
                except Exception:
                    traceback.print_exc()
                    content = ""
            else:
                last_user = next((item.get("content", "") for item in reversed(history) if item.get("role") == "user"), "")
                content = f"教材精读：{book.get('title')} 第{page_number}页。困惑：{last_user or '未记录'}。关键段落：{selected[:160]}。后续复习时优先回看该页概念与例题。"
            memory = save_teacher_memory(conn, content, "textbook")
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
            ("category", "status", "document_id", "chapter", "subject", "search"),
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
        return json_response(self, row_to_dict(row))

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
            except sakura_questions.QuestionUpdateError as exc:
                return json_response(self, {"error": str(exc)}, exc.status)
        return json_response(self, row_to_dict(row))

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
        with connect() as conn:
            row = sakura_questions.load_question_for_ai(conn, q_id)
            if not row:
                return json_response(self, {"error": "题目不存在。"}, 404)
            hint = generate_hint_with_ai(question_payload(row), level)
            conn.execute("UPDATE questions SET ai_hint = ? WHERE id = ?", (hint, q_id))
        return json_response(self, {"level": level, "hint": hint})

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

    def handle_ai_memory_get(self) -> None:
        with connect() as conn:
            memories = load_teacher_memories(conn, limit=30)
        return json_response(self, {
            "memories": memories,
            **llm_settings_view(),
        })

    def handle_llm_settings_get(self) -> None:
        return json_response(self, llm_settings_view())

    def handle_llm_settings_post(self) -> None:
        payload = self.read_json()
        api_key = str(payload.get("api_key", "")).strip()
        base_url = str(payload.get("base_url", "")).strip()
        model = str(payload.get("model", "")).strip()
        if not any([api_key, base_url, model]):
            return json_response(self, {"error": "至少填写 API Key、Base URL 或模型名中的一项"}, 400)
        settings = update_llm_runtime_settings(
            api_key=api_key or None,
            base_url=base_url or None,
            model=model or None,
        )
        return json_response(self, {
            **settings,
            "message": "已保存到本地 .env，并已更新当前运行中的服务。",
        })

    def handle_notification_settings_get(self) -> None:
        return json_response(self, notification_settings_view())

    def handle_reminder_settings_get(self) -> None:
        return json_response(self, reminder_settings_view())

    def handle_reminder_settings_post(self) -> None:
        settings = update_reminder_runtime_settings(self.read_json())
        return json_response(self, {
            **settings,
            "message": settings.get("cron", {}).get("message") or "提醒时间已保存。",
        })

    def handle_notification_settings_post(self) -> None:
        payload = self.read_json()
        wework_webhook = str(payload.get("wework_webhook", "")).strip()
        pushplus_token = str(payload.get("pushplus_token", "")).strip()
        app_public_url = str(payload.get("app_public_url", "")).strip()
        if not any([wework_webhook, pushplus_token, app_public_url]):
            return json_response(self, {"error": "至少填写企业微信 Webhook、PushPlus Token 或公网地址中的一项"}, 400)
        try:
            normalized_public_url = normalize_public_url(app_public_url) if app_public_url else None
        except ValueError as exc:
            return json_response(self, {"error": str(exc)}, 400)
        settings = update_notification_runtime_settings(
            wework_webhook=wework_webhook or None,
            pushplus_token=pushplus_token or None,
            app_public_url=normalized_public_url,
        )
        return json_response(self, {
            **settings,
            "message": "已保存到本地 .env，并已更新当前运行中的推送配置。",
        })

    def handle_ai_memory_post(self) -> None:
        payload = self.read_json()
        try:
            with connect() as conn:
                memory = save_teacher_memory(conn, str(payload.get("content", "")), str(payload.get("source", "chat")))
        except ValueError as exc:
            return json_response(self, {"error": str(exc)}, 400)
        return json_response(self, {"memory": memory})

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
            turn = sakura_ai.build_teacher_chat_turn(message, context, call_llm_messages=call_llm_messages)
        except Exception as exc:
            traceback.print_exc()
            return json_response(self, {"error": f"AI 调用失败：{exc}", "has_key": True}, 500)
        with connect() as conn:
            sakura_teacher_memory.save_teacher_turn(
                conn,
                message=message,
                intent=turn["intent"],
                strategy=turn["strategy"],
                context=context,
                answer=turn["answer"],
                memory_candidate=turn["memory_candidate"],
            )
        return json_response(self, {
            "answer": turn["answer"],
            "has_key": True,
            "model": LLM_MODEL,
            "base_url": LLM_BASE_URL,
            "teacher_intent": turn["intent"],
            "teacher_strategy": turn["strategy"],
            "memory_candidate": turn["memory_candidate"],
        })

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
        html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Sakura 快速回填</title>
  <style>
    :root {{ --pink:#ec4899; --green:#10b981; --red:#ef4444; --amber:#f59e0b; --ink:#172033; --muted:#718096; --line:#eadde7; --bg:#fff7fb; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; color:var(--ink); background:linear-gradient(180deg,#fff 0%,var(--bg) 100%); }}
    header {{ position:sticky; top:0; z-index:3; padding:14px 16px; background:rgba(255,255,255,.92); backdrop-filter:blur(14px); border-bottom:1px solid var(--line); }}
    h1 {{ margin:0; font-size:20px; }}
    .sub {{ margin-top:6px; color:var(--muted); font-size:13px; }}
    .progress {{ margin-top:10px; height:8px; background:#f3e8ef; border-radius:999px; overflow:hidden; }}
    .bar {{ height:100%; width:0%; background:linear-gradient(90deg,var(--pink),#f472b6); transition:.2s; }}
    main {{ padding:14px; max-width:760px; margin:0 auto; }}
    .card {{ background:#fff; border:1px solid var(--line); border-radius:18px; margin:0 0 14px; overflow:hidden; box-shadow:0 10px 28px rgba(236,72,153,.08); }}
    .qhead {{ display:flex; justify-content:space-between; gap:10px; padding:12px 14px; border-bottom:1px solid #f3e8ef; }}
    .qhead strong {{ font-size:16px; }}
    .qhead span {{ color:var(--muted); font-size:12px; text-align:right; }}
    .image-wrap {{ padding:10px; background:#fbfafc; }}
    img {{ width:100%; display:block; border-radius:12px; border:1px solid #eee; background:#fff; }}
    .meta {{ padding:0 14px 10px; display:flex; flex-wrap:wrap; gap:8px; }}
    .tag {{ border-radius:999px; padding:5px 9px; font-size:12px; background:#f8eaf2; color:#9d174d; }}
    textarea {{ width:calc(100% - 28px); margin:0 14px 12px; min-height:64px; resize:vertical; border:1px solid var(--line); border-radius:12px; padding:10px; font:inherit; }}
    .actions {{ display:grid; grid-template-columns:repeat(3,1fr); gap:8px; padding:0 14px 14px; }}
    button {{ border:0; border-radius:13px; padding:12px 8px; font-weight:800; color:#fff; font-size:15px; }}
    .ok {{ background:var(--green); }} .bad {{ background:var(--red); }} .half {{ background:var(--amber); }}
    .done {{ outline:3px solid rgba(16,185,129,.25); }}
    .empty {{ padding:40px 18px; text-align:center; color:var(--muted); }}
    .toast {{ position:fixed; left:16px; right:16px; bottom:18px; padding:12px 14px; background:#172033; color:#fff; border-radius:14px; opacity:0; transform:translateY(12px); transition:.2s; text-align:center; }}
    .toast.show {{ opacity:1; transform:translateY(0); }}
    a {{ color:var(--pink); font-weight:800; }}
  </style>
</head>
<body>
  <header>
    <h1>Sakura 快速回填</h1>
    <div class="sub" id="summary">正在读取本次推送...</div>
    <div class="progress"><div class="bar" id="bar"></div></div>
  </header>
  <main id="list"></main>
  <div class="toast" id="toast"></div>
  <script>
    const batchId = "{safe_batch}";
    const list = document.getElementById("list");
    const summary = document.getElementById("summary");
    const bar = document.getElementById("bar");
    const toast = document.getElementById("toast");
    let state = null;
    function esc(s) {{ return String(s ?? "").replace(/[&<>"']/g, c => ({{"&":"&amp;","<":"&lt;",">":"&gt;","\\\"":"&quot;","'":"&#39;"}}[c])); }}
    function showToast(text) {{ toast.textContent = text; toast.classList.add("show"); setTimeout(() => toast.classList.remove("show"), 1500); }}
    async function load() {{
      const res = await fetch(`/api/practice/${{batchId}}`);
      if (!res.ok) {{ list.innerHTML = '<div class="empty">这个批次不存在或已失效。</div>'; return; }}
      state = await res.json();
      render();
    }}
    function render() {{
      const b = state.batch;
      const qs = state.questions || [];
      summary.textContent = `${{b.day}} · 已回填 ${{b.done_count}}/${{b.question_count}} 道`;
      bar.style.width = b.question_count ? `${{Math.round(b.done_count / b.question_count * 100)}}%` : "0%";
      list.innerHTML = qs.map(q => `
        <article class="card ${{q.quick_status ? "done" : ""}}" id="q-${{q.id}}">
          <div class="qhead">
            <strong>第 ${{q.batch_position}} 题 · ${{esc(q.category || "待归类")}}</strong>
            <span>${{esc(q.subject || "")}}<br>${{esc(q.document_title || q.filename || "")}}</span>
          </div>
          <div class="image-wrap"><img src="${{q.image_url}}" alt="题目图" loading="lazy"></div>
          <div class="meta">
            <span class="tag">当前：${{esc(q.status || "未做")}}</span>
            <span class="tag">${{esc(q.chapter || "未识别章节")}}</span>
            ${{q.quick_status ? `<span class="tag">已回填：${{esc(q.quick_status)}}</span>` : ""}}
          </div>
          <textarea data-note="${{q.id}}" placeholder="可选：一句话备注，电脑端之后可详细复盘">${{esc(q.quick_note || "")}}</textarea>
          <div class="actions">
            <button class="ok" data-id="${{q.id}}" data-status="做对">做对</button>
            <button class="bad" data-id="${{q.id}}" data-status="做错">做错</button>
            <button class="half" data-id="${{q.id}}" data-status="半会">半会</button>
          </div>
        </article>`).join("") || '<div class="empty">本次推送没有题目。<br><a href="/">回到做题集</a></div>';
    }}
    list.addEventListener("click", async (event) => {{
      const btn = event.target.closest("button[data-id]");
      if (!btn) return;
      btn.disabled = true;
      const id = btn.dataset.id;
      const noteEl = document.querySelector(`[data-note="${{id}}"]`);
      const note = noteEl ? noteEl.value : "";
      try {{
        const res = await fetch(`/api/practice/${{batchId}}/questions/${{id}}`, {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify({{ status: btn.dataset.status, note }})
        }});
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "保存失败");
        showToast(`已保存：${{btn.dataset.status}}`);
        await load();
      }} catch (e) {{
        showToast(e.message);
      }} finally {{
        btn.disabled = false;
      }}
    }});
    load();
  </script>
</body>
</html>"""
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
        with connect() as conn:
            reminder = build_daily_reminder(conn)
        result = send_notification(reminder["title"], reminder["content"])
        status = 200 if result["ok"] else 400
        return json_response(self, {
            "ok": result["ok"],
            "title": reminder["title"],
            "due_total": reminder["due_total"],
            "days_left": reminder["days_left"],
            "batch_id": reminder.get("batch_id", ""),
            "practice_url": reminder.get("practice_url", ""),
            "detail": result.get("detail") or result.get("resp") or result.get("error"),
            "configured": result.get("configured", bool(PUSHPLUS_TOKEN or WEWORK_BOT_WEBHOOK)),
        }, status)

    def handle_push_morning(self) -> None:
        with connect() as conn:
            reminder = build_morning_reminder(conn)
        result = send_notification(reminder["title"], reminder["content"])
        status = 200 if result["ok"] else 400
        return json_response(self, {
            "ok": result["ok"], "kind": "morning", "title": reminder["title"],
            "batch_id": reminder.get("batch_id", ""), "practice_url": reminder.get("practice_url", ""),
            "detail": result.get("detail") or result.get("resp") or result.get("error"),
            "configured": result.get("configured", bool(PUSHPLUS_TOKEN or WEWORK_BOT_WEBHOOK)),
        }, status)

    def handle_push_night(self) -> None:
        with connect() as conn:
            checked = is_checked_in(conn)
            payload = build_night_check(conn)
        result = send_notification(payload["title"], payload["content"])
        status = 200 if result["ok"] else 400
        return json_response(self, {
            "ok": result["ok"], "kind": "night", "checked_in": checked, "title": payload["title"],
            "detail": result.get("detail") or result.get("resp") or result.get("error"),
            "configured": result.get("configured", bool(PUSHPLUS_TOKEN or WEWORK_BOT_WEBHOOK)),
        }, status)

    def handle_push_weather(self) -> None:
        payload_in = self.read_json()
        with connect() as conn:
            payload = build_weather_reminder(conn, str(payload_in.get("city", "")).strip() or None)
        result = send_notification(payload["title"], payload["content"])
        status = 200 if result["ok"] else 400
        return json_response(self, {
            "ok": result["ok"],
            "kind": "weather",
            "title": payload["title"],
            "weather": payload["weather"],
            "detail": result.get("detail") or result.get("resp") or result.get("error"),
            "configured": result.get("configured", bool(PUSHPLUS_TOKEN or WEWORK_BOT_WEBHOOK)),
        }, status)

    def handle_today_done(self) -> None:
        with connect() as conn:
            mark_checkin(conn)
        html = (
            "<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>打卡成功</title>"
            "<style>body{margin:0;height:100vh;display:grid;place-items:center;"
            "font-family:-apple-system,'PingFang SC','Microsoft YaHei',sans-serif;"
            "background:linear-gradient(135deg,#FBF1F6,#FCE7F1);color:#20242E}"
            ".card{background:#fff;padding:40px 44px;border-radius:20px;text-align:center;"
            "box-shadow:0 12px 40px -16px rgba(236,72,153,.4)}"
            ".big{font-size:46px}.t{font-size:20px;font-weight:800;margin:14px 0 6px}"
            ".s{color:#6B7280;font-size:14px}a{color:#DB2777;text-decoration:none;font-weight:700}</style>"
            "</head><body><div class='card'><div class='big'>✅</div>"
            "<div class='t'>今日打卡成功</div>"
            "<div class='s'>晚上不会有人来念你了 😌<br>继续保持节奏，加油！</div>"
            f"<p><a href='{APP_PUBLIC_URL.rstrip('/')}'>← 回到做题集</a></p>"
            "</div></body></html>"
        )
        return text_response(self, html, content_type="text/html")

    def handle_today_status(self) -> None:
        with connect() as conn:
            checked = is_checked_in(conn)
        return json_response(self, {"date": date.today().isoformat(), "checked_in": checked})

    def handle_export_mistakes(self, query: dict) -> None:
        mistakes_only = query.get("mistakes_only", ["1"])[0] != "0"
        with connect() as conn:
            pdf_bytes, count = build_mistakes_pdf(conn, query, mistakes_only=mistakes_only)
        if count == 0:
            return json_response(self, {"error": "当前范围没有可导出的错题。"}, 404)
        filename = f"mistakes_{date.today().isoformat()}_{count}q.pdf"
        self.send_response(200)
        self.send_header("Content-Type", "application/pdf")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(pdf_bytes)))
        self.end_headers()
        self.wfile.write(pdf_bytes)

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
            export_options = sakura_backup.export_options_from_query(query)
        except ValueError as exc:
            return json_response(self, {"error": str(exc)}, 400)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp:
            tmp_path = Path(tmp.name)
        try:
            try:
                sakura_backup.build_backup_zip_file(
                    tmp_path,
                    DB_PATH,
                    {"uploads": UPLOAD_DIR, "pages": PAGE_DIR},
                    include_assets=export_options["include_assets"],
                    start_date=export_options["start_date"],
                    end_date=export_options["end_date"],
                )
            except ValueError as exc:
                return json_response(self, {"error": str(exc)}, 400)
            filename = export_options["filename"]
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.send_header("Content-Length", str(tmp_path.stat().st_size))
            self.end_headers()
            with tmp_path.open("rb") as fh:
                while True:
                    chunk = fh.read(1024 * 1024)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass

    def handle_backup_import(self) -> None:
        print("[migration] request received", flush=True)
        form = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ={"REQUEST_METHOD": "POST"})
        file_item = form["backup"] if "backup" in form else form["file"] if "file" in form else None
        if file_item is None or not file_item.filename:
            return json_response(self, {"error": "请上传 Sakura 迁移 ZIP 包。"}, 400)
        job_id = uuid.uuid4().hex
        upload_dir = DATA_DIR / "migration_uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        upload_path = upload_dir / f"{job_id}.zip"
        with upload_path.open("wb") as out:
            shutil.copyfileobj(file_item.file, out, length=1024 * 1024)
        size = upload_path.stat().st_size
        print(f"[migration] uploaded file: {file_item.filename}, {size} bytes, job={job_id}", flush=True)
        now = datetime.now().isoformat(timespec="seconds")
        set_migration_job(
            job_id,
            id=job_id,
            status="queued",
            message="Backup uploaded. Waiting to restore...",
            filename=file_item.filename,
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
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(text.encode("utf-8"))

    def handle_daily(self) -> None:
        with connect() as conn:
            payload = build_daily_payload(conn)
        return json_response(self, payload)


def main() -> None:
    init_db()
    server = ThreadingHTTPServer(("127.0.0.1", PORT), DemoHandler)
    print(f"Gaoshu demo running at http://127.0.0.1:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
