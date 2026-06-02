from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import traceback
import uuid
import warnings
from datetime import date, datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import urllib.request

warnings.filterwarnings("ignore", message="'cgi' is deprecated.*", category=DeprecationWarning)
import cgi

import fitz

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
PAGE_DIR = DATA_DIR / "pages"
STATIC_DIR = ROOT / "static"
DB_PATH = DATA_DIR / "gaoshu_demo.sqlite3"

PORT = int(os.getenv("PORT", "8000"))

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
PUSHPLUS_URL = "https://www.pushplus.plus/send"
# 推送正文里的“打开做题集”链接（部署到公网后改成你的域名/IP）
APP_PUBLIC_URL = os.getenv("APP_PUBLIC_URL", "http://127.0.0.1:8000")
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


def parse_ai_json(raw: str) -> dict:
    match = re.search(r"\{.*\}", raw, flags=re.S)
    if not match:
        raise ValueError("AI 返回内容不是 JSON")
    return json.loads(match.group(0))


def llm_enabled() -> bool:
    """是否已配置 AI 接口密钥。"""
    return bool(LLM_API_KEY)


def call_llm(prompt: str, temperature: float = 0.3) -> str:
    """统一的 OpenAI 兼容调用入口（默认小米 MiMo）。失败时抛异常，由调用方决定 fallback。"""
    from openai import OpenAI

    client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)
    result = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
    )
    return result.choices[0].message.content or ""


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


def extract_json_block(raw: str) -> dict:
    """优先取 ```json ... ``` 代码块，退化到 parse_ai_json。"""
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, flags=re.S)
    if fence:
        return json.loads(fence.group(1))
    return parse_ai_json(raw)


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
            insight = normalize_insight(extract_json_block(content), question)
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


def build_reflection_payload(conn: sqlite3.Connection, period: str) -> dict:
    today = date.today()
    if period == "month":
        start_date = today.replace(day=1)
    else:
        start_date = today - timedelta(days=today.weekday())
    end_date = today
    start_iso = start_date.isoformat()
    end_iso = end_date.isoformat()
    days = (end_date - start_date).days + 1
    rows = conn.execute(
        """
        SELECT q.*, d.title document_title, d.subject, d.document_kind
        FROM questions q
        JOIN documents d ON d.id = q.document_id
        WHERE q.last_reviewed_at IS NOT NULL
          AND q.status <> '未做'
          AND date(q.last_reviewed_at) >= date(?)
          AND date(q.last_reviewed_at) <= date(?)
        ORDER BY q.last_reviewed_at DESC
        """,
        (start_iso, end_iso),
    ).fetchall()
    subject_stats = conn.execute(
        """
        SELECT d.subject,
               COUNT(*) total,
               SUM(CASE WHEN q.status = '做对' THEN 1 ELSE 0 END) correct,
               SUM(CASE WHEN q.status = '做错' THEN 1 ELSE 0 END) wrong,
               SUM(CASE WHEN q.status IN ('半会', '需复习') THEN 1 ELSE 0 END) review
        FROM questions q
        JOIN documents d ON d.id = q.document_id
        WHERE q.last_reviewed_at IS NOT NULL
          AND q.status <> '未做'
          AND date(q.last_reviewed_at) >= date(?)
          AND date(q.last_reviewed_at) <= date(?)
        GROUP BY d.subject
        ORDER BY total DESC, wrong DESC, review DESC
        """,
        (start_iso, end_iso),
    ).fetchall()
    chapter_stats = conn.execute(
        """
        SELECT d.subject, q.chapter, q.category,
               COUNT(*) total,
               SUM(CASE WHEN q.status = '做对' THEN 1 ELSE 0 END) correct,
               SUM(CASE WHEN q.status = '做错' THEN 1 ELSE 0 END) wrong,
               SUM(CASE WHEN q.status IN ('半会', '需复习') THEN 1 ELSE 0 END) review
        FROM questions q
        JOIN documents d ON d.id = q.document_id
        WHERE q.last_reviewed_at IS NOT NULL
          AND q.status <> '未做'
          AND date(q.last_reviewed_at) >= date(?)
          AND date(q.last_reviewed_at) <= date(?)
        GROUP BY d.subject, q.chapter, q.category
        ORDER BY wrong DESC, review DESC, total DESC
        LIMIT 18
        """,
        (start_iso, end_iso),
    ).fetchall()
    questions = [dict(row) for row in rows]
    wrong_questions = [q for q in questions if q["status"] in {"做错", "半会", "需复习"}]
    return {
        "period": period,
        "days": days,
        "total": len(questions),
        "correct": sum(1 for q in questions if q["status"] == "做对"),
        "wrong": sum(1 for q in questions if q["status"] == "做错"),
        "review": sum(1 for q in questions if q["status"] in {"半会", "需复习"}),
        "subjects": [dict(row) for row in subject_stats],
        "chapters": [dict(row) for row in chapter_stats],
        "wrong_questions": wrong_questions[:15],
    }


def save_reflection(period: str, summary: dict, reflection: str) -> str:
    import json as _json
    today = date.today()
    if period == "week":
        start = today - timedelta(days=today.weekday())
    else:
        start = today.replace(day=1)
    end = today
    ref_id = uuid.uuid4().hex
    with connect() as conn:
        conn.execute(
            "INSERT INTO reflections (id, period, period_start, period_end, summary_json, reflection_text, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (ref_id, period, start.isoformat(), end.isoformat(), _json.dumps(summary, ensure_ascii=False, default=str), reflection, datetime.now().isoformat()),
        )
    return ref_id


def generate_reflection_with_ai(payload: dict) -> str:
    if payload.get("force_local") or not llm_enabled():
        weak = payload["chapters"][:5]
        subject_lines = "\n".join(
            f"- {item['subject']}：做题 {item['total']}，做对 {item['correct'] or 0}，做错 {item['wrong'] or 0}，需复习 {item['review'] or 0}"
            for item in payload.get("subjects", [])
        ) or "- 本周期还没有已标记的做题记录。"
        weak_lines = "\n".join(
            f"- {item['subject']} / {item['chapter']}：错题 {item['wrong'] or 0}，需复习 {item['review'] or 0}"
            for item in weak
        ) or "- 暂无明显薄弱章节。"
        return (
            f"{'本月' if payload['period'] == 'month' else '本周'}总结与反思\n"
            f"共完成/复盘 {payload['total']} 道题，做对 {payload['correct']}，做错 {payload['wrong']}，需复习 {payload['review']}。\n\n"
            "科目统计：\n"
            f"{subject_lines}\n\n"
            "当前薄弱点：\n"
            f"{weak_lines}\n\n"
            "建议：优先复盘本周期错题集中的高频章节，再补 2-3 道同章节基础题和 1 道变式题。"
        )
    try:
        compact_wrong = [
            {
                "subject": q.get("subject"),
                "chapter": q.get("chapter"),
                "category": q.get("category"),
                "status": q.get("status"),
                "mistake_reason": q.get("mistake_reason"),
                "user_note": q.get("user_note"),
                "text": (q.get("ocr_text") or "")[:300],
            }
            for q in payload["wrong_questions"]
        ]
        prompt = f"""
你是学习复盘教练。请根据下面的做题记录生成中文总结与反思。
周期：{'本月' if payload['period'] == 'month' else '本周'}
统计口径：只统计本周期内被标记为做对、做错、半会或需复习的题目，不把单纯导入但未做的题目计入。
总统计：完成/复盘 {payload['total']}，做对 {payload['correct']}，做错 {payload['wrong']}，需复习 {payload['review']}
科目统计：
{json.dumps(payload.get('subjects', []), ensure_ascii=False)}
章节统计：
{json.dumps(payload['chapters'], ensure_ascii=False)}
代表性错题：
{json.dumps(compact_wrong, ensure_ascii=False)}

请输出：
1. 本周期学习内容概览，必须按科目分别说明
2. 重难点与薄弱章节
3. 错题暴露出的具体不足
4. 下个周期规划，包含优先级和练习建议
5. 需要警惕的做题习惯问题
"""
        return call_llm(prompt, temperature=0.35) or generate_reflection_with_ai({**payload, "force_local": True})
    except Exception:
        print("LLM reflection failed; falling back", file=sys.stderr)
        traceback.print_exc()
        return generate_reflection_with_ai({**payload, "force_local": True})


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
        extra = extract_json_block(call_llm(prompt, temperature=0.3))
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
    allowed = {"daily_minutes", "exam_date", "cadence", "focus_subject", "last_profile_at", "last_plan_at", "plan_json"}
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


def build_study_phases(days_left: int, daily_minutes: int) -> list[dict]:
    """按剩余天数切分阶段；<14 天压缩为纯冲刺。"""
    per_day_questions = max(1, round(daily_minutes / STUDY_MINUTES_PER_QUESTION))
    today = date.today()

    def span(start_offset: int, length: int) -> str:
        s = today + timedelta(days=start_offset)
        e = today + timedelta(days=max(start_offset, start_offset + length - 1))
        return f"{s.month}/{s.day} – {e.month}/{e.day}"

    if days_left <= 0:
        return [{
            "name": "考试在即", "span": "今天", "days": 0,
            "focus": "回顾错题集与公式卡，保持手感，别碰新题。",
            "daily_questions": per_day_questions,
        }]
    if days_left < 14:
        return [{
            "name": "冲刺模考", "span": span(0, days_left), "days": days_left,
            "focus": "整套模拟卷限时训练 + 错题三轮回炉，主攻最薄弱的 2-3 个知识点。",
            "daily_questions": per_day_questions,
        }]
    base_days = round(days_left * 0.5)
    boost_days = round(days_left * 0.3)
    sprint_days = days_left - base_days - boost_days
    return [
        {"name": "基础攻坚", "span": span(0, base_days), "days": base_days,
         "focus": "补前置缺口 + 主攻薄弱知识点，先把地基打牢。",
         "daily_questions": per_day_questions},
        {"name": "强化提升", "span": span(base_days, boost_days), "days": boost_days,
         "focus": "不稳知识点做专项突破，错题回炉，提升综合题正确率。",
         "daily_questions": per_day_questions},
        {"name": "冲刺模考", "span": span(base_days + boost_days, sprint_days), "days": sprint_days,
         "focus": "整套模拟卷限时模考，按错因复盘，稳住已掌握内容。",
         "daily_questions": per_day_questions},
    ]


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


def compute_predictions(profile: dict, gaps: list[dict], days_left: int, daily_minutes: int) -> dict:
    avg = profile.get("avg_mastery", 0.0)
    capacity_total = max(1, round(days_left * daily_minutes / STUDY_MINUTES_PER_QUESTION))
    weak_total = sum(g.get("total", g.get("evidence", 0)) for g in gaps) or 1
    # 粗估：剩余练习容量能覆盖多少薄弱题量
    coverage = min(1.0, capacity_total / (weak_total * 2.5))
    # 掌握度外推：按容量给薄弱点一个可达增益（带上限，避免过度乐观）
    projected = round(min(0.92, avg + coverage * (1 - avg) * 0.6), 3)
    readiness = round(projected * (0.7 + 0.3 * coverage), 3)
    if days_left <= 0:
        outlook = "考试当天：以稳为主，回顾错题与公式卡即可。"
    elif coverage >= 0.8:
        outlook = "时间相对充裕，按计划推进可把薄弱点系统补齐。"
    elif coverage >= 0.5:
        outlook = "时间偏紧，建议聚焦最高优先级的 3-4 个薄弱点，别铺太开。"
    else:
        outlook = "时间紧张，只攻最高频考点与前置地基，放弃边角难题保性价比。"
    return {
        "days_left": days_left,
        "current_avg_mastery": round(avg, 3),
        "projected_avg_mastery": projected,
        "exam_readiness": readiness,
        "coverage": round(coverage, 3),
        "capacity_total": capacity_total,
        "outlook": outlook,
        "note": "这是基于剩余时间和薄弱点题量的容量估算，不代表成绩预测。",
    }


def coach_narrative_local(profile: dict, gaps: list[dict], backlog: dict, phases: list[dict], predictions: dict) -> str:
    lines = ["【本地复习计划摘要】", ""]
    headline = profile.get("headline")
    if headline:
        lines.append(headline)
    lines.append(profile.get("velocity", ""))
    lines.append("")
    if gaps:
        lines.append("当前最该补的薄弱点（按性价比排序）：")
        for i, g in enumerate(gaps[:4], 1):
            lines.append(f"  {i}. {g['name']}：{g['reason']}")
            lines.append(f"     → {g['prescription']}")
    if backlog["overdue"] or backlog["due_today"]:
        lines.append("")
        lines.append(f"复习账：{backlog['overdue']} 道逾期 + {backlog['due_today']} 道今日到期，先还清再上新题。")
    lines.append("")
    lines.append(f"时间预算：距考试 {predictions['days_left']} 天，按 {phases[0]['daily_questions']} 题/天推进。")
    lines.append(f"容量估算：当前平均掌握度 {int(predictions['current_avg_mastery']*100)}%，剩余时间约可安排 {predictions['capacity_total']} 道练习。")
    lines.append(f"薄弱点覆盖率估算：{int(predictions['coverage']*100)}%。")
    lines.append(predictions["outlook"])
    return "\n".join(line for line in lines if line is not None)


def coach_narrative_ai(profile: dict, gaps: list[dict], backlog: dict, phases: list[dict], predictions: dict) -> str:
    local = coach_narrative_local(profile, gaps, backlog, phases, predictions)
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
    phases = build_study_phases(days_left, daily_minutes)
    in_sprint = days_left < 14
    today_actions = build_today_actions(conn, gaps, backlog, daily_minutes, in_sprint, settings.get("focus_subject", ""))
    predictions = compute_predictions(profile, gaps, days_left, daily_minutes)
    narrative = coach_narrative_ai(profile, gaps, backlog, phases, predictions) if want_ai else coach_narrative_local(profile, gaps, backlog, phases, predictions)

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
    lines.append(f"👉 [打开做题集开始复习]({APP_PUBLIC_URL})")
    return {"title": title, "content": "\n".join(lines), "due_total": due_total, "days_left": days_left}


def send_pushplus(title: str, content: str, template: str = "markdown") -> dict:
    if not PUSHPLUS_TOKEN:
        return {"ok": False, "error": "未配置 PUSHPLUS_TOKEN，无法推送到微信。"}
    payload = json.dumps(
        {"token": PUSHPLUS_TOKEN, "title": title, "content": content, "template": template}
    ).encode("utf-8")
    req = urllib.request.Request(PUSHPLUS_URL, data=payload, headers={"Content-Type": "application/json"})
    try:
        resp = json.loads(urllib.request.urlopen(req, timeout=15).read().decode("utf-8"))
        return {"ok": resp.get("code") == 200, "resp": resp}
    except Exception as exc:
        traceback.print_exc()
        return {"ok": False, "error": str(exc)}


def render_page_image(page: fitz.Page, image_path: Path) -> None:
    page_rect = page.rect
    target_width = 1800
    zoom = max(1.4, min(3.0, target_width / max(page_rect.width, 1)))
    matrix = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=matrix, colorspace=fitz.csRGB, alpha=False, annots=True)
    pix.save(image_path)


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
            for index in range(page_start, page_end + 1):
                page = pdf[index - 1]
                q_id = uuid.uuid4().hex
                text = page.get_text("text", sort=True).strip()
                if document_kind == MOCK_PAPER_KIND:
                    chapter_hint = MOCK_PAPER_CHAPTER
                else:
                    extracted_chapter = extract_chapter_from_page(page, text)
                    if extracted_chapter != DEFAULT_CHAPTER:
                        last_chapter = extracted_chapter
                    chapter_hint = last_chapter if last_chapter != DEFAULT_CHAPTER else extracted_chapter
                image_path = PAGE_DIR / f"{doc_id}_page_{index:03d}.png"
                render_page_image(page, image_path)
                classification = classify_question_locally(text, subject, chapter_hint, document_kind)
                conn.execute(
                    """
                    INSERT INTO questions (
                        id, document_id, page_number, seq_no, image_path, ocr_text, category,
                        subcategory, chapter, difficulty, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        q_id,
                        doc_id,
                        index,
                        index - page_start + 1,
                        str(image_path),
                        text,
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
                        "category": classification["category"],
                        "subcategory": classification["subcategory"],
                        "chapter": classification["chapter"],
                    }
                )
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


class DemoHandler(BaseHTTPRequestHandler):
    server_version = "GaoshuDemo/0.1"

    def log_message(self, format: str, *args) -> None:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {format % args}")

    def do_GET(self) -> None:
        try:
            parsed = urlparse(self.path)
            if parsed.path == "/":
                return self.serve_file(STATIC_DIR / "index.html")
            if parsed.path == "/api/health":
                return json_response(self, {"ok": True, "date": date.today().isoformat()})
            if parsed.path == "/api/documents":
                return self.handle_documents()
            if parsed.path.startswith("/api/documents/") and parsed.path.endswith("/chapter-stats"):
                doc_id = parsed.path.split("/")[-2]
                return self.handle_chapter_stats(doc_id)
            if parsed.path == "/api/questions":
                return self.handle_questions(parse_qs(parsed.query))
            if parsed.path == "/api/daily":
                return self.handle_daily()
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

    def do_POST(self) -> None:
        try:
            parsed = urlparse(self.path)
            if parsed.path == "/api/upload":
                return self.handle_upload()
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
            if parsed.path == "/api/push/daily":
                return self.handle_push_daily()
            return text_response(self, "Not found", HTTPStatus.NOT_FOUND)
        except Exception as exc:
            traceback.print_exc()
            return json_response(self, {"error": str(exc)}, 500)

    def do_DELETE(self) -> None:
        try:
            parsed = urlparse(self.path)
            if parsed.path == "/api/coach/plan":
                return self.handle_clear_coach_plan()
            if parsed.path.startswith("/api/documents/"):
                doc_id = parsed.path.split("/")[-1]
                return self.handle_delete_document(doc_id)
            if parsed.path.startswith("/api/questions/"):
                q_id = parsed.path.split("/")[-1]
                return self.handle_delete_question(q_id)
            if parsed.path.startswith("/api/reflections/"):
                ref_id = parsed.path.split("/")[-1]
                return self.handle_delete_reflection(ref_id)
            return text_response(self, "Not found", HTTPStatus.NOT_FOUND)
        except Exception as exc:
            traceback.print_exc()
            return json_response(self, {"error": str(exc)}, 500)

    def do_PATCH(self) -> None:
        try:
            parsed = urlparse(self.path)
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
            ".html": "text/html",
            ".css": "text/css",
            ".js": "application/javascript",
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
        result = import_pdf(file_item.filename, file_item.file.read(), title, subject, document_kind, start_page, end_page)
        return json_response(self, result)

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
        allowed = {"status", "mistake_reason", "meta_tags", "user_note", "category", "subcategory", "chapter", "difficulty", "question_no"}
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
            payload = build_reflection_payload(conn, period)
        return json_response(self, payload)

    def handle_reflection(self) -> None:
        payload = self.read_json()
        period = payload.get("period", "week")
        if period not in {"week", "month"}:
            period = "week"
        with connect() as conn:
            reflection_payload = build_reflection_payload(conn, period)
        if reflection_payload["total"] == 0:
            return json_response(self, {"reflection": "本周期暂无可复盘内容。先完成一些做题记录，再生成总结与反思。", "summary": reflection_payload, "id": None})
        reflection = generate_reflection_with_ai(reflection_payload)
        ref_id = save_reflection(period, reflection_payload, reflection)
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

    def handle_push_daily(self) -> None:
        with connect() as conn:
            reminder = build_daily_reminder(conn)
        result = send_pushplus(reminder["title"], reminder["content"])
        status = 200 if result["ok"] else 400
        return json_response(self, {
            "ok": result["ok"],
            "title": reminder["title"],
            "due_total": reminder["due_total"],
            "days_left": reminder["days_left"],
            "detail": result.get("resp") or result.get("error"),
            "configured": bool(PUSHPLUS_TOKEN),
        }, status)

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
        today = date.today().isoformat()
        with connect() as conn:
            rows = conn.execute(
                """
                SELECT q.*, d.filename, d.title document_title, d.subject, d.document_kind
                FROM questions q
                JOIN documents d ON d.id = q.document_id
                WHERE q.status IN ('做错', '需复习', '半会')
                   OR (
                       q.ever_wrong = 1
                       AND q.mastered_at IS NULL
                       AND q.next_review_at IS NOT NULL
                       AND date(q.next_review_at) <= date(?)
                   )
                ORDER BY
                    d.subject ASC,
                    COALESCE(NULLIF(d.title, ''), d.filename) ASC,
                    CASE q.status
                        WHEN '做错' THEN 0
                        WHEN '需复习' THEN 1
                        WHEN '半会' THEN 2
                        WHEN '做对' THEN 3
                        ELSE 4
                    END,
                    q.review_stage ASC,
                    COALESCE(q.next_review_at, q.last_reviewed_at, q.created_at) ASC
                """
                ,
                (today,),
            ).fetchall()
            dependency_map = weak_chapter_dependencies(conn)
        groups_map: dict[str, dict] = {}
        used_ids: set[str] = set()
        for row in rows:
            item = row_to_dict(row)
            item["daily_kind"] = "review"
            used_ids.add(item["id"])
            book_name = item.get("document_title") or item.get("filename") or "做题本"
            group_key = f"{item.get('subject') or DEFAULT_SUBJECT} / {item.get('document_kind') or DEFAULT_DOCUMENT_KIND} / {book_name}"
            if group_key not in groups_map:
                groups_map[group_key] = {"title": group_key, "questions": []}
            if len(groups_map[group_key]["questions"]) < 4:
                groups_map[group_key]["questions"].append(item)
        with connect() as conn:
            for group_key, dependencies in dependency_map.items():
                if group_key not in groups_map:
                    continue
                subject = group_key.split(" / ", 1)[0]
                if len(groups_map[group_key]["questions"]) >= 5:
                    continue
                foundations = find_foundation_questions(conn, subject, dependencies, used_ids)
                if foundations:
                    groups_map[group_key]["questions"].append(foundations[0])
                    used_ids.add(foundations[0]["id"])
        groups = [group for group in groups_map.values() if group["questions"]]
        return json_response(
            self,
            {
                "date": date.today().isoformat(),
                "groups": groups,
                "plan": [question for group in groups for question in group["questions"]],
                "message": "每日练习由当前错题、到期复习题和低正确率章节的前置基础题组成；每组最多 5 道，其中约 20% 用于补基础。",
            },
        )


def main() -> None:
    init_db()
    server = ThreadingHTTPServer(("127.0.0.1", PORT), DemoHandler)
    print(f"Gaoshu demo running at http://127.0.0.1:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
