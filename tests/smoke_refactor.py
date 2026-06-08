from __future__ import annotations

import json
import gc
import io
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
import sakura_ai
import sakura_classify
import sakura_coach
import sakura_documents
import sakura_email
import sakura_http
import sakura_import
import sakura_pdf
import sakura_questions
import sakura_routes
import sakura_teacher_memory
import sakura_textbook

import app


class FakeHttpHandler:
    def __init__(self) -> None:
        self.status = None
        self.headers = []
        self.wfile = io.BytesIO()

    def send_response(self, status: int) -> None:
        self.status = status

    def send_header(self, key: str, value: str) -> None:
        self.headers.append((key, value))

    def end_headers(self) -> None:
        pass


def test_http_file_serving() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        page = root / "index.html"
        page.write_bytes(b"<html>Sakura</html>")
        handler = FakeHttpHandler()
        sakura_http.serve_file(handler, page, root)
        assert handler.status == 200
        assert ("Content-Type", "text/html; charset=utf-8") in handler.headers
        assert handler.wfile.getvalue() == b"<html>Sakura</html>"

        missing = FakeHttpHandler()
        sakura_http.serve_file(missing, root / "missing.html", root)
        assert missing.status == 404
        assert b"Not found" in missing.wfile.getvalue()

    assert sakura_routes.route_for("/api/questions", sakura_routes.GET_ROUTES).handler == "handle_questions"
    assert sakura_routes.route_for("/api/questions", sakura_routes.GET_ROUTES).with_query is True
    assert sakura_routes.route_for("/api/notify/settings", sakura_routes.POST_ROUTES).handler == "handle_notification_settings_post"
    assert sakura_routes.route_for("/api/missing", sakura_routes.GET_ROUTES) is None
    assert sakura_routes.split_path("/api/practice/b1/questions/q2") == ["api", "practice", "b1", "questions", "q2"]
    assert sakura_routes.get_dynamic_route("/api/questions/q1").handler == "handle_question_detail"
    assert sakura_routes.get_dynamic_route("/api/textbooks/t1/pages/3").args == ("t1", 3)
    assert sakura_routes.post_dynamic_route("/api/questions/q1/hint").args == ("q1",)
    assert sakura_routes.post_dynamic_route("/api/practice/b1/questions/q2").args == ("b1", "q2")
    assert sakura_routes.delete_dynamic_route("/api/mentor-experience/e1").handler == "handle_mentor_experience_delete"
    assert sakura_routes.patch_dynamic_route("/api/documents/d1").args == ("d1",)
    missing_handlers = [name for name in sakura_routes.configured_handler_names() if not hasattr(app.DemoHandler, name)]
    assert missing_handlers == []
    assert app.demo_mode_enabled() is app.DEMO_MODE


def test_email_notification_helpers() -> None:
    settings = sakura_email.EmailSettings(
        enabled="1",
        host="smtp.example.com",
        port="465",
        use_ssl="1",
        user="sender@example.com",
        password="secret",
        to="first@example.com, second@example.com",
        from_name="Sakura",
    )
    assert sakura_email.is_configured(settings)
    view = sakura_email.settings_public_view(settings)
    assert view["has_email"] is True
    assert view["masked_email_user"] == "sexxxx@example.com"
    assert view["masked_email_to"].startswith("fixxxx@example.com")

    calls = []

    class FakeSMTP:
        def __init__(self, host, port, timeout=None, context=None):
            calls.append(("connect", host, port, timeout, bool(context)))

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def login(self, user, password):
            calls.append(("login", user, password))

        def send_message(self, message):
            calls.append(("send", message["Subject"], message["To"]))

    old_smtp_ssl = sakura_email.smtplib.SMTP_SSL
    sakura_email.smtplib.SMTP_SSL = FakeSMTP
    try:
        result = sakura_email.send_email(settings, "Test Subject", "### Hello\n\n[Open](https://example.com)")
    finally:
        sakura_email.smtplib.SMTP_SSL = old_smtp_ssl

    assert result["ok"] is True
    assert calls[0][:3] == ("connect", "smtp.example.com", 465)
    assert ("login", "sender@example.com", "secret") in calls
    assert calls[-1][0] == "send"


def test_pdf_helpers() -> None:
    assert sakura_pdf.safe_pdf_filename("abc.pdf") == "abc.pdf"
    assert sakura_pdf.safe_pdf_filename("a b/name.pdf") == "a_b_name.pdf"
    assert sakura_pdf.safe_pdf_filename("") == "questions.pdf"
    with tempfile.TemporaryDirectory() as tmp:
        pdf_path = sakura_pdf.save_uploaded_pdf(Path(tmp), "doc1", "a b/name.pdf", b"%PDF-demo")
        assert pdf_path.name == "doc1_a_b_name.pdf"
        assert pdf_path.read_bytes() == b"%PDF-demo"
    assert sakura_pdf.should_split_import_page("mock", split_questions=True, mock_paper_kind="mock") is True
    assert sakura_pdf.should_split_import_page("mock", split_questions=False, mock_paper_kind="mock") is False
    assert sakura_pdf.should_split_import_page("book", split_questions=True, mock_paper_kind="mock") is False
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
    starts, slices = sakura_pdf.import_page_slices(page, split_enabled=False)
    assert starts == []
    assert slices == [{"question_no": "", "clip": None}]
    starts, slices = sakura_pdf.import_page_slices(page, split_enabled=True)
    assert starts == []
    assert slices == [{"question_no": "", "clip": None}]
    page.insert_text((72, 120), "Page text for import", fontsize=12)
    text, starts, slices = sakura_pdf.prepare_import_page(
        page,
        document_kind="book",
        split_questions=True,
        mock_paper_kind="mock",
    )
    assert "Page text for import" in text
    assert starts == []
    assert slices == [{"question_no": "", "clip": None}]

    continuation_state = sakura_pdf.PreviousQuestionState(
        question_id="q4",
        image_path=Path("data/pages/q4.png"),
        value=4,
    )
    appended = []
    continuation_text = sakura_pdf.append_import_continuation(
        page,
        [{"value": 5, "y": 200}],
        continuation_state,
        append_image=lambda _page, clip, path: appended.append((clip, path)),
    )
    assert "Page text for import" in continuation_text
    assert len(appended) == 1
    assert appended[0][1] == Path("data/pages/q4.png")
    assert sakura_pdf.append_import_continuation(page, [], continuation_state, append_image=lambda *_args: None) == ""
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

    resolved = sakura_classify.resolve_import_chapter(
        page=None,
        text="",
        document_kind="mock",
        chapters=sakura_classify.ChapterCarryState("unknown"),
        default_chapter="unknown",
        mock_paper_kind="mock",
        mock_paper_chapter="whole paper",
        extract_chapter=lambda _page, _text, _default: "should-not-run",
    )
    assert resolved == "whole paper"

    state = sakura_classify.ChapterCarryState("unknown")
    assert sakura_classify.resolve_import_chapter(
        page=None,
        text="page 1",
        document_kind="book",
        chapters=state,
        default_chapter="unknown",
        mock_paper_kind="mock",
        mock_paper_chapter="whole paper",
        extract_chapter=lambda _page, _text, _default: "Ch1",
    ) == "Ch1"
    assert sakura_classify.resolve_import_chapter(
        page=None,
        text="page 2",
        document_kind="book",
        chapters=state,
        default_chapter="unknown",
        mock_paper_kind="mock",
        mock_paper_chapter="whole paper",
        extract_chapter=lambda _page, _text, default: default,
    ) == "Ch1"


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


def make_textbook_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE textbooks (
            id TEXT PRIMARY KEY,
            title TEXT,
            subject TEXT,
            filename TEXT,
            stored_path TEXT,
            page_count INTEGER,
            created_at TEXT
        );
        CREATE TABLE textbook_pages (
            id TEXT PRIMARY KEY,
            textbook_id TEXT,
            page_number INTEGER,
            image_path TEXT,
            page_text TEXT,
            paragraphs_json TEXT,
            created_at TEXT
        );
        CREATE TABLE textbook_chats (
            id TEXT PRIMARY KEY,
            textbook_id TEXT,
            page_number INTEGER,
            role TEXT,
            content TEXT,
            created_at TEXT
        );
        """
    )
    return conn


def test_import_insert_and_ocr_helpers() -> None:
    metadata = sakura_documents.import_metadata(
        filename="demo import.pdf",
        title="",
        subject="  Math  ",
        document_kind="mock",
        normalize_label=lambda value, fallback: (value or "").strip() or fallback,
        normalize_document_kind=lambda value: "mock paper" if value == "mock" else "book",
        default_subject="General",
    )
    assert metadata == {"title": "demo import", "subject": "Math", "document_kind": "mock paper"}
    assert sakura_questions.import_question_text("slice", "page") == "slice"
    assert sakura_questions.import_question_text("", "page") == "page"
    assert sakura_questions.import_question_no({"question_no": 7}) == "7"
    assert sakura_questions.import_question_no({}) == ""

    textbook_metadata = sakura_textbook.textbook_import_metadata(
        "lecture notes/part 1.pdf",
        "",
        "  Math  ",
        normalize_label=lambda value, fallback: (value or "").strip() or fallback,
        default_subject="General",
    )
    assert textbook_metadata == {
        "safe_name": "lecture_notes_part_1.pdf",
        "title": "part 1",
        "subject": "Math",
    }
    textbook_conn = make_textbook_conn()
    sakura_textbook.insert_textbook(
        textbook_conn,
        book_id="book1",
        title="Lecture Notes",
        subject="Math",
        filename="lecture.pdf",
        stored_path=Path("data/uploads/lecture.pdf"),
        page_count=4,
        created_at="now",
    )
    textbook_record = textbook_conn.execute("SELECT * FROM textbooks").fetchone()
    assert textbook_record["title"] == "Lecture Notes"
    assert textbook_record["stored_path"] == str(Path("data/uploads/lecture.pdf"))
    assert sakura_textbook.imported_textbook_payload(
        book_id="book1",
        title="Lecture Notes",
        subject="Math",
        page_count=4,
    ) == {
        "textbook_id": "book1",
        "title": "Lecture Notes",
        "subject": "Math",
        "page_count": 4,
    }
    textbook_doc = fitz.open()
    textbook_page = textbook_doc.new_page()
    textbook_page.insert_text((72, 100), "Definition one.", fontsize=12)
    rendered_paths = []
    sakura_textbook.import_textbook_page(
        textbook_conn,
        textbook_page,
        book_id="book1",
        page_number=2,
        page_dir=Path("data/pages"),
        render_page_image=lambda _page, path: rendered_paths.append(path),
        created_at="now",
    )
    textbook_row = textbook_conn.execute("SELECT * FROM textbook_pages").fetchone()
    assert textbook_row["textbook_id"] == "book1"
    assert textbook_row["page_number"] == 2
    assert textbook_row["image_path"] == str(Path("data/pages/book1_textbook_page_002.png"))
    assert "Definition one." in textbook_row["page_text"]
    assert json.loads(textbook_row["paragraphs_json"]) == ["Definition one."]
    assert rendered_paths == [Path("data/pages/book1_textbook_page_002.png")]
    chat_id = sakura_textbook.save_textbook_chat_message(
        textbook_conn,
        textbook_id="book1",
        page_number=2,
        role="user",
        content="x" * 12,
        content_limit=10,
        created_at="now",
    )
    chat_row = textbook_conn.execute("SELECT * FROM textbook_chats WHERE id = ?", (chat_id,)).fetchone()
    assert chat_row["role"] == "user"
    assert chat_row["content"] == "x" * 10
    assert chat_row["created_at"] == "now"
    parsed_request = sakura_textbook.parse_textbook_request(
        {
            "textbook_id": " book1 ",
            "page_number": "2",
            "paragraph_index": "3",
            "message": " explain ",
            "history": [{"role": "user", "content": "question"}],
        },
        parse_positive_int=lambda value, fallback: int(value) if value.isdigit() else fallback,
    )
    assert parsed_request == {
        "textbook_id": "book1",
        "page_number": 2,
        "paragraph_index": 3,
        "message": "explain",
        "history": [{"role": "user", "content": "question"}],
    }
    textbook_doc.close()
    textbook_conn.close()

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
    classified_summary = sakura_questions.classify_and_insert_imported_question(
        conn,
        classify_question=lambda text, subject, chapter, kind: {
            "category": subject,
            "subcategory": kind,
            "chapter": chapter,
            "difficulty": "medium",
        },
        q_id="q2",
        doc_id="d1",
        page_number=4,
        seq_no=2,
        item={"question_no": 8},
        image_path=Path("data/pages/q2.png"),
        slice_text="",
        page_text="fallback page text",
        subject="math",
        chapter_hint="ch2",
        document_kind="book",
        created_at="now",
    )
    assert classified_summary["question_no"] == "8"
    q2 = conn.execute("SELECT * FROM questions WHERE id = ?", ("q2",)).fetchone()
    assert q2["ocr_text"] == "fallback page text"
    assert q2["category"] == "math"
    assert q2["chapter"] == "ch2"

    with tempfile.TemporaryDirectory() as tmp:
        pdf = fitz.open()
        page = pdf.new_page(width=595, height=842)
        page.insert_text((72, 120), "Rendered question text", fontsize=12)
        previous = sakura_pdf.PreviousQuestionState()
        processed = sakura_import.process_question_slice(
            conn,
            page=page,
            page_dir=Path(tmp),
            doc_id="d1",
            page_number=5,
            slice_index=1,
            seq_no=3,
            item={"question_no": "9", "clip": None},
            page_text="Rendered question text",
            subject="math",
            chapter_hint="ch3",
            document_kind="book",
            created_at="now",
            previous_question=previous,
            classify_question=lambda _text, subject, chapter, kind: {
                "category": subject,
                "subcategory": kind,
                "chapter": chapter,
                "difficulty": "medium",
            },
            question_id_factory=lambda: "q3",
        )
        pdf.close()
        assert processed["id"] == "q3"
        assert previous.question_id == "q3"
        assert previous.image_path is not None and previous.image_path.exists()
        assert previous.value is None

    payload = sakura_documents.imported_document_payload(
        doc_id="d1",
        title="Title",
        subject="math",
        document_kind="book",
        filename="a.pdf",
        questions=[summary],
    )
    assert payload == {
        "document_id": "d1",
        "title": "Title",
        "subject": "math",
        "document_kind": "book",
        "filename": "a.pdf",
        "page_count": 1,
        "questions": [summary],
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
    calls = []

    def fake_call_llm_messages(messages, temperature=0.3):
        calls.append((messages, temperature))
        return "teacher answer"

    turn = sakura_ai.build_teacher_chat_turn(
        "please make a plan",
        {
            "profile": {"headline": "needs limits"},
            "top_gaps": [{"name": "limits"}],
            "review_backlog": {},
            "today_actions": [],
        },
        call_llm_messages=fake_call_llm_messages,
    )
    assert turn["answer"] == "teacher answer"
    assert turn["intent"] in sakura_ai.TEACHER_INTENTS
    assert turn["strategy"]["key"]
    assert len(calls) == 1
    assert calls[0][1] == 0.35
    assert calls[0][0][-1] == {"role": "user", "content": "please make a plan"}
    assert sakura_coach.profile_summary_from_latest(None) is None
    assert sakura_coach.profile_summary_from_latest(
        {
            "version": 3,
            "created_at": "now",
            "profile": {
                "evidence_count": 8,
                "knowledge_count": 4,
                "avg_mastery": 0.75,
                "velocity": "up",
                "headline": "steady",
            },
        }
    ) == {
        "version": 3,
        "evidence_count": 8,
        "knowledge_count": 4,
        "avg_mastery": 0.75,
        "velocity": "up",
        "headline": "steady",
        "created_at": "now",
    }
    assert sakura_coach.cached_plan_from_state({"plan_json": "{\"a\": 1}"}) == {"a": 1}
    assert sakura_coach.cached_plan_from_state({"plan_json": "[]"}) == {}
    assert sakura_coach.cached_plan_from_state({"plan_json": "not-json"}) == {}

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

            textbook_result = app.import_textbook_pdf(
                "demo textbook.pdf",
                pdf_bytes,
                title="Demo Textbook",
                subject="Math",
            )
            assert textbook_result["title"] == "Demo Textbook"
            assert textbook_result["subject"] == "Math"
            assert textbook_result["page_count"] == 1

            conn = app.connect()
            try:
                textbooks = conn.execute("SELECT * FROM textbooks").fetchall()
                textbook_pages = conn.execute("SELECT * FROM textbook_pages").fetchall()
            finally:
                conn.close()
            assert len(textbooks) == 1
            assert textbooks[0]["title"] == "Demo Textbook"
            assert Path(textbooks[0]["stored_path"]).exists()
            assert len(textbook_pages) == 1
            assert "sin(x)/x" in textbook_pages[0]["page_text"]
            assert Path(textbook_pages[0]["image_path"]).exists()
        finally:
            for key, value in original_paths.items():
                setattr(app, key, value)
            gc.collect()


def main() -> None:
    test_http_file_serving()
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
