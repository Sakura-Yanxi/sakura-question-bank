from __future__ import annotations

import sqlite3
from pathlib import Path


def ensure_dirs(paths) -> None:
    for path in paths:
        Path(path).mkdir(parents=True, exist_ok=True)


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(
    *,
    db_path: Path,
    dirs,
    default_subject: str,
    default_document_kind: str,
    default_chapter: str,
) -> None:
    ensure_dirs(dirs)
    conn = connect(db_path)
    try:
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
        migrate_db(
            conn,
            default_subject=default_subject,
            default_document_kind=default_document_kind,
            default_chapter=default_chapter,
        )
        conn.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_questions_category ON questions(category);
            CREATE INDEX IF NOT EXISTS idx_questions_chapter ON questions(chapter);
            CREATE INDEX IF NOT EXISTS idx_questions_status ON questions(status);
            CREATE INDEX IF NOT EXISTS idx_questions_document ON questions(document_id);
            CREATE INDEX IF NOT EXISTS idx_questions_next_review ON questions(next_review_at);

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
        conn.commit()
    finally:
        conn.close()


def migrate_db(
    conn: sqlite3.Connection,
    *,
    default_subject: str,
    default_document_kind: str,
    default_chapter: str,
) -> None:
    document_columns = {row["name"] for row in conn.execute("PRAGMA table_info(documents)").fetchall()}
    if "title" not in document_columns:
        conn.execute("ALTER TABLE documents ADD COLUMN title TEXT NOT NULL DEFAULT ''")
    if "subject" not in document_columns:
        conn.execute("ALTER TABLE documents ADD COLUMN subject TEXT NOT NULL DEFAULT '未分类'")
    if "document_kind" not in document_columns:
        conn.execute("ALTER TABLE documents ADD COLUMN document_kind TEXT NOT NULL DEFAULT '做题本'")
    conn.execute("UPDATE documents SET title = filename WHERE title = ''")
    conn.execute("UPDATE documents SET subject = ? WHERE subject = '' OR subject = '其他'", (default_subject,))
    conn.execute(
        "UPDATE documents SET document_kind = ? WHERE document_kind = '' OR document_kind NOT IN ('做题本', '模拟卷')",
        (default_document_kind,),
    )

    question_columns = {row["name"] for row in conn.execute("PRAGMA table_info(questions)").fetchall()}
    if "question_no" not in question_columns:
        conn.execute("ALTER TABLE questions ADD COLUMN question_no TEXT NOT NULL DEFAULT ''")
    if "seq_no" not in question_columns:
        conn.execute("ALTER TABLE questions ADD COLUMN seq_no INTEGER NOT NULL DEFAULT 0")
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
    conn.execute("UPDATE questions SET chapter = ? WHERE chapter = ''", (default_chapter,))
    conn.execute("UPDATE questions SET meta_tags = '[]' WHERE meta_tags = ''")
    coach_exists = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='coach_state'").fetchone()
    coach_columns = {row["name"] for row in conn.execute("PRAGMA table_info(coach_state)").fetchall()} if coach_exists else set()
    if coach_exists and "weather_city" not in coach_columns:
        conn.execute("ALTER TABLE coach_state ADD COLUMN weather_city TEXT NOT NULL DEFAULT ''")
