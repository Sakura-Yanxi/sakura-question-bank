from __future__ import annotations

import json
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import shutil
import sys
import tempfile
import threading
import time
import traceback
import uuid
import warnings
from datetime import date, datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import urllib.parse
from html import escape as html_escape

warnings.filterwarnings("ignore", message="'cgi' is deprecated.*", category=DeprecationWarning)
import cgi

import fitz
from sakura_pdf import (
    append_page_clip_to_question_image,
    detect_question_slices,
    detect_question_starts,
    render_page_clip_image,
    render_page_image,
)
import sakura_notifications
import sakura_weather
import sakura_reminders
import sakura_config
import sakura_ai
import sakura_profile
import sakura_export
import sakura_backup
import sakura_reflection
import sakura_daily
import sakura_textbook

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
REVIEW_INTERVAL_DAYS = [1, 3, 7, 14, 30]
META_TAGS = ["计算失误", "公式遗忘", "逻辑死角", "题意理解偏差"]
WRONGISH_STATUSES = {"做错", "半会", "需复习"}
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
    for path in (DATA_DIR, UPLOAD_DIR, PAGE_DIR, STATIC_DIR):
        path.mkdir(parents=True, exist_ok=True)


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    ensure_dirs()
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL DEFAULT '',
                subject TEXT NOT NULL DEFAULT '未分类',
                document_kind TEXT NOT NULL DEFAULT '做题本',
                filename TEXT NOT NULL,
                stored_path TEXT NOT NULL,
                page_count INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS questions (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                page_number INTEGER NOT NULL,
                image_path TEXT NOT NULL,
                ocr_text TEXT NOT NULL DEFAULT '',
                category TEXT NOT NULL,
                subcategory TEXT NOT NULL DEFAULT '',
                chapter TEXT NOT NULL DEFAULT '未识别章节',
                difficulty TEXT NOT NULL DEFAULT '中等',
                status TEXT NOT NULL DEFAULT '未做',
                mistake_reason TEXT NOT NULL DEFAULT '',
                user_note TEXT NOT NULL DEFAULT '',
                ai_analysis TEXT NOT NULL DEFAULT '',
                ai_variations TEXT NOT NULL DEFAULT '',
                ai_hint TEXT NOT NULL DEFAULT '',
                meta_tags TEXT NOT NULL DEFAULT '[]',
                review_count INTEGER NOT NULL DEFAULT 0,
                last_reviewed_at TEXT,
                ever_wrong INTEGER NOT NULL DEFAULT 0,
                review_stage INTEGER NOT NULL DEFAULT 0,
                retention_stage INTEGER NOT NULL DEFAULT 0,
                next_review_at TEXT,
                mastered_at TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(document_id) REFERENCES documents(id)
            );

            """
        )
        migrate_db(conn)
        conn.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_questions_category ON questions(category);
            CREATE INDEX IF NOT EXISTS idx_questions_chapter ON questions(chapter);
            CREATE INDEX IF NOT EXISTS idx_questions_status ON questions(status);
            CREATE INDEX IF NOT EXISTS idx_questions_document ON questions(document_id);
            CREATE INDEX IF NOT EXISTS idx_questions_next_review ON questions(next_review_at);
            """
        )
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS reflections (
                id TEXT PRIMARY KEY,
                period TEXT NOT NULL,
                period_start TEXT NOT NULL,
                period_end TEXT NOT NULL,
                summary_json TEXT NOT NULL DEFAULT '{}',
                reflection_text TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_reflections_created ON reflections(created_at);
            """
        )
        conn.executescript(
            """
            -- L1 洞察层：每道错题分析时抽取的结构化证据
            CREATE TABLE IF NOT EXISTS insights (
                id TEXT PRIMARY KEY,
                question_id TEXT NOT NULL UNIQUE,
                document_id TEXT NOT NULL DEFAULT '',
                subject TEXT NOT NULL DEFAULT '',
                knowledge_points TEXT NOT NULL DEFAULT '[]',
                root_cause TEXT NOT NULL DEFAULT '',
                misconception TEXT NOT NULL DEFAULT '',
                missing_prereq TEXT NOT NULL DEFAULT '[]',
                user_difficulty INTEGER NOT NULL DEFAULT 3,
                confidence REAL NOT NULL DEFAULT 0.5,
                source TEXT NOT NULL DEFAULT 'local',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(question_id) REFERENCES questions(id)
            );
            CREATE INDEX IF NOT EXISTS idx_insights_subject ON insights(subject);
            CREATE INDEX IF NOT EXISTS idx_insights_root_cause ON insights(root_cause);

            -- L2 画像层：滚动合成的学习者档案（版本快照，留趋势）
            CREATE TABLE IF NOT EXISTS learner_profile (
                id TEXT PRIMARY KEY,
                version INTEGER NOT NULL DEFAULT 1,
                scope TEXT NOT NULL DEFAULT '__all__',
                profile_json TEXT NOT NULL DEFAULT '{}',
                evidence_count INTEGER NOT NULL DEFAULT 0,
                source TEXT NOT NULL DEFAULT 'local',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_profile_scope_version ON learner_profile(scope, version);

            -- 学习档案状态：设置 + 缓存的最近计划（单行 id='singleton'）
            CREATE TABLE IF NOT EXISTS coach_state (
                id TEXT PRIMARY KEY,
                daily_minutes INTEGER NOT NULL DEFAULT 60,
                exam_date TEXT NOT NULL DEFAULT '',
                cadence TEXT NOT NULL DEFAULT 'immediate',
                focus_subject TEXT NOT NULL DEFAULT '',
                last_profile_at TEXT,
                last_plan_at TEXT,
                plan_json TEXT NOT NULL DEFAULT '{}'
            );

            -- 每日打卡：记录哪天点了「已完成」
            CREATE TABLE IF NOT EXISTS checkins (
                day TEXT PRIMARY KEY,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS teacher_memory (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'chat',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS mentor_experience (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL DEFAULT '',
                content TEXT NOT NULL,
                subject TEXT NOT NULL DEFAULT '',
                tags TEXT NOT NULL DEFAULT '[]',
                source TEXT NOT NULL DEFAULT '',
                reliability INTEGER NOT NULL DEFAULT 3,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_mentor_experience_subject ON mentor_experience(subject);
            CREATE INDEX IF NOT EXISTS idx_mentor_experience_created ON mentor_experience(created_at);

            CREATE TABLE IF NOT EXISTS ai_teacher_turns (
                id TEXT PRIMARY KEY,
                user_message TEXT NOT NULL,
                intent TEXT NOT NULL DEFAULT '',
                strategy TEXT NOT NULL DEFAULT '',
                context_json TEXT NOT NULL DEFAULT '{}',
                answer TEXT NOT NULL DEFAULT '',
                memory_candidate TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_ai_teacher_turns_created ON ai_teacher_turns(created_at);

            CREATE TABLE IF NOT EXISTS textbooks (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL DEFAULT '',
                subject TEXT NOT NULL DEFAULT '未分类',
                filename TEXT NOT NULL,
                stored_path TEXT NOT NULL,
                page_count INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS textbook_pages (
                id TEXT PRIMARY KEY,
                textbook_id TEXT NOT NULL,
                page_number INTEGER NOT NULL,
                image_path TEXT NOT NULL,
                page_text TEXT NOT NULL DEFAULT '',
                paragraphs_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                UNIQUE(textbook_id, page_number),
                FOREIGN KEY(textbook_id) REFERENCES textbooks(id)
            );

            CREATE TABLE IF NOT EXISTS textbook_chats (
                id TEXT PRIMARY KEY,
                textbook_id TEXT NOT NULL DEFAULT '',
                page_number INTEGER NOT NULL DEFAULT 0,
                role TEXT NOT NULL,
                content TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS daily_rules (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL DEFAULT '',
                enabled INTEGER NOT NULL DEFAULT 1,
                document_id TEXT NOT NULL DEFAULT '',
                subject TEXT NOT NULL DEFAULT '',
                category TEXT NOT NULL DEFAULT '',
                chapter TEXT NOT NULL DEFAULT '',
                status_group TEXT NOT NULL DEFAULT 'active_wrong',
                limit_count INTEGER NOT NULL DEFAULT 5,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS practice_batches (
                id TEXT PRIMARY KEY,
                day TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'manual',
                title TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                completed_at TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS practice_batch_items (
                batch_id TEXT NOT NULL,
                question_id TEXT NOT NULL,
                position INTEGER NOT NULL DEFAULT 0,
                quick_status TEXT NOT NULL DEFAULT '',
                quick_note TEXT NOT NULL DEFAULT '',
                completed_at TEXT NOT NULL DEFAULT '',
                PRIMARY KEY(batch_id, question_id),
                FOREIGN KEY(batch_id) REFERENCES practice_batches(id),
                FOREIGN KEY(question_id) REFERENCES questions(id)
            );
            """
        )


def migrate_db(conn: sqlite3.Connection) -> None:
    document_columns = {row["name"] for row in conn.execute("PRAGMA table_info(documents)").fetchall()}
    if "title" not in document_columns:
        conn.execute("ALTER TABLE documents ADD COLUMN title TEXT NOT NULL DEFAULT ''")
    if "subject" not in document_columns:
        conn.execute("ALTER TABLE documents ADD COLUMN subject TEXT NOT NULL DEFAULT '未分类'")
    if "document_kind" not in document_columns:
        conn.execute("ALTER TABLE documents ADD COLUMN document_kind TEXT NOT NULL DEFAULT '做题本'")
    conn.execute("UPDATE documents SET title = filename WHERE title = ''")
    conn.execute("UPDATE documents SET subject = ? WHERE subject = '' OR subject = '其他'", (DEFAULT_SUBJECT,))
    conn.execute(
        "UPDATE documents SET document_kind = ? WHERE document_kind = '' OR document_kind NOT IN ('做题本', '模拟卷')",
        (DEFAULT_DOCUMENT_KIND,),
    )

    question_columns = {row["name"] for row in conn.execute("PRAGMA table_info(questions)").fetchall()}
    if "question_no" not in question_columns:
        conn.execute("ALTER TABLE questions ADD COLUMN question_no TEXT NOT NULL DEFAULT ''")
    if "seq_no" not in question_columns:
        conn.execute("ALTER TABLE questions ADD COLUMN seq_no INTEGER NOT NULL DEFAULT 0")
        # 回填：每本做题本内按页码排出 1-based 序号
        conn.execute(
            """
            UPDATE questions SET seq_no = (
                SELECT COUNT(*) FROM questions q2
                WHERE q2.document_id = questions.document_id
                  AND q2.page_number <= questions.page_number
            )
            """
        )
    if "chapter" not in question_columns:
        conn.execute("ALTER TABLE questions ADD COLUMN chapter TEXT NOT NULL DEFAULT '未识别章节'")
    if "ai_variations" not in question_columns:
        conn.execute("ALTER TABLE questions ADD COLUMN ai_variations TEXT NOT NULL DEFAULT ''")
    if "ai_hint" not in question_columns:
        conn.execute("ALTER TABLE questions ADD COLUMN ai_hint TEXT NOT NULL DEFAULT ''")
    if "meta_tags" not in question_columns:
        conn.execute("ALTER TABLE questions ADD COLUMN meta_tags TEXT NOT NULL DEFAULT '[]'")
    if "ever_wrong" not in question_columns:
        conn.execute("ALTER TABLE questions ADD COLUMN ever_wrong INTEGER NOT NULL DEFAULT 0")
        conn.execute("UPDATE questions SET ever_wrong = 1 WHERE status IN ('做错', '半会', '需复习')")
    if "review_stage" not in question_columns:
        conn.execute("ALTER TABLE questions ADD COLUMN review_stage INTEGER NOT NULL DEFAULT 0")
    if "retention_stage" not in question_columns:
        conn.execute("ALTER TABLE questions ADD COLUMN retention_stage INTEGER NOT NULL DEFAULT 0")
    if "next_review_at" not in question_columns:
        conn.execute("ALTER TABLE questions ADD COLUMN next_review_at TEXT")
    if "mastered_at" not in question_columns:
        conn.execute("ALTER TABLE questions ADD COLUMN mastered_at TEXT")
    conn.execute("UPDATE questions SET chapter = ? WHERE chapter = ''", (DEFAULT_CHAPTER,))
    conn.execute("UPDATE questions SET meta_tags = '[]' WHERE meta_tags = ''")
    coach_exists = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='coach_state'").fetchone()
    coach_columns = {row["name"] for row in conn.execute("PRAGMA table_info(coach_state)").fetchall()} if coach_exists else set()
    if coach_exists and "weather_city" not in coach_columns:
        conn.execute("ALTER TABLE coach_state ADD COLUMN weather_city TEXT NOT NULL DEFAULT ''")


def to_public_path(path: str | Path) -> str:
    absolute = Path(path).resolve()
    return "/" + absolute.relative_to(ROOT).as_posix()


def extract_question_no(text: str) -> str:
    """从题目文字里尽力识别印刷题号（如 03. / 345），用于快速定位。"""
    if not text:
        return ""
    for line in text.splitlines()[:8]:
        s = line.strip()
        if not s or "公众号" in s or "微信" in s:
            continue
        if re.match(r"^\d+\.\d+", s):  # 跳过章节号，例如 1.1 / 2.3
            continue
        m = re.match(r"^(\d{1,3})\s*[.、．。)）:：]?\s*\S", s)
        if m:
            return str(int(m.group(1)))
    return ""


def row_to_dict(row: sqlite3.Row) -> dict:
    item = dict(row)
    item["image_url"] = to_public_path(item["image_path"])
    try:
        item["meta_tags"] = json.loads(item.get("meta_tags") or "[]")
    except (TypeError, json.JSONDecodeError):
        item["meta_tags"] = []
    if "document_kind" in item:
        item["document_kind"] = normalize_document_kind(item.get("document_kind"))
    item["question_no"] = (item.get("question_no") or "").strip() or extract_question_no(item.get("ocr_text", ""))
    return item


def document_to_dict(row: sqlite3.Row) -> dict:
    item = dict(row)
    item["document_kind"] = normalize_document_kind(item.get("document_kind"))
    return item


def normalize_document_kind(value: str | None) -> str:
    clean = normalize_label(value or "", DEFAULT_DOCUMENT_KIND)
    if clean.lower() in {"mock", "mock_paper", "paper", "exam"}:
        return MOCK_PAPER_KIND
    if clean.lower() in {"book", "workbook"}:
        return DEFAULT_DOCUMENT_KIND
    return clean if clean in DOCUMENT_KINDS else DEFAULT_DOCUMENT_KIND


def schedule_for_status(current: sqlite3.Row | dict | None, status: str, now: datetime | None = None) -> dict:
    now = now or datetime.now()
    if status in WRONGISH_STATUSES:
        return {
            "ever_wrong": 1,
            "review_stage": 0,
            "retention_stage": 1,
            "next_review_at": (now + timedelta(days=1)).date().isoformat(),
            "mastered_at": None,
        }
    if status != "做对" or not current:
        return {}

    current_dict = dict(current)
    was_in_review = bool(current_dict.get("ever_wrong")) or current_dict.get("status") in {"做错", "半会", "需复习"}
    if not was_in_review:
        return {}

    next_stage = int(current_dict.get("review_stage") or 0) + 1
    if next_stage > len(REVIEW_INTERVAL_DAYS):
        return {
            "ever_wrong": 1,
            "review_stage": next_stage,
            "retention_stage": REVIEW_INTERVAL_DAYS[-1],
            "next_review_at": None,
            "mastered_at": now.isoformat(timespec="seconds"),
        }
    interval = REVIEW_INTERVAL_DAYS[next_stage - 1]
    return {
        "ever_wrong": 1,
        "review_stage": next_stage,
        "retention_stage": interval,
        "next_review_at": (now + timedelta(days=interval)).date().isoformat(),
        "mastered_at": None,
    }


def get_filter_options(conn: sqlite3.Connection) -> dict:
    subjects = [
        row["subject"]
        for row in conn.execute(
            "SELECT DISTINCT subject FROM documents WHERE subject <> '' ORDER BY subject"
        ).fetchall()
    ]
    categories = [
        row["category"]
        for row in conn.execute(
            """
            SELECT category, MIN(page_number) first_page
            FROM questions
            WHERE category <> ''
            GROUP BY category
            ORDER BY first_page ASC, category ASC
            """
        ).fetchall()
    ]
    chapters = [
        row["chapter"]
        for row in conn.execute(
            """
            SELECT chapter, MIN(page_number) first_page
            FROM questions
            WHERE chapter <> ''
            GROUP BY chapter
            ORDER BY first_page ASC, chapter ASC
            """
        ).fetchall()
    ]
    return {"subjects": subjects, "categories": categories, "chapters": chapters}


def build_question_filters(query: dict, keys: tuple[str, ...]) -> tuple[str, list[str]]:
    clauses = []
    params: list[str] = []
    for key in ("category", "status", "document_id", "chapter"):
        value = query.get(key, [""])[0]
        if value and key in keys:
            clauses.append(f"q.{key} = ?")
            params.append(value)
    subject = query.get("subject", [""])[0]
    if subject and "subject" in keys:
        clauses.append("d.subject = ?")
        params.append(subject)
    search = query.get("search", [""])[0].strip()
    if search and "search" in keys:
        clauses.append("(q.ocr_text LIKE ? OR q.subcategory LIKE ? OR q.user_note LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    return where, params


def get_scoped_filter_options(conn: sqlite3.Connection, query: dict) -> dict:
    subjects = [
        row["subject"]
        for row in conn.execute(
            "SELECT DISTINCT subject FROM documents WHERE subject <> '' ORDER BY subject"
        ).fetchall()
    ]
    category_where, category_params = build_question_filters(
        query,
        ("status", "document_id", "chapter", "subject", "search"),
    )
    category_where = f"{category_where} AND q.category <> ''" if category_where else "WHERE q.category <> ''"
    categories = [
        row["category"]
        for row in conn.execute(
            f"""
            SELECT q.category, MIN(q.page_number) first_page
            FROM questions q
            JOIN documents d ON d.id = q.document_id
            {category_where}
            GROUP BY q.category
            ORDER BY first_page ASC, q.category ASC
            """,
            category_params,
        ).fetchall()
    ]
    chapter_where, chapter_params = build_question_filters(
        query,
        ("category", "status", "document_id", "subject", "search"),
    )
    chapter_where = f"{chapter_where} AND q.chapter <> ''" if chapter_where else "WHERE q.chapter <> ''"
    chapters = [
        row["chapter"]
        for row in conn.execute(
            f"""
            SELECT q.chapter, MIN(q.page_number) first_page
            FROM questions q
            JOIN documents d ON d.id = q.document_id
            {chapter_where}
            GROUP BY q.chapter
            ORDER BY first_page ASC, q.chapter ASC
            """,
            chapter_params,
        ).fetchall()
    ]
    return {"subjects": subjects, "categories": categories, "chapters": chapters}


def json_response(handler: BaseHTTPRequestHandler, payload: dict | list, status: int = 200) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def text_response(handler: BaseHTTPRequestHandler, text: str, status: int = 200, content_type: str = "text/plain") -> None:
    body = text.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", f"{content_type}; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def redirect_response(handler: BaseHTTPRequestHandler, location: str, status: int = HTTPStatus.FOUND) -> None:
    handler.send_response(status)
    handler.send_header("Location", location)
    handler.end_headers()


def auth_enabled() -> bool:
    return bool(ADMIN_PASSWORD)


def auth_secret() -> str:
    return AUTH_SECRET or ADMIN_PASSWORD or "sakura-local-dev"


def sign_session(payload: str) -> str:
    return hmac.new(auth_secret().encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def make_session_token() -> str:
    expires = int(time.time()) + AUTH_MAX_AGE_SECONDS
    nonce = secrets.token_urlsafe(18)
    payload = f"{expires}:{nonce}"
    return f"{payload}:{sign_session(payload)}"


def verify_session_token(token: str) -> bool:
    parts = (token or "").split(":")
    if len(parts) != 3:
        return False
    expires, nonce, signature = parts
    payload = f"{expires}:{nonce}"
    if not hmac.compare_digest(signature, sign_session(payload)):
        return False
    try:
        return int(expires) >= int(time.time())
    except ValueError:
        return False


def login_page(error: str = "") -> str:
    error_html = f"<div class='error'>{html_escape(error)}</div>" if error else ""
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Sakura 做题集 · 登录</title>
  <style>
    :root {{ color-scheme: light; --pink:#ec4899; --ink:#14213d; --muted:#718096; --line:#eadfea; }}
    * {{ box-sizing: border-box; }}
    body {{ margin:0; min-height:100vh; display:grid; place-items:center; font-family: Inter, "Microsoft YaHei", system-ui, sans-serif; background: radial-gradient(circle at 20% 10%, #fff0f7 0, transparent 28%), linear-gradient(135deg,#f8fbff,#fff7fb 48%,#f5fffb); color:var(--ink); }}
    .card {{ width:min(420px, calc(100vw - 32px)); background:rgba(255,255,255,.92); border:1px solid var(--line); border-radius:26px; padding:34px; box-shadow:0 28px 80px rgba(236,72,153,.16); }}
    .logo {{ width:58px; height:58px; border-radius:18px; display:grid; place-items:center; background:#fff0f7; color:var(--pink); font-size:28px; font-weight:900; margin-bottom:18px; }}
    h1 {{ margin:0 0 8px; font-size:28px; letter-spacing:0; }}
    p {{ margin:0 0 24px; color:var(--muted); line-height:1.7; }}
    label {{ display:grid; gap:8px; font-weight:800; color:#4a5568; }}
    input {{ width:100%; height:52px; border:1px solid #e6d8e6; border-radius:16px; padding:0 16px; font-size:16px; outline:none; }}
    input:focus {{ border-color:var(--pink); box-shadow:0 0 0 4px rgba(236,72,153,.12); }}
    button {{ width:100%; height:52px; margin-top:18px; border:0; border-radius:16px; color:white; background:linear-gradient(135deg,#ec4899,#f472b6); font-size:16px; font-weight:900; cursor:pointer; box-shadow:0 18px 34px rgba(236,72,153,.25); }}
    .error {{ margin-bottom:16px; padding:10px 12px; border-radius:14px; background:#fff5f5; color:#dc2626; font-weight:700; }}
    small {{ display:block; margin-top:16px; color:#94a3b8; line-height:1.6; }}
  </style>
</head>
<body>
  <main class="card">
    <div class="logo">S</div>
    <h1>Sakura 做题集</h1>
    <p>请输入管理员密码后进入学习面板。这样别人知道域名，也不能随意修改题库、API 和推送配置。</p>
    {error_html}
    <form method="post" action="/login">
      <label>管理员密码
        <input name="password" type="password" autocomplete="current-password" autofocus required />
      </label>
      <button type="submit">进入 Sakura</button>
    </form>
    <small>登录状态会在当前浏览器保留 14 天。忘记密码时可在服务器 .env 修改 SAKURA_ADMIN_PASSWORD。</small>
  </main>
</body>
</html>"""


def classify_by_rules(text: str) -> tuple[str, str, str]:
    haystack = text.lower()
    for category, keywords in KEYWORD_RULES:
        if any(keyword.lower() in haystack for keyword in keywords):
            return category, "规则分类", "中等"
    return DEFAULT_CATEGORY, "待人工确认", "中等"


def normalize_label(value: str, fallback: str) -> str:
    clean = re.sub(r"\s+", " ", (value or "").strip())
    clean = re.sub(r"^[\-\s|·•]+|[\-\s|·•]+$", "", clean)
    return clean[:80] if clean else fallback


def normalize_chapter(value: str, fallback: str = DEFAULT_CHAPTER) -> str:
    clean = normalize_label(value, fallback)
    clean = strip_chapter_noise(clean)
    clean = re.sub(r"\s+", " ", clean)
    clean = re.sub(r"第\s*([一二三四五六七八九十百\d]+)\s*([章节讲])", r"第\1\2", clean)
    clean = re.sub(r"chapter\s*([0-9a-zA-Z_.-]+)", r"Chapter \1", clean, flags=re.I)
    clean = dedupe_repeated_phrase(clean)
    return clean


def strip_chapter_noise(value: str) -> str:
    text = normalize_label(value, "")
    noise_patterns = [
        r"\s*基础篇.*$",
        r"\s*强化篇.*$",
        r"\s*提高篇.*$",
        r"\s*冲刺篇.*$",
        r"\s*专项篇.*$",
        r"\s*微信公众号.*$",
        r"\s*公众号.*$",
        r"\s*微信.*$",
        r"\s*一研题本.*$",
        r"\s*考研.*$",
    ]
    for pattern in noise_patterns:
        text = re.sub(pattern, "", text, flags=re.I)
    return text.strip()


def dedupe_repeated_phrase(value: str) -> str:
    text = normalize_label(value, "")
    if not text:
        return value
    repeated_prefix = re.match(r"^(.{2,45}?)(?:\s+\1)(?:\s+.*)?$", text)
    if repeated_prefix:
        return repeated_prefix.group(1)
    numbered = re.match(r"^((?:第\s*)?[一二三四五六七八九十百\d]+[.、章节讲]\s*[^，。；;\s]{2,30})(?:\s+\1)(?:\s+.*)?$", text)
    if numbered:
        return numbered.group(1)
    length = len(text)
    if length % 2 == 0:
        half = length // 2
        if text[:half] == text[half:]:
            return text[:half]
    compact = re.sub(r"\s+", "", text)
    for size in range(2, len(compact) // 2 + 1):
        if len(compact) % size == 0:
            unit = compact[:size]
            if unit * (len(compact) // size) == compact:
                return unit
    match = re.match(r"^(.{2,40}?)(?:\s*\1)+$", text)
    if match:
        return match.group(1)
    return text


def looks_like_chapter(text: str) -> bool:
    clean = normalize_label(text, "")
    if not clean or len(clean) > 90:
        return False
    if re.fullmatch(r"\d+|第\s*\d+\s*页|page\s*\d+", clean, flags=re.I):
        return False
    chapter_patterns = [
        r"第\s*[一二三四五六七八九十百\d]+\s*[章节讲]",
        r"(chapter|unit|lecture|section)\s*[0-9a-zA-Z_.-]+",
        r"^[一二三四五六七八九十\d]+[.、]\s*[^，。；;]{2,}",
        r"(函数|极限|积分|微分|级数|矩阵|行列式|概率|随机|网络|数据库|操作系统|组成原理|数据结构|算法)",
    ]
    return any(re.search(pattern, clean, flags=re.I) for pattern in chapter_patterns)


def extract_chapter_from_page(page: fitz.Page, text: str) -> str:
    candidates = []
    width = max(page.rect.width, 1)
    height = max(page.rect.height, 1)
    for block in page.get_text("blocks", sort=True):
        if len(block) < 5:
            continue
        x0, y0, x1, y1, block_text = block[:5]
        clean = re.sub(r"\s+", " ", str(block_text)).strip()
        if not clean:
            continue
        if y1 <= height * 0.22:
            candidates.append((0, clean))
        if x0 >= width * 0.38 and y1 <= height * 0.35:
            candidates.append((1, clean))
        if y1 <= height * 0.35 and looks_like_chapter(clean):
            candidates.append((2, clean))

    words = page.get_text("words", sort=True)
    top_words = []
    right_top_words = []
    for word in words:
        if len(word) < 5:
            continue
        x0, y0, x1, y1, word_text = word[:5]
        if y1 <= height * 0.16:
            top_words.append(str(word_text))
        if x0 >= width * 0.4 and y1 <= height * 0.32:
            right_top_words.append(str(word_text))
    for joined in (" ".join(right_top_words), " ".join(top_words)):
        joined = normalize_label(joined, "")
        if joined:
            candidates.append((3, joined))

    for _priority, candidate in sorted(candidates, key=lambda item: item[0]):
        parts = re.split(r"\s{2,}|[|｜]", candidate)
        for part in parts:
            if looks_like_chapter(part):
                return normalize_chapter(part)

    patterns = [
        r"(第[一二三四五六七八九十百\d]+[章节讲][^\n，。；;]{0,30})",
        r"((?:Chapter|Unit|Lecture|Section)\s*[\w.-]+[^\n]{0,35})",
        r"([一二三四五六七八九十\d]+[.、]\s*[^\n，。；;]{2,35})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            return normalize_chapter(match.group(1), DEFAULT_CHAPTER)
    return DEFAULT_CHAPTER


def llm_enabled() -> bool:
    """是否已配置 AI 接口密钥。"""
    return bool(LLM_API_KEY)


def mask_secret(value: str) -> str:
    value = value or ""
    if not value:
        return ""
    keep = 4 if len(value) <= 12 else 8
    return value[:keep] + "xxxx"


def mask_public_url(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    parsed = urlparse(value)
    if parsed.scheme and parsed.netloc:
        host = parsed.netloc
        if re.match(r"^\d+\.\d+\.", host):
            parts = host.split(".")
            return f"{parsed.scheme}://{parts[0]}.{parts[1]}.xxxx"
        keep = min(len(host), 6 if re.match(r"^\d+\.\d+", host) else 10)
        return f"{parsed.scheme}://{host[:keep]}xxxx"
    return mask_secret(value)


def llm_settings_view() -> dict:
    return {
        "has_key": llm_enabled(),
        "masked_key": mask_secret(LLM_API_KEY),
        "base_url": LLM_BASE_URL,
        "model": LLM_MODEL,
        "key_env": "LLM_API_KEY" if LLM_API_KEY else "",
    }


def notification_settings_view() -> dict:
    return {
        "has_wework": bool(WEWORK_BOT_WEBHOOK),
        "masked_wework": mask_secret(WEWORK_BOT_WEBHOOK),
        "has_pushplus": bool(PUSHPLUS_TOKEN),
        "masked_pushplus": mask_secret(PUSHPLUS_TOKEN),
        "app_public_url": "",
        "masked_app_public_url": mask_public_url(APP_PUBLIC_URL),
    }


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
    clean = value.strip().rstrip("/")
    parsed = urlparse(clean)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("公网地址必须是完整 URL，例如：https://your-domain.example")
    return clean


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
    category, subcategory, difficulty = classify_by_rules(text)
    chapter = normalize_chapter(chapter_hint, DEFAULT_CHAPTER)
    if document_kind != MOCK_PAPER_KIND and category == DEFAULT_CATEGORY and chapter != DEFAULT_CHAPTER:
        category = chapter
        subcategory = "章节归类"
    return {
        "subject": normalize_label(subject_hint, DEFAULT_SUBJECT),
        "chapter": chapter,
        "category": category,
        "subcategory": subcategory,
        "difficulty": difficulty,
        "reason": "导入阶段使用本地规则分类，不调用 DeepSeek。",
    }


# ==========================================================================
# L1 洞察层：分析错题时抽取结构化证据，沉淀进学习者记忆
# ==========================================================================
def guess_root_cause(question: dict) -> str:
    for tag in normalize_meta_tags(question.get("meta_tags")):
        mapped = META_TAG_TO_ROOT_CAUSE.get(tag)
        if mapped:
            return mapped
    return "方法不会"


def local_insight(question: dict) -> dict:
    """无 DeepSeek 时，用 meta_tags + 本地分类规则拼出一条洞察。"""
    category = question.get("category") or DEFAULT_CATEGORY
    chapter = question.get("chapter") or ""
    knowledge_points = [kp for kp in (category, chapter) if kp and kp != DEFAULT_CATEGORY and kp != DEFAULT_CHAPTER]
    knowledge_points = knowledge_points or [category]
    root_cause = guess_root_cause(question)
    tags = normalize_meta_tags(question.get("meta_tags"))
    misconception = (question.get("mistake_reason") or "、".join(tags) or "暂无具体误区记录").strip()[:200]
    prereq = []
    for key in (category, chapter):
        prereq.extend(KNOWLEDGE_DEPENDENCIES.get(key, []))
    seen: list[str] = []
    for item in prereq:
        if item not in seen:
            seen.append(item)
    return {
        "knowledge_points": knowledge_points[:5],
        "root_cause": root_cause,
        "misconception": misconception,
        "missing_prereq": seen[:5],
        "user_difficulty": {"简单": 2, "中等": 3, "困难": 4}.get(question.get("difficulty", "中等"), 3),
        "confidence": 0.4,
        "source": "local",
    }


def normalize_insight(raw: dict, question: dict) -> dict:
    """把 AI 返回的洞察 JSON 收敛到固定 schema、做夹断与枚举校验。"""
    base = local_insight(question)
    if not isinstance(raw, dict):
        return base

    kps = raw.get("knowledge_points")
    if isinstance(kps, str):
        kps = [kps]
    kps = [str(k).strip() for k in (kps or []) if str(k).strip()][:5]

    root_cause = str(raw.get("root_cause", "")).strip()
    if root_cause not in ROOT_CAUSES:
        root_cause = base["root_cause"]

    prereq = raw.get("missing_prereq")
    if isinstance(prereq, str):
        prereq = [prereq]
    prereq = [str(p).strip() for p in (prereq or []) if str(p).strip()][:5]

    try:
        difficulty = int(raw.get("user_difficulty", base["user_difficulty"]))
    except (TypeError, ValueError):
        difficulty = base["user_difficulty"]
    try:
        confidence = float(raw.get("confidence", 0.7))
    except (TypeError, ValueError):
        confidence = 0.7

    return {
        "knowledge_points": kps or base["knowledge_points"],
        "root_cause": root_cause,
        "misconception": str(raw.get("misconception", "")).strip()[:200] or base["misconception"],
        "missing_prereq": prereq or base["missing_prereq"],
        "user_difficulty": max(1, min(5, difficulty)),
        "confidence": max(0.0, min(1.0, confidence)),
        "source": "ai",
    }


def analyze_and_extract_with_ai(question: dict) -> tuple[str, dict]:
    """一次 DeepSeek 调用同时拿到：给人看的解析散文 + 给记忆用的结构化洞察。"""
    local = local_insight(question)
    fallback_prose = (
        f"知识点：{question.get('category', DEFAULT_CATEGORY)}。\n"
        "建议先复盘这道题的核心定义、常见公式和第一步切入方法。"
        "如果是计算错误，把关键变形逐行写出；如果是方法不会，先找同类基础题练 2-3 道。"
    )
    if not llm_enabled():
        return fallback_prose + "\n\n当前未配置 AI 接口密钥，使用本地简版分析与洞察。", local

    try:
        prompt = f"""
你是严谨的错题教练。请完成两件事并严格按格式输出。

科目：{question.get('subject', DEFAULT_SUBJECT)}
章节：{question.get('chapter', DEFAULT_CHAPTER)}
题目分类：{question.get('category', DEFAULT_CATEGORY)} / {question.get('subcategory', '')}
难度：{question.get('difficulty', '中等')}
做题状态：{question.get('status', '')}
学生勾选的错因标签：{', '.join(normalize_meta_tags(question.get('meta_tags'))) or '无'}
学生备注：{question.get('user_note') or '无'}
题目文字：
{(question.get('ocr_text') or '')[:3500]}

第一部分：用中文给出简洁可执行的错题分析，分四点——1.本题考察点 2.可能错因 3.解题切入 4.下次练习建议。

第二部分：另起一行，输出一个 ```json 代码块，字段固定如下（不要多余字段）：
{{
  "knowledge_points": ["真实考察的知识点，1-3个"],
  "root_cause": "必须是其中之一：概念缺失 / 计算失误 / 方法不会 / 审题偏差",
  "misconception": "一句话点明这名学生最可能的具体误区",
  "missing_prereq": ["为掌握本题需要补的前置知识点，可为空数组"],
  "user_difficulty": 1到5的整数（这道题对该学生的难度）,
  "confidence": 0到1之间的小数（你对以上判断的置信度）
}}
"""
        content = call_llm(prompt, temperature=0.3)
        try:
            insight = normalize_insight(sakura_ai.extract_json_block(content), question)
        except (ValueError, json.JSONDecodeError):
            insight = local
        prose = re.sub(r"```(?:json)?\s*\{.*?\}\s*```", "", content, flags=re.S).strip() or fallback_prose
        return prose, insight
    except Exception:
        print("LLM analyze+extract failed; falling back", file=sys.stderr)
        traceback.print_exc()
        return fallback_prose, local


def upsert_insight(conn: sqlite3.Connection, question: dict, insight: dict) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        """
        INSERT INTO insights (
            id, question_id, document_id, subject, knowledge_points, root_cause,
            misconception, missing_prereq, user_difficulty, confidence, source, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(question_id) DO UPDATE SET
            document_id = excluded.document_id,
            subject = excluded.subject,
            knowledge_points = excluded.knowledge_points,
            root_cause = excluded.root_cause,
            misconception = excluded.misconception,
            missing_prereq = excluded.missing_prereq,
            user_difficulty = excluded.user_difficulty,
            confidence = excluded.confidence,
            source = excluded.source,
            updated_at = excluded.updated_at
        """,
        (
            uuid.uuid4().hex,
            question.get("id"),
            question.get("document_id", ""),
            question.get("subject") or DEFAULT_SUBJECT,
            json.dumps(insight["knowledge_points"], ensure_ascii=False),
            insight["root_cause"],
            insight["misconception"],
            json.dumps(insight["missing_prereq"], ensure_ascii=False),
            insight["user_difficulty"],
            insight["confidence"],
            insight["source"],
            now,
            now,
        ),
    )


def infer_concept_hint(question: dict) -> str:
    text = f"{question.get('category', '')} {question.get('chapter', '')} {question.get('ocr_text', '')}".lower()
    rules = [
        (["洛必达", "l'h", "lhopital", "0/0", "∞/∞"], "核心定理：洛必达法则。先确认是否满足 0/0 或 ∞/∞ 型，再分别求分子分母导数。"),
        (["等价", "无穷小", "lim", "极限"], "核心定理：等价无穷小替换与极限四则运算。先判断主导项，再化简为标准极限。"),
        (["泰勒", "麦克劳林"], "核心定理：泰勒展开。优先围绕展开点保留到第一个非零项或题目所需阶数。"),
        (["级数", "收敛", "发散"], "核心定理：级数收敛判别法。先判断是正项级数、交错级数、幂级数还是一般项级数。"),
        (["积分", "原函数", "不定积分"], "核心方法：换元积分或分部积分。先观察复合函数结构与可微因子。"),
        (["微分方程", "通解", "特解"], "核心方法：一阶方程分类。先判断可分离、齐次、线性，或是否需要积分因子。"),
        (["导数", "微分", "求导"], "核心定理：复合函数求导法则。先拆外层函数与内层函数。"),
        (["矩阵", "行列式", "特征值"], "核心定理：矩阵初等变换与特征方程。先明确目标是化简、求秩还是求特征值。"),
    ]
    for keywords, hint in rules:
        if any(keyword in text for keyword in keywords):
            return hint
    return f"核心概念：{question.get('category') or DEFAULT_CATEGORY}。先回到该知识点的定义、适用条件和标准题型。"


def infer_key_step_hint(question: dict) -> str:
    text = f"{question.get('category', '')} {question.get('chapter', '')} {question.get('ocr_text', '')}".lower()
    if "洛必达" in text or "0/0" in text or "∞/∞" in text:
        return "关键第一步：把原式整理成分式极限，并验证分子、分母同时趋于 0 或同时趋于无穷，再考虑求导。"
    if "泰勒" in text or "麦克劳林" in text:
        return "关键第一步：选定展开点，写出常用展开式，例如 e^x、sin x、ln(1+x)，并判断需要保留到几阶。"
    if "级数" in text:
        return "关键第一步：先写出通项 a_n，判断是否满足 a_n -> 0；若不满足，可直接判定发散。"
    if "积分" in text:
        return "关键第一步：寻找一个可设为 u 的内层表达式，检查 du 是否能在积分式中配出来。"
    if "微分方程" in text:
        return "关键第一步：把方程整理成 y' = f(x, y) 或标准线性形式 y' + P(x)y = Q(x)。"
    if "导数" in text or "微分" in text:
        return "关键第一步：先标出外层函数，再对内层整体求导，避免漏乘链式法则中的内导数。"
    return "关键第一步：先把已知条件、要求目标和可用公式分三行写出来，再选择最直接的变形入口。"


def generate_hint_with_ai(question: dict, level: int) -> str:
    if level == 1:
        return infer_concept_hint(question)
    if level == 2:
        return infer_key_step_hint(question)

    fallback = (
        "Level 3 完整解析：\n"
        f"1. 先识别知识点：{question.get('category', DEFAULT_CATEGORY)}。\n"
        "2. 写出题目所需的核心公式。\n"
        "3. 按公式代入并逐步化简。\n\n"
        "当前未配置 AI 接口密钥，因此返回本地简版解析。"
    )
    if not llm_enabled():
        return fallback
    try:
        prompt = f"""
你是严谨的数学助教。请为下面题目生成 Level 3 Full Solution。
要求：
- 使用 Markdown + LaTeX。
- 公式用 $$...$$ 或 \\(...\\)。
- 先列关键定理，再给完整步骤，最后给易错点。
- 不要省略关键代数变形。

科目：{question.get('subject', DEFAULT_SUBJECT)}
章节：{question.get('chapter', DEFAULT_CHAPTER)}
资料类型：{question.get('document_kind', DEFAULT_DOCUMENT_KIND)}
知识点：{question.get('category', DEFAULT_CATEGORY)}
元认知错因：{', '.join(question.get('meta_tags') or []) or question.get('mistake_reason') or '未填写'}
题目文字：
{question.get('ocr_text', '')[:4000]}
"""
        return call_llm(prompt, temperature=0.25) or fallback
    except Exception:
        print("LLM hint failed; falling back", file=sys.stderr)
        traceback.print_exc()
        return fallback


def generate_variations_with_ai(question: dict) -> str:
    fallback = (
        "难度梯度变式：\n"
        f"Base：同属「{question.get('category', DEFAULT_CATEGORY)}」，只换数字，不换核心逻辑。\n"
        "Advanced：改变求解目标，例如由求导改为求原函数、由判定改为求参数范围。\n"
        "Pro：跨章节综合，把本题知识点与前置概念组合训练。"
    )
    if not llm_enabled():
        return fallback + "\n\n当前未配置 AI 接口密钥，因此使用本地简版举一反三。"
    try:
        prompt = f"""
你是学习训练教练。请根据错题生成“难度梯度变式”，使用 Markdown + LaTeX。
科目：{question.get('subject', DEFAULT_SUBJECT)}
章节：{question.get('chapter', DEFAULT_CHAPTER)}
资料类型：{question.get('document_kind', DEFAULT_DOCUMENT_KIND)}
知识点：{question.get('category', DEFAULT_CATEGORY)} / {question.get('subcategory', '')}
错因：{', '.join(question.get('meta_tags') or []) or question.get('mistake_reason') or '未填写'}
备注：{question.get('user_note') or '无'}
原题文字：
{question.get('ocr_text', '')[:3500]}

请输出：
1. 题型迁移规律
2. Base：换数不换逻辑，只给 1 道题
3. Advanced：变换求解目标，只给 1 道题
4. Pro：跨章节综合，只给 1 道题
5. 每道题的训练目标，不给完整答案
"""
        return call_llm(prompt, temperature=0.45) or fallback
    except Exception:
        print("LLM variations failed; falling back", file=sys.stderr)
        traceback.print_exc()
        return fallback


def normalize_meta_tags(value) -> list[str]:
    if isinstance(value, list):
        raw = value
    else:
        try:
            raw = json.loads(value or "[]")
        except (TypeError, json.JSONDecodeError):
            raw = []
    return [tag for tag in raw if tag in META_TAGS]


def question_payload(row: sqlite3.Row) -> dict:
    item = dict(row)
    item["meta_tags"] = normalize_meta_tags(item.get("meta_tags"))
    if "document_kind" in item:
        item["document_kind"] = normalize_document_kind(item.get("document_kind"))
    return item


def get_meta_tag_stats(conn: sqlite3.Connection, doc_id: str | None = None) -> list[dict]:
    params = []
    where = "WHERE q.status IN ('做错', '半会', '需复习')"
    if doc_id:
        where += " AND q.document_id = ?"
        params.append(doc_id)
    rows = conn.execute(f"SELECT q.meta_tags FROM questions q {where}", params).fetchall()
    counts = {tag: 0 for tag in META_TAGS}
    for row in rows:
        for tag in normalize_meta_tags(row["meta_tags"]):
            counts[tag] += 1
    max_count = max(counts.values(), default=0) or 1
    return [{"tag": tag, "count": count, "ratio": round(count / max_count, 3)} for tag, count in counts.items()]


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
# L2 画像层：把 L0 统计 + L1 洞察滚动合成为「学习者档案」，存版本快照
# ==========================================================================
def gather_knowledge_stats(conn: sqlite3.Connection, scope: str = "__all__") -> list[dict]:
    """按 subject+category 聚合做题情况（只统计已做的题）。"""
    where = ""
    params: list[str] = []
    if scope and scope != "__all__":
        where = "WHERE d.subject = ?"
        params.append(scope)
    rows = conn.execute(
        f"""
        SELECT d.subject, q.category,
               COUNT(*) total,
               SUM(CASE WHEN q.status <> '未做' THEN 1 ELSE 0 END) done,
               SUM(CASE WHEN q.status = '做对' THEN 1 ELSE 0 END) correct,
               SUM(CASE WHEN q.status = '做错' THEN 1 ELSE 0 END) wrong,
               SUM(CASE WHEN q.status IN ('半会', '需复习') THEN 1 ELSE 0 END) review
        FROM questions q
        JOIN documents d ON d.id = q.document_id
        {where}
        GROUP BY d.subject, q.category
        HAVING q.category <> ''
        ORDER BY done DESC, total DESC
        """,
        params,
    ).fetchall()
    return [dict(row) for row in rows]


def load_insight_rows(conn: sqlite3.Connection, scope: str = "__all__") -> list[dict]:
    where = ""
    params: list[str] = []
    if scope and scope != "__all__":
        where = "WHERE i.subject = ?"
        params.append(scope)
    rows = conn.execute(
        f"""
        SELECT i.*, q.status, q.category
        FROM insights i
        JOIN questions q ON q.id = i.question_id
        {where}
        ORDER BY i.updated_at DESC
        """,
        params,
    ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        try:
            item["knowledge_points"] = json.loads(item.get("knowledge_points") or "[]")
        except (TypeError, json.JSONDecodeError):
            item["knowledge_points"] = []
        try:
            item["missing_prereq"] = json.loads(item.get("missing_prereq") or "[]")
        except (TypeError, json.JSONDecodeError):
            item["missing_prereq"] = []
        result.append(item)
    return result


def load_latest_profile(conn: sqlite3.Connection, scope: str = "__all__") -> dict | None:
    row = conn.execute(
        "SELECT * FROM learner_profile WHERE scope = ? ORDER BY version DESC LIMIT 1",
        (scope,),
    ).fetchone()
    if not row:
        return None
    item = dict(row)
    try:
        item["profile"] = json.loads(item.get("profile_json") or "{}")
    except (TypeError, json.JSONDecodeError):
        item["profile"] = {}
    return item


def mastery_band(score: float, evidence: int) -> str:
    if evidence == 0:
        return "未触及"
    if score >= 0.8:
        return "已掌握"
    if score >= 0.6:
        return "巩固中"
    if score >= 0.4:
        return "不稳"
    return "薄弱"


def merge_profile_locally(stats: list[dict], insights: list[dict], prev_profile: dict | None) -> dict:
    """确定性合成档案：掌握度用拉普拉斯平滑，趋势对比上一版。"""
    prev_state = (prev_profile or {}).get("knowledge_state", {}) if prev_profile else {}
    knowledge_state: dict[str, dict] = {}
    for stat in stats:
        category = stat["category"]
        done = stat["done"] or 0
        correct = stat["correct"] or 0
        # 拉普拉斯平滑：做得少的知识点掌握度自动向中位收敛，避免小样本假象
        mastery = round((correct + 1) / (done + 2), 3)
        prev = prev_state.get(category, {})
        prev_mastery = prev.get("mastery")
        if prev_mastery is None or done == 0:
            trend = "new" if done else "untouched"
        elif mastery > prev_mastery + 0.03:
            trend = "up"
        elif mastery < prev_mastery - 0.03:
            trend = "down"
        else:
            trend = "flat"
        knowledge_state[category] = {
            "subject": stat["subject"],
            "mastery": mastery,
            "band": mastery_band(mastery, done),
            "evidence": done,
            "correct": correct,
            "wrong": stat["wrong"] or 0,
            "review": stat["review"] or 0,
            "total": stat["total"] or 0,
            "trend": trend,
        }

    # 错因分布 + 反复误区（来自 L1 洞察）
    error_mode: dict[str, int] = {cause: 0 for cause in ROOT_CAUSES}
    misconception_counter: dict[str, dict] = {}
    prereq_counter: dict[str, int] = {}
    for ins in insights:
        cause = ins.get("root_cause")
        if cause in error_mode:
            error_mode[cause] += 1
        text = (ins.get("misconception") or "").strip()
        if text and text not in {"暂无具体误区记录"}:
            entry = misconception_counter.setdefault(text, {"text": text, "count": 0, "examples": []})
            entry["count"] += 1
            if len(entry["examples"]) < 3:
                entry["examples"].append(ins.get("question_id"))
        for prereq in ins.get("missing_prereq", []):
            prereq_counter[prereq] = prereq_counter.get(prereq, 0) + 1

    recurring = sorted(misconception_counter.values(), key=lambda x: x["count"], reverse=True)[:8]
    prereq_gaps = [p for p, _ in sorted(prereq_counter.items(), key=lambda kv: kv[1], reverse=True)][:8]

    # 学习速度：和上一版掌握度均值对比
    masteries = [v["mastery"] for v in knowledge_state.values() if v["evidence"] > 0]
    avg_mastery = round(sum(masteries) / len(masteries), 3) if masteries else 0.0
    prev_avg = (prev_profile or {}).get("avg_mastery")
    if prev_avg is None:
        velocity = f"首次建档，平均掌握度 {int(avg_mastery * 100)}%"
    else:
        delta = int((avg_mastery - prev_avg) * 100)
        arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "→")
        velocity = f"平均掌握度 {int(prev_avg * 100)}% {arrow} {int(avg_mastery * 100)}%"

    return {
        "knowledge_state": knowledge_state,
        "error_mode_profile": error_mode,
        "recurring_misconceptions": recurring,
        "prereq_gaps": prereq_gaps,
        "avg_mastery": avg_mastery,
        "velocity": velocity,
        "evidence_count": len(insights),
        "knowledge_count": len(knowledge_state),
        "source": "local",
    }


def polish_profile_with_ai(base_profile: dict, insights: list[dict]) -> dict:
    """有 key 时，让大模型在确定性档案之上补充人话总结，不改数字。"""
    if not llm_enabled():
        return base_profile
    try:
        weak = sorted(
            base_profile["knowledge_state"].items(),
            key=lambda kv: kv[1]["mastery"],
        )[:10]
        compact = {
            "weak_points": [
                {"name": k, "mastery": v["mastery"], "band": v["band"], "evidence": v["evidence"], "trend": v["trend"]}
                for k, v in weak
            ],
            "error_mode_profile": base_profile["error_mode_profile"],
            "recurring_misconceptions": [m["text"] for m in base_profile["recurring_misconceptions"][:6]],
            "prereq_gaps": base_profile["prereq_gaps"],
            "velocity": base_profile["velocity"],
        }
        prompt = f"""
你是一位学习数据分析助手，正在更新一名学生的学情档案。下面是基于真实做题数据算出的客观统计（数字已准确，请勿改动数字）：
{json.dumps(compact, ensure_ascii=False)}

请只输出一个 JSON 代码块，字段固定：
{{
  "headline": "一句话概括这名学生当前的学情画像",
  "knowledge_notes": {{"知识点名": "针对该薄弱点的一句具体诊断（结合掌握度与趋势）"}},
  "pattern_summary": "结合错因分布与反复误区，指出这名学生最值得警惕的1-2个习惯问题"
}}
knowledge_notes 只需覆盖上面 weak_points 里的知识点。
"""
        extra = sakura_ai.extract_json_block(call_llm(prompt, temperature=0.3))
        base_profile = {**base_profile, "source": "ai"}
        base_profile["headline"] = str(extra.get("headline", "")).strip()
        base_profile["pattern_summary"] = str(extra.get("pattern_summary", "")).strip()
        notes = extra.get("knowledge_notes") or {}
        if isinstance(notes, dict):
            for name, note in notes.items():
                if name in base_profile["knowledge_state"]:
                    base_profile["knowledge_state"][name]["note"] = str(note).strip()[:120]
        return base_profile
    except Exception:
        print("LLM profile polish failed; keeping local profile", file=sys.stderr)
        traceback.print_exc()
        return base_profile


def synthesize_profile(conn: sqlite3.Connection, want_ai: bool = True, scope: str = "__all__") -> dict:
    """读上一版 + 新增洞察 + 统计 → 合成新版本快照（增量迭代记忆）。"""
    prev = load_latest_profile(conn, scope)
    prev_profile = prev["profile"] if prev else None
    stats = gather_knowledge_stats(conn, scope)
    insights = load_insight_rows(conn, scope)
    profile = merge_profile_locally(stats, insights, prev_profile)
    if want_ai:
        profile = polish_profile_with_ai(profile, insights)

    version = (prev["version"] + 1) if prev else 1
    now = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        """
        INSERT INTO learner_profile (id, version, scope, profile_json, evidence_count, source, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (uuid.uuid4().hex, version, scope, json.dumps(profile, ensure_ascii=False), profile["evidence_count"], profile["source"], now),
    )
    return {"version": version, "scope": scope, "profile": profile, "created_at": now}


# ==========================================================================
# 学习档案状态（设置 + 缓存计划）
# ==========================================================================
def get_coach_state(conn: sqlite3.Connection) -> dict:
    row = conn.execute("SELECT * FROM coach_state WHERE id = ?", (COACH_STATE_ID,)).fetchone()
    if not row:
        conn.execute(
            "INSERT INTO coach_state (id, daily_minutes, exam_date, cadence, focus_subject, plan_json) VALUES (?, ?, ?, ?, ?, '{}')",
            (COACH_STATE_ID, DEFAULT_DAILY_MINUTES, EXAM_DATE.isoformat(), "immediate", ""),
        )
        row = conn.execute("SELECT * FROM coach_state WHERE id = ?", (COACH_STATE_ID,)).fetchone()
    item = dict(row)
    if not item.get("exam_date"):
        item["exam_date"] = EXAM_DATE.isoformat()
    return item


def save_coach_state(conn: sqlite3.Connection, **fields) -> dict:
    state = get_coach_state(conn)
    allowed = {"daily_minutes", "exam_date", "cadence", "focus_subject", "last_profile_at", "last_plan_at", "plan_json", "weather_city"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if updates:
        assignments = ", ".join(f"{k} = ?" for k in updates)
        conn.execute(f"UPDATE coach_state SET {assignments} WHERE id = ?", [*updates.values(), COACH_STATE_ID])
    return get_coach_state(conn)


def parse_exam_date(value: str | None) -> date:
    try:
        return date.fromisoformat((value or "").strip())
    except (TypeError, ValueError):
        return EXAM_DATE


def load_teacher_memories(conn: sqlite3.Connection, limit: int = 10) -> list[dict]:
    rows = conn.execute(
        "SELECT id, content, source, created_at FROM teacher_memory ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def save_teacher_memory(conn: sqlite3.Connection, content: str, source: str = "chat") -> dict:
    content = (content or "").strip()
    if not content:
        raise ValueError("记忆内容不能为空")
    memory = {
        "id": uuid.uuid4().hex,
        "content": content[:2000],
        "source": (source or "chat")[:30],
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    conn.execute(
        "INSERT INTO teacher_memory (id, content, source, created_at) VALUES (?, ?, ?, ?)",
        (memory["id"], memory["content"], memory["source"], memory["created_at"]),
    )
    return memory


def teacher_memory_prompt(conn: sqlite3.Connection) -> str:
    memories = load_teacher_memories(conn, limit=8)
    if not memories:
        return "暂无主动导入的对话记忆。"
    return "\n".join(f"- {item['content']}" for item in memories)


def parse_tags(value) -> list[str]:
    if isinstance(value, list):
        raw = value
    else:
        text = str(value or "").strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
            raw = parsed if isinstance(parsed, list) else re.split(r"[,，、\s]+", text)
        except json.JSONDecodeError:
            raw = re.split(r"[,，、\s]+", text)
    return [str(item).strip()[:30] for item in raw if str(item).strip()][:12]


def mentor_experience_to_dict(row) -> dict:
    item = dict(row)
    try:
        item["tags"] = json.loads(item.get("tags") or "[]")
    except (TypeError, json.JSONDecodeError):
        item["tags"] = []
    return item


def load_mentor_experiences(conn: sqlite3.Connection, limit: int = 30) -> list[dict]:
    rows = conn.execute(
        """
        SELECT * FROM mentor_experience
        ORDER BY reliability DESC, created_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [mentor_experience_to_dict(row) for row in rows]


def save_mentor_experience(conn: sqlite3.Connection, payload: dict) -> dict:
    content = str(payload.get("content", "")).strip()
    if not content:
        raise ValueError("经验内容不能为空")
    reliability = parse_positive_int(str(payload.get("reliability", "3")), 3) or 3
    reliability = max(1, min(5, reliability))
    item = {
        "id": uuid.uuid4().hex,
        "title": str(payload.get("title", "")).strip()[:80],
        "content": content[:3000],
        "subject": str(payload.get("subject", "")).strip()[:60],
        "tags": parse_tags(payload.get("tags", "")),
        "source": str(payload.get("source", "")).strip()[:80],
        "reliability": reliability,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    conn.execute(
        """
        INSERT INTO mentor_experience (id, title, content, subject, tags, source, reliability, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            item["id"], item["title"], item["content"], item["subject"],
            json.dumps(item["tags"], ensure_ascii=False), item["source"], item["reliability"], item["created_at"],
        ),
    )
    return item


def select_relevant_mentor_experiences(conn: sqlite3.Connection, message: str = "", subject_hint: str = "", limit: int = 5) -> list[dict]:
    experiences = load_mentor_experiences(conn, limit=80)
    text = (message or "").lower()
    tokens = [token for token in re.split(r"[,，、\s。！？；;:：/\\-]+", text) if len(token) >= 2]
    ranked = []
    for item in experiences:
        haystack = " ".join([
            item.get("title", ""),
            item.get("content", ""),
            item.get("subject", ""),
            " ".join(item.get("tags", [])),
        ]).lower()
        score = item.get("reliability", 3) * 0.2
        if subject_hint and subject_hint == item.get("subject"):
            score += 2
        for token in tokens:
            if token and token in haystack:
                score += 1
        if score > 0.5:
            ranked.append((score, item))
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in ranked[:limit]]


def recent_learning_evidence(conn: sqlite3.Connection, limit: int = 8) -> list[dict]:
    rows = conn.execute(
        """
        SELECT q.id, q.status, q.category, q.chapter, q.difficulty,
               q.mistake_reason, q.meta_tags, q.review_stage, q.retention_stage,
               q.next_review_at, q.created_at,
               d.subject, d.title document_title
        FROM questions q
        JOIN documents d ON d.id = q.document_id
        WHERE q.status IN ('做错', '半会', '需复习') OR q.ever_wrong = 1
        ORDER BY COALESCE(q.last_reviewed_at, q.created_at) DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    evidence = []
    for row in rows:
        item = dict(row)
        try:
            item["meta_tags"] = json.loads(item.get("meta_tags") or "[]")
        except (TypeError, json.JSONDecodeError):
            item["meta_tags"] = []
        evidence.append(item)
    return evidence


def build_ai_teacher_context(conn: sqlite3.Connection, message: str = "") -> dict:
    state = get_coach_state(conn)
    latest = load_latest_profile(conn)
    profile = latest["profile"] if latest else {}
    gaps = rank_gaps_from_profile(profile, top_n=5) if profile else []
    backlog = compute_review_backlog(conn, date.today())
    exam = parse_exam_date(state.get("exam_date"))
    days_left = (exam - date.today()).days
    daily_minutes = int(state.get("daily_minutes") or DEFAULT_DAILY_MINUTES)
    today_actions = build_today_actions(
        conn,
        gaps,
        backlog,
        daily_minutes,
        days_left < 14,
        state.get("focus_subject", ""),
    ) if profile else []
    recent_evidence = recent_learning_evidence(conn, limit=8)
    stats = gather_knowledge_stats(conn)[:10]
    subject_hint = state.get("focus_subject", "")
    mentor_experiences = select_relevant_mentor_experiences(conn, message, subject_hint, limit=5)
    return {
        "teacher_memories": teacher_memory_prompt(conn),
        "mentor_experiences": mentor_experiences,
        "mentor_experience_policy": "这些是外部经验参考，不是用户个人做题证据；只能辅助生成策略，不能替代本地错题统计。",
        "settings": {
            "daily_minutes": daily_minutes,
            "exam_date": exam.isoformat(),
            "days_left": days_left,
            "cadence": state.get("cadence", "immediate"),
            "focus_subject": subject_hint,
        },
        "profile": {
            "version": latest["version"] if latest else 0,
            "has_profile": bool(latest),
            "headline": profile.get("headline", ""),
            "pattern_summary": profile.get("pattern_summary", ""),
            "avg_mastery": profile.get("avg_mastery", 0),
            "evidence_count": profile.get("evidence_count", 0),
            "error_mode_profile": profile.get("error_mode_profile", {}),
            "recurring_misconceptions": profile.get("recurring_misconceptions", [])[:6],
            "prereq_gaps": profile.get("prereq_gaps", [])[:8],
        },
        "top_gaps": gaps,
        "review_backlog": backlog,
        "today_actions": today_actions,
        "recent_wrong_or_review_questions": recent_evidence,
        "knowledge_stats_sample": stats,
        "response_contract": {
            "must_use_evidence": True,
            "avoid_fabrication": True,
            "default_scaffolding": "概念提示 -> 关键一步 -> 完整说明",
            "must_end_with_actions": True,
        },
    }


# ==========================================================================
# L3 决策层：基于学习档案产出诊断 / 查缺排序 / 复习节奏 / 今日任务 / 容量估算
# ==========================================================================
def compute_review_backlog(conn: sqlite3.Connection, today: date) -> dict:
    today_iso = today.isoformat()
    week_iso = (today + timedelta(days=7)).isoformat()
    overdue = conn.execute(
        "SELECT COUNT(*) c FROM questions WHERE ever_wrong = 1 AND mastered_at IS NULL AND next_review_at IS NOT NULL AND date(next_review_at) < date(?)",
        (today_iso,),
    ).fetchone()["c"]
    due_today = conn.execute(
        "SELECT COUNT(*) c FROM questions WHERE ever_wrong = 1 AND mastered_at IS NULL AND next_review_at IS NOT NULL AND date(next_review_at) = date(?)",
        (today_iso,),
    ).fetchone()["c"]
    due_week = conn.execute(
        "SELECT COUNT(*) c FROM questions WHERE ever_wrong = 1 AND mastered_at IS NULL AND next_review_at IS NOT NULL AND date(next_review_at) <= date(?)",
        (week_iso,),
    ).fetchone()["c"]
    active_wrong = conn.execute(
        "SELECT COUNT(*) c FROM questions WHERE status IN ('做错', '半会', '需复习')",
    ).fetchone()["c"]
    return {"overdue": overdue, "due_today": due_today, "due_week": due_week, "active_wrong": active_wrong}


def rank_gaps_from_profile(profile: dict, top_n: int = 6) -> list[dict]:
    """从档案的 knowledge_state 排出查缺补漏优先级，每条附可核对的证据与处方。"""
    import math

    state = profile.get("knowledge_state", {})
    prereq_gaps = set(profile.get("prereq_gaps", []))
    error_mode = profile.get("error_mode_profile", {})
    main_cause = max(error_mode, key=error_mode.get) if error_mode and max(error_mode.values(), default=0) > 0 else ""

    ranked = []
    for name, info in state.items():
        evidence = info.get("evidence", 0)
        if evidence == 0:
            continue  # 未触及单独处理，这里只排已暴露薄弱的
        mastery = info.get("mastery", 0.5)
        weakness = 1 - mastery
        volume = math.log(1 + info.get("total", 0))
        prereq_boost = 1.35 if name in prereq_gaps else 1.0
        urgency = 1 + (info.get("wrong", 0) + info.get("review", 0)) * 0.12
        score = round(weakness * (0.5 + volume) * prereq_boost * urgency, 4)

        reason = f"正确率 {int(mastery * 100)}%（做对 {info.get('correct', 0)}/{evidence}）"
        if name in prereq_gaps:
            reason += "，且是其它薄弱点的前置 → 先补地基"
        if info.get("trend") == "down":
            reason += "，近期还在退步"
        elif info.get("trend") == "up":
            reason += "，已在回升、值得乘胜追击"
        prescription = ROOT_CAUSE_PRESCRIPTIONS.get(main_cause, "先精读同类范题，再闭卷重做巩固。")
        ranked.append({
            "name": name,
            "subject": info.get("subject", ""),
            "mastery": mastery,
            "band": info.get("band", ""),
            "evidence": evidence,
            "trend": info.get("trend", "flat"),
            "score": score,
            "reason": reason,
            "prescription": prescription,
            "note": info.get("note", ""),
        })
    ranked.sort(key=lambda x: x["score"], reverse=True)
    return ranked[:top_n]


def build_today_actions(conn: sqlite3.Connection, gaps: list[dict], backlog: dict, daily_minutes: int, in_sprint: bool, focus_subject: str) -> list[dict]:
    capacity = max(2, round(daily_minutes / STUDY_MINUTES_PER_QUESTION))
    actions = []
    used = 0

    review_n = min(backlog["due_today"] + backlog["overdue"], max(1, capacity // 2))
    if review_n > 0:
        actions.append({
            "kind": "review", "label": f"复习 {review_n} 道到期错题",
            "detail": f"含 {backlog['overdue']} 道逾期 + {backlog['due_today']} 道今日到期，先还复习账。",
            "count": review_n, "filter": {"status": "需复习"},
        })
        used += review_n

    for gap in gaps[:2]:
        if used >= capacity:
            break
        n = min(3, capacity - used)
        actions.append({
            "kind": "attack", "label": f"攻坚「{gap['name']}」{n} 道",
            "detail": gap["reason"], "count": n,
            "filter": {"category": gap["name"], "subject": gap.get("subject", "")},
        })
        used += n

    # 前置基础题（复用现有 foundation 逻辑）
    if used < capacity and gaps:
        subject = focus_subject or gaps[0].get("subject", "")
        dep_categories = []
        for gap in gaps:
            dep_categories.extend(KNOWLEDGE_DEPENDENCIES.get(gap["name"], []))
        foundations = find_foundation_questions(conn, subject, list(dict.fromkeys(dep_categories)), set())
        if foundations:
            n = min(len(foundations), capacity - used)
            actions.append({
                "kind": "foundation", "label": f"补 {n} 道前置基础题",
                "detail": "针对薄弱点的前置知识，先把地基补上再啃难题。",
                "count": n, "filter": {"subject": subject},
            })
            used += n

    if in_sprint:
        actions.append({
            "kind": "mock", "label": "限时做 1 套模拟卷",
            "detail": "整卷计时，做完按错因归档，模拟真实考场节奏。",
            "count": 1, "filter": {"kind": "模拟卷"},
        })

    return actions


def coach_narrative_ai(profile: dict, gaps: list[dict], backlog: dict, phases: list[dict], predictions: dict) -> str:
    local = sakura_profile.coach_narrative_local(profile, gaps, backlog, phases, predictions)
    if not llm_enabled():
        return local
    try:
        compact = {
            "headline": profile.get("headline", ""),
            "velocity": profile.get("velocity", ""),
            "pattern_summary": profile.get("pattern_summary", ""),
            "top_gaps": [{"name": g["name"], "reason": g["reason"], "prescription": g["prescription"]} for g in gaps[:5]],
            "backlog": backlog,
            "phases": [{"name": p["name"], "span": p["span"], "focus": p["focus"]} for p in phases],
            "predictions": predictions,
        }
        prompt = f"""
你是一位学习规划助手。下面是一名学生的学情档案与备考数据（数字均来自真实做题记录，请勿改动数字）：
{json.dumps(compact, ensure_ascii=False)}

请用中文写一段 250-400 字的个性化学习档案解读，要求：
1. 先点明这名学生当前的核心问题（结合 pattern_summary 与 top_gaps）。
2. 给出本阶段最该做的 2-3 件事，落到具体知识点和动作。
3. 结合剩余天数给一句务实的节奏建议与鼓励。
语气务实、可执行、不空泛、不堆砌套话；不要承诺提分或预测成绩。
"""
        return call_llm(prompt, temperature=0.5) or local
    except Exception:
        print("LLM coach narrative failed; falling back", file=sys.stderr)
        traceback.print_exc()
        return local


def build_coach_plan(conn: sqlite3.Connection, settings: dict, want_ai: bool = False) -> dict:
    """组装完整学习档案计划：诊断 + 查缺 + 阶段 + 今日 + 容量估算 + 摘要。"""
    profile_row = load_latest_profile(conn)
    profile = profile_row["profile"] if profile_row else {}
    today = date.today()
    exam = parse_exam_date(settings.get("exam_date"))
    days_left = (exam - today).days
    daily_minutes = int(settings.get("daily_minutes") or DEFAULT_DAILY_MINUTES)

    gaps = rank_gaps_from_profile(profile, top_n=6)
    backlog = compute_review_backlog(conn, today)
    phases = sakura_profile.build_study_phases(days_left, daily_minutes, STUDY_MINUTES_PER_QUESTION)
    in_sprint = days_left < 14
    today_actions = build_today_actions(conn, gaps, backlog, daily_minutes, in_sprint, settings.get("focus_subject", ""))
    predictions = sakura_profile.compute_predictions(profile, gaps, days_left, daily_minutes, STUDY_MINUTES_PER_QUESTION)
    narrative = coach_narrative_ai(profile, gaps, backlog, phases, predictions) if want_ai else sakura_profile.coach_narrative_local(profile, gaps, backlog, phases, predictions)

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "has_profile": bool(profile_row),
        "profile_version": profile_row["version"] if profile_row else 0,
        "evidence_count": profile.get("evidence_count", 0),
        "exam_date": exam.isoformat(),
        "days_left": days_left,
        "daily_minutes": daily_minutes,
        "diagnosis": {
            "headline": profile.get("headline", ""),
            "velocity": profile.get("velocity", ""),
            "pattern_summary": profile.get("pattern_summary", ""),
            "error_mode_profile": profile.get("error_mode_profile", {}),
            "recurring_misconceptions": profile.get("recurring_misconceptions", []),
            "knowledge_state": profile.get("knowledge_state", {}),
        },
        "gaps": gaps,
        "backlog": backlog,
        "phases": phases,
        "today": today_actions,
        "predictions": predictions,
        "narrative": narrative,
        "narrative_source": "ai" if (want_ai and llm_enabled()) else "local",
    }


# ==========================================================================
# 微信每日提醒（PushPlus）
# ==========================================================================
def build_daily_reminder(conn: sqlite3.Connection) -> dict:
    """汇总今日待复习错题，生成 PushPlus markdown 推送内容。"""
    today = date.today()
    backlog = compute_review_backlog(conn, today)
    state = get_coach_state(conn)
    exam = parse_exam_date(state.get("exam_date"))
    days_left = (exam - today).days
    due_total = backlog["overdue"] + backlog["due_today"]
    batch = create_practice_batch(conn, "daily_push")
    practice_url = f"{APP_PUBLIC_URL.rstrip('/')}/practice/{batch['id']}"

    rows = conn.execute(
        """
        SELECT d.subject, COALESCE(NULLIF(d.title, ''), d.filename) book, COUNT(*) n
        FROM questions q
        JOIN documents d ON d.id = q.document_id
        WHERE q.status IN ('做错', '需复习', '半会')
           OR (q.ever_wrong = 1 AND q.mastered_at IS NULL
               AND q.next_review_at IS NOT NULL AND date(q.next_review_at) <= date(?))
        GROUP BY d.subject, book
        ORDER BY n DESC
        LIMIT 8
        """,
        (today.isoformat(),),
    ).fetchall()

    title = f"📚 今日错题复习 · 待复习 {due_total} 道 · 距考试 {days_left} 天"
    lines = [
        f"### 📚 今日错题复习提醒",
        f"- 🗓 今天：{today.month}月{today.day}日，距考试还有 **{days_left}** 天",
        f"- 🔴 到期待复习：**{due_total}** 道（逾期 {backlog['overdue']} + 今日 {backlog['due_today']}）",
        f"- 📒 在练错题总数：{backlog['active_wrong']} 道",
        "",
    ]
    if rows:
        lines.append("**按做题本分布：**")
        for r in rows:
            lines.append(f"- {r['subject'] or '未分类'} / {r['book']}：{r['n']} 道")
    else:
        lines.append("🎉 今天没有到期的错题，保持节奏，可以预习新内容！")
    lines.append("")
    lines.append(f"👉 [手机快速回填本批次 {batch['question_count']} 道题]({practice_url})")
    lines.append(f"💻 [打开完整做题集]({APP_PUBLIC_URL})")
    return {
        "title": title,
        "content": "\n".join(lines),
        "due_total": due_total,
        "days_left": days_left,
        "batch_id": batch["id"],
        "practice_url": practice_url,
    }


def weather_city_from_state(conn: sqlite3.Connection) -> str:
    state = get_coach_state(conn)
    return (state.get("weather_city") or WEATHER_CITY or "北京").strip()


def build_weather_reminder(conn: sqlite3.Connection, city: str | None = None) -> dict:
    city = (city or weather_city_from_state(conn)).strip()
    info = sakura_weather.fetch_tomorrow_weather(city)
    display_city = info["resolved_city"] or city
    title = f"明天天气提醒 · {display_city}"
    lines = [
        f"### 明天天气提醒：{display_city}",
        f"- 日期：**{info['date']}**",
        f"- 天气：**{info['weather_text']}**",
        f"- 温度：**{info['temp_min']}°C ~ {info['temp_max']}°C**",
        f"- 降水概率：**{info['rain_probability']}%**",
        f"- 最大风速：**{info['wind_max']} km/h**",
        "",
        "晚上提前看一下天气，第二天出门少一点临时慌张。",
        f"👉 [打开 Sakura 做题集]({APP_PUBLIC_URL.rstrip('/')})",
    ]
    return {"title": title, "content": "\n".join(lines), "weather": info}


def send_notification(title: str, content: str) -> dict:
    return sakura_notifications.send_notification(
        title,
        content,
        wework_webhook=WEWORK_BOT_WEBHOOK,
        pushplus_token=PUSHPLUS_TOKEN,
    )


def today_quote() -> str:
    return MOTIVATIONAL_QUOTES[date.today().toordinal() % len(MOTIVATIONAL_QUOTES)]


def is_checked_in(conn: sqlite3.Connection, day: date | None = None) -> bool:
    day = day or date.today()
    row = conn.execute("SELECT 1 FROM checkins WHERE day = ?", (day.isoformat(),)).fetchone()
    return row is not None


def mark_checkin(conn: sqlite3.Connection, day: date | None = None) -> None:
    day = day or date.today()
    conn.execute(
        "INSERT OR IGNORE INTO checkins (day, created_at) VALUES (?, ?)",
        (day.isoformat(), datetime.now().isoformat(timespec="seconds")),
    )


def build_morning_reminder(conn: sqlite3.Connection) -> dict:
    """早安推送：励志金句 + 今日待复习 + 打卡链接。"""
    base = build_daily_reminder(conn)
    checkin_url = f"{APP_PUBLIC_URL.rstrip('/')}/api/today/done"
    content = (
        f"> 「{today_quote()}」\n\n"
        f"{base['content']}\n\n"
        f"---\n"
        f"做完今天的复习了吗？点这里打卡：\n"
        f"✅ [我已完成]({checkin_url})\n\n"
        f"（晚上 8 点会检查；没打卡的话，某人会来念你 👀）"
    )
    return {
        "title": f"🌅 早安 · {base['title']}",
        "content": content,
        "due_total": base["due_total"],
        "batch_id": base.get("batch_id", ""),
        "practice_url": base.get("practice_url", ""),
    }


def build_night_check(conn: sqlite3.Connection) -> dict:
    """晚间检测：已打卡则鼓励，未打卡则狠话。返回 dict，skip=True 表示无需发送。"""
    if is_checked_in(conn):
        return {
            "skip": False,
            "title": "🌙 今日已完成 · 干得漂亮",
            "content": f"> 「{today_quote()}」\n\n今天的复习已打卡完成 ✅ 早点休息，明天继续保持节奏。",
        }
    nag = NAG_MESSAGES[date.today().toordinal() % len(NAG_MESSAGES)]
    backlog = compute_review_backlog(conn, date.today())
    due_total = backlog["overdue"] + backlog["due_today"]
    content = (
        f"### ⏰ 今日未打卡\n\n"
        f"{nag}\n\n"
        f"- 还有 **{due_total}** 道到期错题等着你\n"
        f"👉 [现在去做]({APP_PUBLIC_URL.rstrip('/')}) · 做完点 [✅ 我已完成]({APP_PUBLIC_URL.rstrip('/')}/api/today/done)"
    )
    return {"skip": False, "title": "⏰ 今天还没打卡，别装看不见", "content": content}


def build_mistakes_pdf(conn: sqlite3.Connection, query: dict, mistakes_only: bool = True) -> tuple[bytes, int]:
    """把筛选后的题目导出为 PDF。优先复制原始 PDF 对应页，原文件缺失时再退回题图。"""
    where, params = build_question_filters(
        query, ("category", "status", "document_id", "chapter", "subject", "search")
    )
    raw_ids = query.get("ids", [""])[0].strip()
    if raw_ids:
        selected_ids = [item for item in raw_ids.split(",") if re.fullmatch(r"[0-9a-fA-F]{32}", item)]
        if selected_ids:
            placeholders = ",".join("?" for _ in selected_ids)
            where = f"{where} AND q.id IN ({placeholders})" if where else f"WHERE q.id IN ({placeholders})"
            params.extend(selected_ids)
        else:
            where = f"{where} AND 1 = 0" if where else "WHERE 1 = 0"
    status_group = query.get("status_group", [""])[0]
    if status_group == "review" and not raw_ids:
        cond = "(q.status IN ('半会', '需复习') OR (q.ever_wrong = 1 AND q.mastered_at IS NULL AND q.status <> '做错'))"
        where = f"{where} AND {cond}" if where else f"WHERE {cond}"
    if mistakes_only:
        cond = "(q.status IN ('做错', '半会', '需复习') OR (q.ever_wrong = 1 AND q.mastered_at IS NULL))"
        where = f"{where} AND {cond}" if where else f"WHERE {cond}"
    rows = conn.execute(
        f"""
        SELECT q.*, COALESCE(NULLIF(d.title, ''), d.filename) document_title, d.subject, d.stored_path
        FROM questions q
        JOIN documents d ON d.id = q.document_id
        {where}
        ORDER BY d.subject ASC, document_title ASC, q.seq_no ASC, q.page_number ASC
        """,
        params,
    ).fetchall()

    return sakura_export.build_mistakes_pdf(rows, normalize_meta_tags)


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
    pages = []
    last_chapter = DEFAULT_CHAPTER
    pdf = fitz.open(pdf_path)
    try:
        for index, page in enumerate(pdf, start=1):
            text = page.get_text("text", sort=True).strip()
            if document_kind == MOCK_PAPER_KIND:
                pages.append({"page_number": index, "text": text, "chapter": MOCK_PAPER_CHAPTER})
                continue
            extracted = extract_chapter_from_page(page, text)
            if extracted != DEFAULT_CHAPTER:
                last_chapter = extracted
            chapter = last_chapter if last_chapter != DEFAULT_CHAPTER else extracted
            pages.append({"page_number": index, "text": text, "chapter": normalize_chapter(chapter)})
    finally:
        pdf.close()
    return pages


def parse_positive_int(value: str, fallback: int | None = None) -> int | None:
    try:
        parsed = int(str(value).strip())
        return parsed if parsed > 0 else fallback
    except (TypeError, ValueError):
        return fallback


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
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", filename) or "questions.pdf"
    pdf_path = UPLOAD_DIR / f"{doc_id}_{safe_name}"
    pdf_path.write_bytes(pdf_bytes)
    title = title.strip() or Path(filename).stem
    subject = normalize_label(subject, DEFAULT_SUBJECT)
    document_kind = normalize_document_kind(document_kind)

    now = datetime.now().isoformat(timespec="seconds")
    inserted = []
    pdf = fitz.open(pdf_path)
    last_chapter = DEFAULT_CHAPTER
    try:
        with connect() as conn:
            conn.execute(
                """
                INSERT INTO documents (id, title, subject, document_kind, filename, stored_path, page_count, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (doc_id, title, subject, document_kind, filename, str(pdf_path), pdf.page_count, now),
            )
            page_start = max(start_page or 1, 1)
            page_end = min(end_page or pdf.page_count, pdf.page_count)
            if page_start > page_end:
                raise ValueError("页码范围无效，请检查起止页。")
            seq_no = 0
            previous_question_id = ""
            previous_question_image: Path | None = None
            previous_question_value: int | None = None
            for index in range(page_start, page_end + 1):
                page = pdf[index - 1]
                text = page.get_text("text", sort=True).strip()
                if document_kind == MOCK_PAPER_KIND:
                    chapter_hint = MOCK_PAPER_CHAPTER
                else:
                    extracted_chapter = extract_chapter_from_page(page, text)
                    if extracted_chapter != DEFAULT_CHAPTER:
                        last_chapter = extracted_chapter
                    chapter_hint = last_chapter if last_chapter != DEFAULT_CHAPTER else extracted_chapter
                starts = detect_question_starts(page) if document_kind == MOCK_PAPER_KIND and split_questions else []
                if (
                    starts
                    and previous_question_id
                    and previous_question_image
                    and previous_question_value is not None
                    and starts[0]["value"] == previous_question_value + 1
                    and starts[0]["y"] > page.rect.height * 0.12
                ):
                    continuation_clip = fitz.Rect(
                        page.rect.x0 + 18,
                        page.rect.y0 + 16,
                        page.rect.x1 - 18,
                        starts[0]["y"] - 4,
                    )
                    if continuation_clip.height > 36:
                        append_page_clip_to_question_image(page, continuation_clip, previous_question_image)
                        continuation_text = page.get_text("text", sort=True, clip=continuation_clip).strip()
                        if continuation_text:
                            conn.execute(
                                "UPDATE questions SET ocr_text = trim(coalesce(ocr_text, '') || char(10) || ?) WHERE id = ?",
                                (continuation_text, previous_question_id),
                            )
                slices = detect_question_slices(page, starts) if document_kind == MOCK_PAPER_KIND and split_questions else []
                if not slices:
                    slices = [{"question_no": "", "clip": None}]
                for slice_index, item in enumerate(slices, start=1):
                    seq_no += 1
                    q_id = uuid.uuid4().hex
                    clip = item.get("clip")
                    if clip:
                        image_path = PAGE_DIR / f"{doc_id}_page_{index:03d}_q{slice_index:02d}.png"
                        render_page_clip_image(page, clip, image_path)
                        question_text = page.get_text("text", sort=True, clip=clip).strip()
                    else:
                        image_path = PAGE_DIR / f"{doc_id}_page_{index:03d}.png"
                        render_page_image(page, image_path)
                        question_text = text
                    classification = classify_question_locally(question_text or text, subject, chapter_hint, document_kind)
                    conn.execute(
                        """
                        INSERT INTO questions (
                            id, document_id, page_number, seq_no, question_no, image_path, ocr_text, category,
                            subcategory, chapter, difficulty, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            q_id,
                            doc_id,
                            index,
                            seq_no,
                            str(item.get("question_no") or ""),
                            str(image_path),
                            question_text or text,
                            classification["category"],
                            classification["subcategory"],
                            classification["chapter"],
                            classification["difficulty"],
                            now,
                        ),
                    )
                    inserted.append(
                        {
                            "id": q_id,
                            "page_number": index,
                            "seq_no": seq_no,
                            "question_no": str(item.get("question_no") or ""),
                            "category": classification["category"],
                            "subcategory": classification["subcategory"],
                            "chapter": classification["chapter"],
                        }
                    )
                    previous_question_id = q_id
                    previous_question_image = image_path
                    value = item.get("question_value")
                    previous_question_value = int(value) if value is not None else None
    finally:
        pdf.close()

    return {
        "document_id": doc_id,
        "title": title,
        "subject": subject,
        "document_kind": document_kind,
        "filename": filename,
        "page_count": len(inserted),
        "questions": inserted,
    }


def unlink_if_inside_data(path_value: str) -> None:
    if not path_value:
        return
    path = Path(path_value).resolve()
    if str(path).startswith(str(DATA_DIR.resolve())) and path.exists() and path.is_file():
        path.unlink()


def prune_empty_documents(conn: sqlite3.Connection) -> int:
    rows = conn.execute(
        """
        SELECT d.id, d.stored_path
        FROM documents d
        LEFT JOIN questions q ON q.document_id = d.id
        GROUP BY d.id
        HAVING COUNT(q.id) = 0
        """
    ).fetchall()
    for row in rows:
        unlink_if_inside_data(row["stored_path"])
        conn.execute("DELETE FROM documents WHERE id = ?", (row["id"],))
    return len(rows)


MIGRATION_JOBS: dict[str, dict] = {}
MIGRATION_LOCK = threading.Lock()


def set_migration_job(job_id: str, **updates) -> None:
    with MIGRATION_LOCK:
        job = MIGRATION_JOBS.setdefault(job_id, {})
        job.update(updates)
        job["updated_at"] = datetime.now().isoformat(timespec="seconds")


def get_migration_job(job_id: str) -> dict | None:
    with MIGRATION_LOCK:
        job = MIGRATION_JOBS.get(job_id)
        return dict(job) if job else None


def run_migration_import_job(job_id: str, upload_path: Path) -> None:
    set_migration_job(job_id, status="running", message="Restoring backup...")
    try:
        result = sakura_backup.restore_backup_zip(
            upload_path.read_bytes(),
            root=ROOT,
            db_path=DB_PATH,
            folders={"uploads": UPLOAD_DIR, "pages": PAGE_DIR},
            ensure_dirs=ensure_dirs,
            init_db=init_db,
        )
        set_migration_job(job_id, status="done", message="Import completed.", result=result)
    except Exception as exc:
        traceback.print_exc()
        set_migration_job(job_id, status="failed", message=str(exc), error=str(exc))
    finally:
        try:
            upload_path.unlink(missing_ok=True)
        except Exception:
            pass


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
            if parsed.path == "/api/documents":
                return self.handle_documents()
            if parsed.path == "/api/textbooks":
                return self.handle_textbooks()
            if parsed.path.startswith("/api/textbooks/") and "/pages/" in parsed.path:
                parts = parsed.path.split("/")
                return self.handle_textbook_page(parts[3], int(parts[5]))
            if parsed.path.startswith("/api/documents/") and parsed.path.endswith("/chapter-stats"):
                doc_id = parsed.path.split("/")[-2]
                return self.handle_chapter_stats(doc_id)
            if parsed.path == "/api/questions":
                return self.handle_questions(parse_qs(parsed.query))
            if parsed.path == "/api/daily":
                return self.handle_daily()
            if parsed.path.startswith("/api/practice/"):
                batch_id = parsed.path.split("/")[-1]
                return self.handle_practice_batch_get(batch_id)
            if parsed.path == "/api/daily/rules":
                return self.handle_daily_rules_get()
            if parsed.path == "/api/daily/rule-options":
                return self.handle_daily_rule_options(parse_qs(parsed.query))
            if parsed.path == "/api/backup/export":
                return self.handle_backup_export(parse_qs(parsed.query))
            if parsed.path == "/api/backup/import-status":
                return self.handle_backup_import_status(parse_qs(parsed.query))
            if parsed.path == "/api/reflection":
                return self.handle_reflection_preview(parse_qs(parsed.query))
            if parsed.path == "/api/countdown":
                return self.handle_countdown()
            if parsed.path == "/api/quote":
                return self.handle_quote()
            if parsed.path == "/api/coach":
                return self.handle_coach_get()
            if parsed.path == "/api/coach/settings":
                return self.handle_coach_settings_get()
            if parsed.path == "/api/weather/settings":
                return self.handle_weather_settings_get()
            if parsed.path == "/api/weather/preview":
                return self.handle_weather_preview(parse_qs(parsed.query))
            if parsed.path == "/api/ai-chat/memory":
                return self.handle_ai_memory_get()
            if parsed.path == "/api/mentor-experience":
                return self.handle_mentor_experience_get()
            if parsed.path == "/api/llm/settings":
                return self.handle_llm_settings_get()
            if parsed.path in ("/api/notification/settings", "/api/notify/settings"):
                return self.handle_notification_settings_get()
            if parsed.path == "/api/reminder/settings":
                return self.handle_reminder_settings_get()
            if parsed.path == "/api/today/done":
                return self.handle_today_done()
            if parsed.path == "/api/today/status":
                return self.handle_today_status()
            if parsed.path == "/api/export/mistakes":
                return self.handle_export_mistakes(parse_qs(parsed.query))
            if parsed.path == "/api/reflections":
                return self.handle_reflection_history()
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
            if parsed.path == "/api/upload":
                return self.handle_upload()
            if parsed.path == "/api/textbooks/upload":
                return self.handle_textbook_upload()
            if parsed.path == "/api/textbooks/chat":
                return self.handle_textbook_chat()
            if parsed.path == "/api/textbooks/memory":
                return self.handle_textbook_memory()
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
            if parsed.path == "/api/reflection":
                return self.handle_reflection()
            if parsed.path == "/api/profile/refresh":
                return self.handle_profile_refresh()
            if parsed.path == "/api/coach":
                return self.handle_coach_post()
            if parsed.path == "/api/coach/settings":
                return self.handle_coach_settings_post()
            if parsed.path == "/api/daily/rules":
                return self.handle_daily_rule_save()
            if parsed.path == "/api/backup/import":
                return self.handle_backup_import()
            if parsed.path == "/api/weather/settings":
                return self.handle_weather_settings_post()
            if parsed.path == "/api/weather/reminder":
                return self.handle_weather_reminder_preview()
            if parsed.path.startswith("/api/practice/") and "/questions/" in parsed.path:
                parts = parsed.path.strip("/").split("/")
                return self.handle_practice_feedback(parts[2], parts[4])
            if parsed.path == "/api/push/daily":
                return self.handle_push_daily()
            if parsed.path == "/api/push/morning":
                return self.handle_push_morning()
            if parsed.path == "/api/push/night":
                return self.handle_push_night()
            if parsed.path == "/api/push/weather":
                return self.handle_push_weather()
            if parsed.path == "/api/ai-chat":
                return self.handle_ai_chat()
            if parsed.path == "/api/ai-chat/memory":
                return self.handle_ai_memory_post()
            if parsed.path == "/api/mentor-experience":
                return self.handle_mentor_experience_post()
            if parsed.path == "/api/llm/settings":
                return self.handle_llm_settings_post()
            if parsed.path in ("/api/notification/settings", "/api/notify/settings"):
                return self.handle_notification_settings_post()
            if parsed.path == "/api/reminder/settings":
                return self.handle_reminder_settings_post()
            return text_response(self, "Not found", HTTPStatus.NOT_FOUND)
        except Exception as exc:
            traceback.print_exc()
            return json_response(self, {"error": str(exc)}, 500)

    def do_DELETE(self) -> None:
        try:
            parsed = urlparse(self.path)
            if not self.require_auth(parsed.path):
                return
            if parsed.path == "/api/coach/plan":
                return self.handle_clear_coach_plan()
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
        resolved = path.resolve()
        if not str(resolved).startswith(str(ROOT)) or not resolved.exists() or resolved.is_dir():
            return text_response(self, "Not found", HTTPStatus.NOT_FOUND)
        content_types = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".pdf": "application/pdf",
        }
        body = resolved.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_types.get(resolved.suffix.lower(), "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

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
        split_questions = form.getfirst("split_questions", "") in {"1", "true", "on", "yes"}
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
            rows = conn.execute(
                """
                SELECT t.*, COUNT(p.id) saved_pages
                FROM textbooks t
                LEFT JOIN textbook_pages p ON p.textbook_id = t.id
                GROUP BY t.id
                ORDER BY t.created_at DESC
                """
            ).fetchall()
        return json_response(self, {"textbooks": [textbook_to_dict(row) for row in rows]})

    def handle_textbook_page(self, textbook_id: str, page_number: int) -> None:
        with connect() as conn:
            book, page = build_textbook_context(conn, textbook_id, page_number)
        return json_response(self, {"textbook": book, "page": page})

    def handle_delete_textbook(self, textbook_id: str) -> None:
        with connect() as conn:
            book = conn.execute("SELECT stored_path FROM textbooks WHERE id = ?", (textbook_id,)).fetchone()
            if not book:
                return json_response(self, {"error": "教材不存在。"}, 404)
            page_rows = conn.execute("SELECT image_path FROM textbook_pages WHERE textbook_id = ?", (textbook_id,)).fetchall()
            for row in page_rows:
                unlink_if_inside_data(row["image_path"])
            unlink_if_inside_data(book["stored_path"])
            conn.execute("DELETE FROM textbook_chats WHERE textbook_id = ?", (textbook_id,))
            conn.execute("DELETE FROM textbook_pages WHERE textbook_id = ?", (textbook_id,))
            conn.execute("DELETE FROM textbooks WHERE id = ?", (textbook_id,))
        return json_response(self, {"ok": True})

    def handle_textbook_chat(self) -> None:
        payload = self.read_json()
        textbook_id = str(payload.get("textbook_id", "")).strip()
        page_number = parse_positive_int(str(payload.get("page_number", "")), 1) or 1
        paragraph_index = parse_positive_int(str(payload.get("paragraph_index", "")), 0) or 0
        message = str(payload.get("message", "")).strip()
        history = payload.get("history") if isinstance(payload.get("history"), list) else []
        if not textbook_id or not message:
            return json_response(self, {"error": "请选择教材并输入问题。"}, 400)
        with connect() as conn:
            book, page = build_textbook_context(conn, textbook_id, page_number, paragraph_index)
            now = datetime.now().isoformat(timespec="seconds")
            conn.execute(
                "INSERT INTO textbook_chats (id, textbook_id, page_number, role, content, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (uuid.uuid4().hex, textbook_id, page_number, "user", message[:4000], now),
            )
            try:
                answer = explain_textbook_with_ai(book, page, message, history)
            except Exception as exc:
                traceback.print_exc()
                return json_response(self, {"error": f"AI 精读失败：{exc}"}, 500)
            conn.execute(
                "INSERT INTO textbook_chats (id, textbook_id, page_number, role, content, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (uuid.uuid4().hex, textbook_id, page_number, "assistant", answer[:8000], datetime.now().isoformat(timespec="seconds")),
            )
        return json_response(self, {"answer": answer, "textbook": book, "page": page, "has_key": llm_enabled()})

    def handle_textbook_memory(self) -> None:
        payload = self.read_json()
        textbook_id = str(payload.get("textbook_id", "")).strip()
        page_number = parse_positive_int(str(payload.get("page_number", "")), 1) or 1
        paragraph_index = parse_positive_int(str(payload.get("paragraph_index", "")), 0) or 0
        history = payload.get("history") if isinstance(payload.get("history"), list) else []
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
            prune_empty_documents(conn)
            rows = conn.execute(
                """
                SELECT d.*,
                       COUNT(q.id) question_count,
                       SUM(CASE WHEN q.status = '做错' THEN 1 ELSE 0 END) wrong_count,
                       SUM(CASE WHEN q.status IN ('需复习', '半会') THEN 1 ELSE 0 END) review_count
                FROM documents d
                LEFT JOIN questions q ON q.document_id = d.id
                GROUP BY d.id
                ORDER BY d.created_at DESC
                """
            ).fetchall()
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
            doc = conn.execute("SELECT id FROM documents WHERE id = ?", (doc_id,)).fetchone()
            if not doc:
                return json_response(self, {"error": "做题本不存在。"}, 404)
            conn.execute(
                "UPDATE documents SET title = ?, subject = ?, document_kind = ? WHERE id = ?",
                (title, subject, document_kind, doc_id),
            )
            updated = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
        return json_response(self, {"ok": True, "document": document_to_dict(updated)})

    def handle_questions(self, query: dict) -> None:
        where, params = build_question_filters(
            query,
            ("category", "status", "document_id", "chapter", "subject", "search"),
        )
        with connect() as conn:
            rows = conn.execute(
                f"""
                SELECT q.*, d.filename, d.title document_title, d.subject, d.document_kind
                FROM questions q
                JOIN documents d ON d.id = q.document_id
                {where}
                ORDER BY q.created_at DESC, q.page_number ASC
                """,
                params,
            ).fetchall()
            stats = conn.execute(
                """
                SELECT q.category, COUNT(*) total,
                       SUM(CASE WHEN status = '做错' THEN 1 ELSE 0 END) wrong
                FROM questions q
                JOIN documents d ON d.id = q.document_id
                {where}
                GROUP BY q.category
                ORDER BY total DESC
                """.format(where=where),
                params,
            ).fetchall()
            subject_stats = conn.execute(
                """
                SELECT d.subject, COUNT(*) total,
                       SUM(CASE WHEN q.status = '做错' THEN 1 ELSE 0 END) wrong
                FROM questions q
                JOIN documents d ON d.id = q.document_id
                {where}
                GROUP BY d.subject
                ORDER BY total DESC
                """.format(where=where),
                params,
            ).fetchall()
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
            row = conn.execute(
                """
                SELECT q.*, d.filename, d.title document_title, d.subject, d.document_kind
                FROM questions q
                JOIN documents d ON d.id = q.document_id
                WHERE q.id = ?
                """,
                (q_id,),
            ).fetchone()
        if not row:
            return json_response(self, {"error": "题目不存在。"}, 404)
        return json_response(self, row_to_dict(row))

    def handle_delete_question(self, q_id: str) -> None:
        with connect() as conn:
            row = conn.execute("SELECT document_id, image_path FROM questions WHERE id = ?", (q_id,)).fetchone()
            if not row:
                return json_response(self, {"error": "题目不存在。"}, 404)
            doc_id = row["document_id"]
            unlink_if_inside_data(row["image_path"])
            conn.execute("DELETE FROM questions WHERE id = ?", (q_id,))
            remaining = conn.execute("SELECT COUNT(*) remaining FROM questions WHERE document_id = ?", (doc_id,)).fetchone()["remaining"]
            document_deleted = False
            if remaining == 0:
                doc = conn.execute("SELECT stored_path FROM documents WHERE id = ?", (doc_id,)).fetchone()
                if doc:
                    unlink_if_inside_data(doc["stored_path"])
                conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
                document_deleted = True
        return json_response(self, {"ok": True, "document_id": doc_id, "document_deleted": document_deleted})

    def handle_delete_document(self, doc_id: str) -> None:
        with connect() as conn:
            doc = conn.execute("SELECT stored_path FROM documents WHERE id = ?", (doc_id,)).fetchone()
            if not doc:
                return json_response(self, {"error": "做题本不存在。"}, 404)
            question_rows = conn.execute("SELECT image_path FROM questions WHERE document_id = ?", (doc_id,)).fetchall()
            for row in question_rows:
                unlink_if_inside_data(row["image_path"])
            unlink_if_inside_data(doc["stored_path"])
            conn.execute("DELETE FROM questions WHERE document_id = ?", (doc_id,))
            conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        return json_response(self, {"ok": True})

    def handle_delete_reflection(self, ref_id: str) -> None:
        with connect() as conn:
            row = conn.execute("SELECT id FROM reflections WHERE id = ?", (ref_id,)).fetchone()
            if not row:
                return json_response(self, {"error": "历史知识归档不存在。"}, 404)
            conn.execute("DELETE FROM reflections WHERE id = ?", (ref_id,))
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
            doc = conn.execute("SELECT stored_path, document_kind, subject FROM documents WHERE id = ?", (doc_id,)).fetchone()
            if not doc:
                return json_response(self, {"error": "做题本不存在。"}, 404)
            pdf_path = Path(doc["stored_path"])
            if not pdf_path.exists():
                return json_response(self, {"error": "原始 PDF 文件不存在，无法重扫。"}, 404)
            document_kind = normalize_document_kind(doc["document_kind"])
            pages = extract_text_and_chapters(pdf_path, document_kind)
            updated = 0
            for page in pages:
                category, subcategory, difficulty = classify_by_rules(page["text"])
                if document_kind != MOCK_PAPER_KIND and category == DEFAULT_CATEGORY and page["chapter"] != DEFAULT_CHAPTER:
                    category = page["chapter"]
                    subcategory = "章节归类"
                cursor = conn.execute(
                    """
                    UPDATE questions
                    SET ocr_text = ?, chapter = ?, category = ?, subcategory = ?, difficulty = ?
                    WHERE document_id = ? AND page_number = ?
                    """,
                    (
                        page["text"],
                        page["chapter"],
                        category,
                        subcategory,
                        difficulty,
                        doc_id,
                        page["page_number"],
                    ),
                )
                updated += max(cursor.rowcount, 0)
        return json_response(self, {"ok": True, "pages": len(pages), "updated": updated})

    def handle_update_question(self, q_id: str) -> None:
        payload = self.read_json()
        allowed = {
            "status", "mistake_reason", "meta_tags", "user_note", "category",
            "subcategory", "chapter", "difficulty", "question_no",
            "ai_analysis", "ai_hint", "ai_variations",
        }
        updates = {k: v for k, v in payload.items() if k in allowed}
        if not updates:
            return json_response(self, {"error": "没有可更新字段。"}, 400)
        with connect() as conn:
            current = conn.execute("SELECT * FROM questions WHERE id = ?", (q_id,)).fetchone()
            if not current:
                return json_response(self, {"error": "题目不存在。"}, 404)
            if "meta_tags" in updates:
                updates["meta_tags"] = json.dumps(normalize_meta_tags(updates["meta_tags"]), ensure_ascii=False)
            if updates.get("status") in WRONGISH_STATUSES:
                existing_tags = normalize_meta_tags(updates.get("meta_tags", current["meta_tags"]))
                if not existing_tags:
                    return json_response(self, {"error": "标记错题前，请至少选择一个元认知错因标签。"}, 400)
            if updates.get("status") in {*WRONGISH_STATUSES, "做对"}:
                updates["last_reviewed_at"] = datetime.now().isoformat(timespec="seconds")
                updates["review_count"] = "review_count + 1"
                updates.update(schedule_for_status(current, updates["status"]))
            assignments = []
            params = []
            for key, value in updates.items():
                if key == "review_count":
                    assignments.append("review_count = review_count + 1")
                else:
                    assignments.append(f"{key} = ?")
                    params.append(value)
            params.append(q_id)
            conn.execute(f"UPDATE questions SET {', '.join(assignments)} WHERE id = ?", params)
            row = conn.execute(
                """
                SELECT q.*, d.filename, d.title document_title, d.subject, d.document_kind
                FROM questions q
                JOIN documents d ON d.id = q.document_id
                WHERE q.id = ?
                """,
                (q_id,),
            ).fetchone()
        return json_response(self, row_to_dict(row))

    def handle_analyze(self, q_id: str) -> None:
        with connect() as conn:
            row = conn.execute(
                """
                SELECT q.*, d.subject, d.document_kind
                FROM questions q
                JOIN documents d ON d.id = q.document_id
                WHERE q.id = ?
                """,
                (q_id,),
            ).fetchone()
            if not row:
                return json_response(self, {"error": "题目不存在。"}, 404)
            question = question_payload(row)
            analysis, insight = analyze_and_extract_with_ai(question)
            conn.execute("UPDATE questions SET ai_analysis = ? WHERE id = ?", (analysis, q_id))
            upsert_insight(conn, question, insight)
        return json_response(self, {"ai_analysis": analysis, "insight": insight})

    def handle_hint(self, q_id: str) -> None:
        payload = self.read_json()
        level = parse_positive_int(str(payload.get("level", "1")), 1) or 1
        level = max(1, min(3, level))
        with connect() as conn:
            row = conn.execute(
                """
                SELECT q.*, d.subject, d.document_kind
                FROM questions q
                JOIN documents d ON d.id = q.document_id
                WHERE q.id = ?
                """,
                (q_id,),
            ).fetchone()
            if not row:
                return json_response(self, {"error": "题目不存在。"}, 404)
            hint = generate_hint_with_ai(question_payload(row), level)
            conn.execute("UPDATE questions SET ai_hint = ? WHERE id = ?", (hint, q_id))
        return json_response(self, {"level": level, "hint": hint})

    def handle_variations(self, q_id: str) -> None:
        with connect() as conn:
            row = conn.execute(
                """
                SELECT q.*, d.subject, d.document_kind
                FROM questions q
                JOIN documents d ON d.id = q.document_id
                WHERE q.id = ?
                """,
                (q_id,),
            ).fetchone()
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
                from PIL import Image

                with Image.open(image_path) as image:
                    width, height = image.size
                    left = max(0, min(width - 1, int(float(crop.get("x", 0)) * width)))
                    top = max(0, min(height - 1, int(float(crop.get("y", 0)) * height)))
                    right = max(left + 1, min(width, int(float(crop.get("w", 1)) * width) + left))
                    bottom = max(top + 1, min(height, int(float(crop.get("h", 1)) * height) + top))
                    cropped = image.crop((left, top, right, bottom))
                    cropped.save(image_path)
            except ImportError:
                return json_response(self, {"error": "裁剪功能需要安装 Pillow：pip install -r requirements.txt"}, 500)
            except Exception as exc:
                return json_response(self, {"error": f"裁剪失败：{exc}"}, 400)
            updated = conn.execute(
                """
                SELECT q.*, d.filename, d.title document_title, d.subject, d.document_kind
                FROM questions q
                JOIN documents d ON d.id = q.document_id
                WHERE q.id = ?
                """,
                (q_id,),
            ).fetchone()
        return json_response(self, row_to_dict(updated))

    def handle_chapter_stats(self, doc_id: str) -> None:
        with connect() as conn:
            doc = conn.execute("SELECT id, title, filename FROM documents WHERE id = ?", (doc_id,)).fetchone()
            if not doc:
                return json_response(self, {"error": "做题本不存在。"}, 404)
            rows = conn.execute(
                """
                SELECT chapter,
                       MIN(page_number) first_page,
                       COUNT(*) total,
                       SUM(CASE WHEN status = '做对' THEN 1 ELSE 0 END) correct,
                       SUM(CASE WHEN status = '做错' THEN 1 ELSE 0 END) wrong,
                       SUM(CASE WHEN status IN ('半会', '需复习') THEN 1 ELSE 0 END) review,
                       SUM(CASE WHEN status = '未做' THEN 1 ELSE 0 END) todo
                FROM questions
                WHERE document_id = ?
                GROUP BY chapter
                ORDER BY first_page ASC
                """,
                (doc_id,),
            ).fetchall()
            meta_stats = get_meta_tag_stats(conn, doc_id)
        stats = []
        for row in rows:
            done = (row["correct"] or 0) + (row["wrong"] or 0) + (row["review"] or 0)
            correct_rate = round(((row["correct"] or 0) / done) * 100, 1) if done else 0
            item = dict(row)
            item["correct_rate"] = correct_rate
            stats.append(item)
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
            row = conn.execute("SELECT id FROM teacher_memory WHERE id = ?", (memory_id,)).fetchone()
            if not row:
                return json_response(self, {"error": "记忆不存在"}, 404)
            conn.execute("DELETE FROM teacher_memory WHERE id = ?", (memory_id,))
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
            row = conn.execute("SELECT id FROM mentor_experience WHERE id = ?", (exp_id,)).fetchone()
            if not row:
                return json_response(self, {"error": "经验不存在"}, 404)
            conn.execute("DELETE FROM mentor_experience WHERE id = ?", (exp_id,))
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
        intent = sakura_ai.infer_teacher_intent(message)
        strategy = sakura_ai.choose_teacher_strategy(intent, context)
        turn_instruction = sakura_ai.build_teacher_turn_instruction(intent, strategy)
        try:
            answer = call_llm_messages(
                [
                    {"role": "system", "content": sakura_ai.AI_TEACHER_PROTOCOL},
                    {"role": "system", "content": turn_instruction},
                    {"role": "system", "content": "本地上下文：\n" + json.dumps(context, ensure_ascii=False)},
                    {"role": "user", "content": message},
                ],
                temperature=0.35,
            )
        except Exception as exc:
            traceback.print_exc()
            return json_response(self, {"error": f"AI 调用失败：{exc}", "has_key": True}, 500)
        memory_candidate = sakura_ai.build_memory_candidate(message, answer, intent, strategy, context)
        with connect() as conn:
            conn.execute(
                """
                INSERT INTO ai_teacher_turns (id, user_message, intent, strategy, context_json, answer, memory_candidate, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    uuid.uuid4().hex,
                    message[:2000],
                    intent,
                    strategy.get("key", ""),
                    json.dumps({
                        "profile": context.get("profile", {}),
                        "top_gaps": context.get("top_gaps", [])[:5],
                        "review_backlog": context.get("review_backlog", {}),
                        "today_actions": context.get("today_actions", [])[:5],
                    }, ensure_ascii=False),
                    answer[:8000],
                    memory_candidate,
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )
        return json_response(self, {
            "answer": answer,
            "has_key": True,
            "model": LLM_MODEL,
            "base_url": LLM_BASE_URL,
            "teacher_intent": intent,
            "teacher_strategy": strategy,
            "memory_candidate": memory_candidate,
        })

    def handle_coach_get(self) -> None:
        """纯读记忆：返回设置 + 最新档案摘要 + 缓存计划 + 是否需要刷新。零 token。"""
        with connect() as conn:
            state = get_coach_state(conn)
            latest = load_latest_profile(conn)
            needs_refresh = self._profile_needs_refresh(conn, state)
            try:
                cached_plan = json.loads(state.get("plan_json") or "{}")
            except (TypeError, json.JSONDecodeError):
                cached_plan = {}
            insight_count = conn.execute("SELECT COUNT(*) c FROM insights").fetchone()["c"]
        profile_summary = None
        if latest:
            p = latest["profile"]
            profile_summary = {
                "version": latest["version"],
                "evidence_count": p.get("evidence_count", 0),
                "knowledge_count": p.get("knowledge_count", 0),
                "avg_mastery": p.get("avg_mastery", 0),
                "velocity": p.get("velocity", ""),
                "headline": p.get("headline", ""),
                "created_at": latest["created_at"],
            }
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
            row = conn.execute("SELECT id FROM daily_rules WHERE id = ?", (rule_id,)).fetchone()
            if not row:
                return json_response(self, {"error": "规则不存在"}, 404)
            conn.execute("DELETE FROM daily_rules WHERE id = ?", (rule_id,))
        return json_response(self, {"ok": True})

    def handle_backup_export(self, query: dict) -> None:
        mode = (query.get("mode") or ["full"])[0]
        if mode not in {"full", "light", "range"}:
            return json_response(self, {"error": "导出模式必须是 full、light 或 range"}, 400)
        start_date = (query.get("start_date") or [""])[0].strip()
        end_date = (query.get("end_date") or [""])[0].strip()
        include_assets = (query.get("include_assets") or ["1" if mode == "full" else "0"])[0] == "1"
        if mode == "light":
            include_assets = False
            start_date = ""
            end_date = ""
        if mode == "range" and (not start_date or not end_date):
            return json_response(self, {"error": "范围导出必须填写开始日期和结束日期"}, 400)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix = mode if mode != "range" else f"range_{start_date}_to_{end_date}"
        filename = f"sakura_backup_{suffix}_{stamp}.zip"
        with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp:
            tmp_path = Path(tmp.name)
        try:
            try:
                sakura_backup.build_backup_zip_file(
                    tmp_path,
                    DB_PATH,
                    {"uploads": UPLOAD_DIR, "pages": PAGE_DIR},
                    include_assets=include_assets,
                    start_date=start_date,
                    end_date=end_date,
                )
            except ValueError as exc:
                return json_response(self, {"error": str(exc)}, 400)
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
            rows = conn.execute(
                "SELECT id, period, period_start, period_end, summary_json, reflection_text, created_at FROM reflections ORDER BY created_at DESC LIMIT 30"
            ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            try:
                item["summary"] = json.loads(item.pop("summary_json"))
            except (json.JSONDecodeError, TypeError):
                item["summary"] = {}
            item["delete_url"] = f"/api/reflections/{item['id']}"
            items.append(item)
        return json_response(self, {"title": "历史知识归档", "reflections": items})

    def handle_reflection_download(self, ref_id: str) -> None:
        with connect() as conn:
            row = conn.execute(
                "SELECT id, period, period_start, period_end, reflection_text, created_at FROM reflections WHERE id = ?",
                (ref_id,),
            ).fetchone()
        if not row:
            return json_response(self, {"error": "反思记录不存在"}, 404)
        lines_out = [
            "# 历史知识归档",
            "",
            f"周期：{row['period']}（{row['period_start']} ~ {row['period_end']}）",
            f"生成时间：{row['created_at']}",
            "",
            "---",
            "",
            row['reflection_text'],
        ]
        text = "\n".join(lines_out)
        filename = f"reflection_{row['period_start']}_{row['period_end']}.txt"
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
