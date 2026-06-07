from __future__ import annotations

import json
import gc
import sqlite3
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import sakura_backup
import sakura_classify
import sakura_documents
import sakura_pdf
import sakura_questions
import sakura_teacher_memory

import app


def test_pdf_helpers() -> None:
    assert sakura_pdf.safe_pdf_filename("abc.pdf") == "abc.pdf"
    assert sakura_pdf.safe_pdf_filename("a b/name.pdf") == "a_b_name.pdf"
    assert sakura_pdf.safe_pdf_filename("") == "questions.pdf"
    assert sakura_pdf.page_range(10, None, None) == (1, 10)
    assert sakura_pdf.page_range(10, 3, 7) == (3, 7)
    assert sakura_pdf.page_range(10, -5, 99) == (1, 10)
    try:
        sakura_pdf.page_range(10, 8, 3)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid PDF page range accepted")

    doc = fitz.open()
    page = doc.new_page(width=600, height=800)
    clip = sakura_pdf.continuation_clip_for_starts(page, [{"value": 5, "y": 200}], 4)
    assert clip is not None
    assert round(clip.x0) == 18
    assert round(clip.y0) == 16
    assert round(clip.x1) == 582
    assert round(clip.y1) == 196
    assert sakura_pdf.continuation_clip_for_starts(page, [{"value": 6, "y": 200}], 4) is None
    assert sakura_pdf.continuation_clip_for_starts(page, [{"value": 5, "y": 80}], 4) is None
    doc.close()

    state = sakura_pdf.PreviousQuestionState()
    state.update("q1", Path("data/pages/q1.png"), {"question_value": "12"})
    assert state.question_id == "q1"
    assert state.image_path == Path("data/pages/q1.png")
    assert state.value == 12
    state.update("q2", Path("data/pages/q2.png"), {})
    assert state.question_id == "q2"
    assert state.value is None


def test_chapter_carry_state() -> None:
    state = sakura_classify.ChapterCarryState("unknown")
    assert state.resolve("unknown") == "unknown"
    assert state.resolve("Ch1") == "Ch1"
    assert state.resolve("unknown") == "Ch1"
    assert state.resolve("Ch2") == "Ch2"
    assert state.resolve("unknown") == "Ch2"


def make_import_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE documents (
            id TEXT PRIMARY KEY,
            title TEXT,
            subject TEXT,
            document_kind TEXT,
            filename TEXT,
            stored_path TEXT,
            page_count INTEGER,
            created_at TEXT
        );
        CREATE TABLE questions (
            id TEXT PRIMARY KEY,
            document_id TEXT,
            page_number INTEGER,
            seq_no INTEGER,
            question_no TEXT,
            image_path TEXT,
            ocr_text TEXT,
            category TEXT,
            subcategory TEXT,
            chapter TEXT,
            difficulty TEXT,
            status TEXT,
            meta_tags TEXT,
            review_count INTEGER DEFAULT 0,
            last_reviewed_at TEXT,
            next_review_at TEXT,
            retention_stage INTEGER,
            created_at TEXT
        );
        """
    )
    return conn


def test_import_insert_and_ocr_helpers() -> None:
    conn = make_import_conn()
    sakura_documents.insert_document(
        conn,
        doc_id="d1",
        title="Title",
        subject="math",
        document_kind="book",
        filename="a.pdf",
        stored_path=Path("data/uploads/a.pdf"),
        page_count=12,
        created_at="now",
    )
    doc = conn.execute("SELECT * FROM documents WHERE id = ?", ("d1",)).fetchone()
    assert doc["title"] == "Title"
    assert doc["page_count"] == 12

    summary = sakura_questions.insert_imported_question(
        conn,
        q_id="q1",
        doc_id="d1",
        page_number=3,
        seq_no=1,
        question_no="7",
        image_path=Path("data/pages/q.png"),
        question_text="first",
        classification={"category": "limits", "subcategory": "rule", "chapter": "ch1", "difficulty": "medium"},
        created_at="now",
    )
    assert summary == {
        "id": "q1",
        "page_number": 3,
        "seq_no": 1,
        "question_no": "7",
        "category": "limits",
        "subcategory": "rule",
        "chapter": "ch1",
    }
    sakura_questions.append_question_ocr_text(conn, "q1", "second")
    q = conn.execute("SELECT ocr_text FROM questions WHERE id = ?", ("q1",)).fetchone()
    assert q["ocr_text"] == "first\nsecond"


def test_question_update_helper() -> None:
    conn = make_import_conn()
    sakura_documents.insert_document(
        conn,
        doc_id="d1",
        title="Title",
        subject="math",
        document_kind="book",
        filename="a.pdf",
        stored_path=Path("data/uploads/a.pdf"),
        page_count=12,
        created_at="now",
    )
    sakura_questions.insert_imported_question(
        conn,
        q_id="q1",
        doc_id="d1",
        page_number=1,
        seq_no=1,
        question_no="",
        image_path=Path("data/pages/q.png"),
        question_text="text",
        classification={"category": "old", "subcategory": "rule", "chapter": "ch1", "difficulty": "medium"},
        created_at="now",
    )

    def normalize_tags(value):
        if isinstance(value, list):
            return [str(item) for item in value]
        try:
            parsed = json.loads(value or "[]")
        except (TypeError, json.JSONDecodeError):
            return []
        return [str(item) for item in parsed]

    def schedule(_current, _status):
        return {"next_review_at": "2026-01-02", "retention_stage": 1}

    try:
        sakura_questions.update_question(
            conn,
            "q1",
            {"status": "wrong"},
            normalize_meta_tags=normalize_tags,
            wrongish_statuses={"wrong"},
            schedule_for_status=schedule,
        )
    except sakura_questions.QuestionUpdateError as exc:
        assert exc.status == 400
    else:
        raise AssertionError("wrong status without meta tags accepted")

    row = sakura_questions.update_question(
        conn,
        "q1",
        {"status": "wrong", "meta_tags": ["calc"], "category": "new"},
        normalize_meta_tags=normalize_tags,
        wrongish_statuses={"wrong"},
        schedule_for_status=schedule,
    )
    assert row["category"] == "new"
    assert json.loads(row["meta_tags"]) == ["calc"]
    assert row["review_count"] == 1
    assert row["next_review_at"] == "2026-01-02"


def test_backup_options() -> None:
    now = datetime(2026, 1, 2, 3, 4, 5)
    full = sakura_backup.export_options_from_query({}, now)
    assert full["mode"] == "full"
    assert full["include_assets"] is True
    assert full["filename"] == "sakura_backup_full_20260102_030405.zip"

    light = sakura_backup.export_options_from_query(
        {"mode": ["light"], "include_assets": ["1"], "start_date": ["2026-01-01"]},
        now,
    )
    assert light["include_assets"] is False
    assert light["start_date"] == ""

    ranged = sakura_backup.export_options_from_query(
        {"mode": ["range"], "start_date": ["2026-01-01"], "end_date": ["2026-01-31"], "include_assets": ["1"]},
        now,
    )
    assert ranged["include_assets"] is True
    assert ranged["filename"] == "sakura_backup_range_2026-01-01_to_2026-01-31_20260102_030405.zip"


def test_teacher_turn_persistence() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE ai_teacher_turns (
            id TEXT PRIMARY KEY,
            user_message TEXT,
            intent TEXT,
            strategy TEXT,
            context_json TEXT,
            answer TEXT,
            memory_candidate TEXT,
            created_at TEXT
        )
        """
    )
    turn_id = sakura_teacher_memory.save_teacher_turn(
        conn,
        message="m" * 2100,
        intent="diagnose",
        strategy={"key": "socratic"},
        context={"profile": {"a": 1}, "top_gaps": list(range(10)), "review_backlog": {"n": 2}, "today_actions": list(range(8))},
        answer="a" * 9000,
        memory_candidate="remember",
    )
    row = conn.execute("SELECT * FROM ai_teacher_turns WHERE id = ?", (turn_id,)).fetchone()
    assert len(row["user_message"]) == 2000
    assert len(row["answer"]) == 8000
    assert row["strategy"] == "socratic"
    context = json.loads(row["context_json"])
    assert len(context["top_gaps"]) == 5
    assert len(context["today_actions"]) == 5


def test_real_import_pdf_smoke() -> None:
    original_paths = {
        "DATA_DIR": app.DATA_DIR,
        "UPLOAD_DIR": app.UPLOAD_DIR,
        "PAGE_DIR": app.PAGE_DIR,
        "STATIC_DIR": app.STATIC_DIR,
        "DB_PATH": app.DB_PATH,
    }
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        app.DATA_DIR = root / "data"
        app.UPLOAD_DIR = app.DATA_DIR / "uploads"
        app.PAGE_DIR = app.DATA_DIR / "pages"
        app.STATIC_DIR = root / "static"
        app.DB_PATH = app.DATA_DIR / "gaoshu_demo.sqlite3"

        pdf = fitz.open()
        page = pdf.new_page(width=595, height=842)
        page.insert_text((72, 72), "Chapter 1 Limits", fontsize=14)
        page.insert_text((72, 130), "1. Find the limit of sin(x)/x as x -> 0.", fontsize=12)
        pdf_bytes = pdf.write()
        pdf.close()

        try:
            app.init_db()
            result = app.import_pdf(
                "demo import.pdf",
                pdf_bytes,
                title="Demo Import",
                subject="Math",
                document_kind=app.DEFAULT_DOCUMENT_KIND,
            )
            assert result["title"] == "Demo Import"
            assert result["subject"] == "Math"
            assert result["document_kind"] == app.DEFAULT_DOCUMENT_KIND
            assert result["page_count"] == 1
            assert len(result["questions"]) == 1

            conn = app.connect()
            try:
                docs = conn.execute("SELECT * FROM documents").fetchall()
                questions = conn.execute("SELECT * FROM questions").fetchall()
            finally:
                conn.close()
            assert len(docs) == 1
            assert docs[0]["title"] == "Demo Import"
            assert docs[0]["page_count"] == 1
            assert Path(docs[0]["stored_path"]).exists()
            assert len(questions) == 1
            assert "sin(x)/x" in questions[0]["ocr_text"]
            assert Path(questions[0]["image_path"]).exists()
        finally:
            for key, value in original_paths.items():
                setattr(app, key, value)
            gc.collect()


def main() -> None:
    test_pdf_helpers()
    test_chapter_carry_state()
    test_import_insert_and_ocr_helpers()
    test_question_update_helper()
    test_backup_options()
    test_teacher_turn_persistence()
    test_real_import_pdf_smoke()
    print("smoke_refactor_ok")


if __name__ == "__main__":
    main()
