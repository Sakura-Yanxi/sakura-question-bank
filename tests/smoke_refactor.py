from __future__ import annotations

import json
import gc
import io
import os
import re
import sqlite3
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sakura.ai import client as sakura_ai
from sakura.ai import coach as sakura_coach
from sakura.ai import profile as sakura_profile
from sakura.ai import teacher_memory as sakura_teacher_memory
from sakura.api import textbook_runtime as sakura_textbook_runtime
from sakura.content import classify as sakura_classify
from sakura.content import documents as sakura_documents
from sakura.content import importer as sakura_import
from sakura.content import models as sakura_models
from sakura.content import pdf as sakura_pdf
from sakura.content import questions as sakura_questions
from sakura.content import textbook as sakura_textbook
from sakura.core import http as sakura_http
from sakura.core import config as sakura_config
from sakura.core import routes as sakura_routes
from sakura.system import backup as sakura_backup
from sakura.system import email as sakura_email
from sakura.system import notifications as sakura_notifications
from sakura.system import practice_pages as sakura_practice_pages
from sakura.system import settings as sakura_settings
from sakura.system import update as sakura_update

import app
import notify_daily


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


class FakeUpload:
    def __init__(self, filename: str) -> None:
        self.filename = filename


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
    assert sakura_routes.route_for("/api/version", sakura_routes.GET_ROUTES).with_query is True
    assert sakura_routes.route_for("/api/notify/settings", sakura_routes.POST_ROUTES).handler == "handle_notification_settings_post"
    assert sakura_routes.route_for("/api/textbooks/vision", sakura_routes.POST_ROUTES).handler == "handle_textbook_vision"
    assert sakura_routes.route_for("/api/missing", sakura_routes.GET_ROUTES) is None
    assert sakura_routes.split_path("/api/practice/b1/questions/q2") == ["api", "practice", "b1", "questions", "q2"]
    assert sakura_routes.get_dynamic_route("/api/questions/q1").handler == "handle_question_detail"
    assert sakura_routes.get_dynamic_route("/api/textbooks/t1/pages/3").args == ("t1", 3)
    assert sakura_routes.get_dynamic_route("/api/textbooks/t1/pages/not-a-number") is None
    assert sakura_routes.get_dynamic_route("/api/questions/q1/extra") is None
    assert sakura_routes.post_dynamic_route("/api/questions/q1/hint").args == ("q1",)
    assert sakura_routes.post_dynamic_route("/api/practice/b1/questions/q2").args == ("b1", "q2")
    assert sakura_routes.post_dynamic_route("/api/practice/b1/questions/q2/extra") is None
    assert sakura_routes.delete_dynamic_route("/api/mentor-experience/e1").handler == "handle_mentor_experience_delete"
    assert sakura_routes.delete_dynamic_route("/api/textbooks/t1/pages/0") is None
    assert sakura_routes.patch_dynamic_route("/api/documents/d1").args == ("d1",)
    assert sakura_routes.patch_dynamic_route("/api/documents/d1/extra") is None
    missing_handlers = [name for name in sakura_routes.configured_handler_names() if not hasattr(app.DemoHandler, name)]
    assert missing_handlers == []
    assert app.demo_mode_enabled() is app.DEMO_MODE
    assert app.public_file_base_for_path("/static/styles.css") == app.STATIC_DIR
    assert app.public_file_base_for_path("/data/pages/example.png") == app.PAGE_DIR
    assert app.public_file_base_for_path("/data/gaoshu_demo.sqlite3") is None
    assert app.public_file_base_for_path("/data/uploads/source.pdf") is None
    assert app.to_public_path(app.PAGE_DIR / "example.png") == "/data/pages/example.png"
    assert app.to_public_path(app.STATIC_DIR / "styles.css") == "/static/styles.css"
    assert not app.to_public_path(app.UPLOAD_DIR / "source.pdf").startswith("/data/uploads/")
    disposition = sakura_http.content_disposition_attachment('反思 "周报".txt')
    assert 'attachment; filename="' in disposition
    assert "filename*=UTF-8''" in disposition
    assert "%E5%8F%8D%E6%80%9D" in disposition
    assert "\n" not in sakura_http.content_disposition_attachment("bad\nname.pdf")

    download = FakeHttpHandler()
    sakura_http.send_attachment_bytes(
        download,
        b"pdf",
        filename="错题.pdf",
        content_type="application/pdf",
    )
    assert download.status == 200
    assert ("Content-Type", "application/pdf") in download.headers
    assert ("Content-Length", "3") in download.headers
    assert download.wfile.getvalue() == b"pdf"

    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / "backup.zip"
        archive.write_bytes(b"zip-body")
        streamed = FakeHttpHandler()
        sakura_http.stream_attachment_file(
            streamed,
            archive,
            filename="backup.zip",
            content_type="application/zip",
            chunk_size=3,
        )
        assert ("Content-Type", "application/zip") in streamed.headers
        assert ("Content-Length", "8") in streamed.headers
        assert streamed.wfile.getvalue() == b"zip-body"

    assert sakura_http.first_form_file({"backup": FakeUpload("backup.zip")}, "backup", "file").filename == "backup.zip"
    assert sakura_http.first_form_file({"file": [FakeUpload("book.pdf")]}, "backup", "file").filename == "book.pdf"
    assert sakura_http.first_form_file({}, "file") is None
    assert sakura_http.uploaded_filename(FakeUpload("Book.PDF")) == "Book.PDF"
    assert sakura_http.uploaded_file_has_suffix(FakeUpload("Book.PDF"), ".pdf")
    assert not sakura_http.uploaded_file_has_suffix(FakeUpload("Book.txt"), ".pdf")


def test_update_release_helpers() -> None:
    assert sakura_update.repo_configured("Sakura-Yanxi/-") is True
    assert sakura_update.repo_configured("owner/repo") is True
    assert sakura_update.repo_configured("") is False
    assert sakura_update.repo_configured("owner/") is False
    assert sakura_update.repo_configured("owner/repo/extra") is False
    assert sakura_update.releases_url("Sakura-Yanxi/-") == "https://github.com/Sakura-Yanxi/-/releases"
    assert sakura_update.is_newer("v1.0.1", "1.0.0") is True
    assert sakura_update.is_newer("v1.0.0", "1.0.1") is False


def test_json_body_parsing_guards() -> None:
    body = io.BytesIO(b'{"ok": true}')
    assert sakura_http.read_json_body({"Content-Length": "12"}, body) == {"ok": True}
    assert sakura_http.read_json_body({"Content-Length": "0"}, io.BytesIO()) == {}
    assert sakura_http.read_limited_body({"Content-Length": "4"}, io.BytesIO(b"test"), max_bytes=4) == b"test"

    for headers, raw in [
        ({"Content-Length": "abc"}, b"{}"),
        ({"Content-Length": "5"}, b"{bad}"),
        ({"Content-Length": "2"}, b"[]"),
    ]:
        try:
            sakura_http.read_json_body(headers, io.BytesIO(raw))
            raise AssertionError("invalid JSON body should be rejected")
        except sakura_http.BadRequestError:
            pass

    try:
        sakura_http.read_json_body({"Content-Length": "3"}, io.BytesIO(b"{}"), max_bytes=2)
        raise AssertionError("oversized JSON body should be rejected")
    except sakura_http.BadRequestError:
        pass


def test_question_detail_legacy_note_fallback() -> None:
    row = {
        "id": "q1",
        "status": "需复习",
        "user_note": "补一次定义",
        "meta_tags": ["概念混淆"],
        "last_reviewed_at": "",
        "created_at": "2026-06-01T10:00:00",
    }
    detail = sakura_models.question_detail_to_dict(
        None,
        row,
        row_to_dict=lambda value: dict(value),
        load_question_review_notes=lambda conn, question_id: [],
    )
    assert detail["review_notes"] == [
        {
            "id": "legacy-user-note",
            "question_id": "q1",
            "status": "需复习",
            "note": "补一次定义",
            "meta_tags": ["概念混淆"],
            "source": "legacy",
            "created_at": "2026-06-01T10:00:00",
        }
    ]


def test_local_env_override_policy() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".env").write_text(
            "LLM_VISION_MODEL=qwen-vl-max\n"
            "EXTERNAL_ONLY=from-dotenv\n",
            encoding="utf-8",
        )
        old_vision = os.environ.get("LLM_VISION_MODEL")
        old_external = os.environ.get("EXTERNAL_ONLY")
        try:
            os.environ["LLM_VISION_MODEL"] = "old-system-value"
            os.environ["EXTERNAL_ONLY"] = "system-value"
            sakura_config.load_local_env(root, override_keys={"LLM_VISION_MODEL"})
            assert os.environ["LLM_VISION_MODEL"] == "qwen-vl-max"
            assert os.environ["EXTERNAL_ONLY"] == "system-value"
        finally:
            if old_vision is None:
                os.environ.pop("LLM_VISION_MODEL", None)
            else:
                os.environ["LLM_VISION_MODEL"] = old_vision
            if old_external is None:
                os.environ.pop("EXTERNAL_ONLY", None)
            else:
                os.environ["EXTERNAL_ONLY"] = old_external


def test_settings_payload_parsing() -> None:
    llm = sakura_settings.parse_llm_settings_payload({
        "api_key": " key ",
        "base_url": " https://api.example.com/v1/ ",
        "model": " demo ",
        "vision_model": "",
        "vision_base_url": "",
    })
    assert llm == {
        "api_key": "key",
        "base_url": "https://api.example.com/v1/",
        "model": "demo",
        "vision_model": "",
        "vision_api_key": None,
        "vision_base_url": "",
    }
    try:
        sakura_settings.parse_llm_settings_payload({})
        raise AssertionError("empty llm settings payload should be rejected")
    except ValueError:
        pass

    notify = sakura_settings.parse_notification_settings_payload({
        "app_public_url": " https://example.com/sakura/ ",
        "email_enabled": "1",
    })
    assert notify["app_public_url"] == "https://example.com/sakura"
    assert notify["email_enabled"] == "1"
    assert notify["wework_webhook"] is None
    try:
        sakura_settings.parse_notification_settings_payload({"app_public_url": "not-a-url"})
        raise AssertionError("invalid public url should be rejected")
    except ValueError:
        pass


def test_profile_history_loading() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    try:
        conn.execute(
            """
            CREATE TABLE learner_profile (
                id TEXT,
                version INTEGER,
                scope TEXT,
                profile_json TEXT,
                evidence_count INTEGER,
                source TEXT,
                created_at TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO learner_profile VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("p1", 2, "__all__", json.dumps({"headline": "稳步提升", "avg_mastery": 0.7}, ensure_ascii=False), 5, "ai", "2026-06-02"),
        )
        conn.execute(
            "INSERT INTO learner_profile VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("p0", 1, "__all__", "{bad", 3, "local", "2026-06-01"),
        )
        history = sakura_profile.load_profile_history(conn)
        assert [item["id"] for item in history] == ["p1", "p0"]
        assert history[0]["headline"] == "稳步提升"
        assert history[0]["avg_mastery"] == 0.7
        assert history[1]["headline"] == "本地统计档案"
    finally:
        conn.close()


def test_memory_compression_helper() -> None:
    settings = {"compression_prompt": "请压缩"}
    ai_result = sakura_teacher_memory.compress_memory_content(
        content="用户总是忘记先写定义域",
        subject="高数",
        source="chat",
        instruction="保留复习建议",
        settings=settings,
        llm_enabled=True,
        call_llm=lambda prompt, temperature=0.15: "先提醒定义域，再进入计算。",
    )
    assert ai_result["summary"] == "先提醒定义域，再进入计算。"
    assert ai_result["used_ai"] is True
    assert ai_result["error"] == ""
    assert ai_result["memory_settings"] is settings

    errors = []

    def fail_llm(prompt, temperature=0.15):
        raise RuntimeError("no balance")

    fallback = sakura_teacher_memory.compress_memory_content(
        content="用户经常混淆公式，复习时需要先画图。",
        subject="高数",
        source="chat",
        instruction="",
        settings=settings,
        llm_enabled=True,
        call_llm=fail_llm,
        on_error=errors.append,
    )
    assert fallback["used_ai"] is False
    assert fallback["error"] == "no balance"
    assert errors and isinstance(errors[0], RuntimeError)
    assert "高数" in fallback["summary"]


def test_normalize_llm_error_messages() -> None:
    class FakeProviderError(Exception):
        def __init__(self, text: str, body=None) -> None:
            super().__init__(text)
            self.body = body

    insufficient = FakeProviderError(
        "Error code: 402 - insufficient_balance",
        {"code": "402", "message": "Insufficient account balance", "type": "insufficient_balance"},
    )
    assert "余额不足" in sakura_ai.normalize_llm_error(insufficient)

    invalid_key = FakeProviderError(
        "Error code: 401 - invalid_api_key",
        {"code": "401", "message": "Incorrect API key", "type": "invalid_api_key"},
    )
    assert "API Key 无效" in sakura_ai.normalize_llm_error(invalid_key)

    fallback = FakeProviderError("something odd happened")
    assert sakura_ai.normalize_llm_error(fallback) == "something odd happened"


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


def test_practice_pages_and_reminder_helpers() -> None:
    source_bytes = Path("sakura/system/practice_pages.py").read_bytes()
    assert sum(byte > 127 for byte in source_bytes) == 0

    practice_html = sakura_practice_pages.render_practice_page("abc123")
    assert "Sakura \u5feb\u901f\u56de\u586b" in practice_html
    assert "\u6b63\u5728\u8bfb\u53d6\u672c\u6b21\u63a8\u9001" in practice_html
    assert "/api/practice/${batchId}" in practice_html
    assert "\\u6f02\\u4eae" in practice_html
    assert "data-status=\"${STATUS_RIGHT}\"" in practice_html

    done_html = sakura_practice_pages.render_today_done_page("http://example.com/")
    assert "\u4eca\u65e5\u6253\u5361\u6210\u529f" in done_html
    assert "http://example.com" in done_html

    calls = []

    def fake_send_notification(title, content, mode):
        calls.append(("send", title, content, mode))
        return {"ok": True, "selected_channel": mode, "detail": "sent"}

    def fake_pdf(reminder, mode):
        calls.append(("pdf", reminder["title"], mode))
        return {"ok": True, "filename": "daily.pdf"}

    old_send = app.send_notification
    old_pdf = app.send_practice_pdf_if_available
    app.send_notification = fake_send_notification
    app.send_practice_pdf_if_available = fake_pdf
    try:
        result, pdf = app.send_reminder_payload({"title": "T", "content": "C", "batch_id": "b1"}, "wework")
    finally:
        app.send_notification = old_send
        app.send_practice_pdf_if_available = old_pdf

    assert result["ok"] is True
    assert result["practice_pdf"] == {"ok": True, "filename": "daily.pdf"}
    assert pdf == {"ok": True, "filename": "daily.pdf"}
    assert calls == [("send", "T", "C", "wework"), ("pdf", "T", "wework")]
    payload = app.reminder_response_payload("daily", {"title": "T", "batch_id": "b1"}, result, "wework")
    assert payload["kind"] == "daily"
    assert payload["batch_id"] == "b1"
    assert payload["practice_pdf"] == {"ok": True, "filename": "daily.pdf"}
    assert app.reminder_kinds_for_minute(
        "20:00",
        [
            ("morning", "1", "10:00"),
            ("night", "1", "20:00"),
            ("weather", "0", "20:00"),
            ("daily", "1", "20:00"),
        ],
    ) == ["night", "daily"]
    assert app.reminder_kinds_for_minute("21:00", [("night", "1", "20:00")]) == []
    old_value = os.environ.get("SAKURA_SCHEDULER_POLL_SECONDS")
    try:
        os.environ["SAKURA_SCHEDULER_POLL_SECONDS"] = "bad"
        assert app.env_int("SAKURA_SCHEDULER_POLL_SECONDS", 30, minimum=10) == 30
        os.environ["SAKURA_SCHEDULER_POLL_SECONDS"] = "3"
        assert app.env_int("SAKURA_SCHEDULER_POLL_SECONDS", 30, minimum=10) == 10
    finally:
        if old_value is None:
            os.environ.pop("SAKURA_SCHEDULER_POLL_SECONDS", None)
        else:
            os.environ["SAKURA_SCHEDULER_POLL_SECONDS"] = old_value


def test_notification_summary_helpers() -> None:
    assert sakura_notifications.is_private_app_url("http://127.0.0.1:8000")
    assert sakura_notifications.is_private_app_url("http://192.168.1.5")
    assert sakura_notifications.is_private_app_url("http://172.20.1.5")
    assert not sakura_notifications.is_private_app_url("https://example.com")

    private_lines = sakura_notifications.reminder_link_lines("http://127.0.0.1:8000", "http://127.0.0.1:8000/practice/a", 3)
    assert "\u624b\u673a\u5fae\u4fe1\u91cc\u901a\u5e38\u6253\u4e0d\u5f00" in private_lines[0]
    public_lines = sakura_notifications.reminder_link_lines("https://example.com", "https://example.com/practice/a", 3)
    assert "3 \u9053\u9898" in public_lines[0]
    assert "Sakura \u505a\u9898\u96c6" in public_lines[1]

    questions = [
        {
            "subject": "S",
            "document_title": f"B{i}",
            "page_number": i + 1,
            "chapter": "C",
            "status": "\u505a\u9519",
            "question_no": str(i),
        }
        for i in range(10)
    ]
    lines = sakura_notifications.question_summary_lines({"payload": {"plan": questions}}, max_items=8)
    assert len(lines) == 9
    assert lines[0].startswith("1. S / B0 P1")
    assert "\u8fd8\u6709 2 \u9053\u9898" in lines[-1]
    empty = sakura_notifications.question_summary_lines({"payload": {"plan": []}})
    assert "\u672c\u6b21\u6ca1\u6709\u7b5b\u9009\u51fa" in empty[0]


def test_scheduled_dispatch_failure_is_logged() -> None:
    original_paths = {
        "DATA_DIR": app.DATA_DIR,
        "UPLOAD_DIR": app.UPLOAD_DIR,
        "PAGE_DIR": app.PAGE_DIR,
        "DB_PATH": app.DB_PATH,
    }
    old_builder = app.build_scheduled_reminder
    old_print_exc = app.traceback.print_exc
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        app.DATA_DIR = root / "data"
        app.UPLOAD_DIR = app.DATA_DIR / "uploads"
        app.PAGE_DIR = app.DATA_DIR / "pages"
        app.DB_PATH = app.DATA_DIR / "gaoshu_demo.sqlite3"

        def broken_builder(_conn, _kind):
            raise RuntimeError("builder failed")

        app.build_scheduled_reminder = broken_builder
        app.traceback.print_exc = lambda: None
        try:
            app.init_db()
            result = app.dispatch_scheduled_reminder("morning", "wework")
            assert result["ok"] is False
            assert result["kind"] == "morning"
            assert "builder failed" in str(result["detail"])
            conn = app.connect()
            try:
                row = conn.execute(
                    "SELECT kind, status, detail_json FROM reminder_dispatch_log ORDER BY updated_at DESC LIMIT 1"
                ).fetchone()
            finally:
                conn.close()
            assert row["kind"] == "morning"
            assert row["status"] == "failed"
            assert "builder failed" in row["detail_json"]
        finally:
            app.build_scheduled_reminder = old_builder
            app.traceback.print_exc = old_print_exc
            for key, value in original_paths.items():
                setattr(app, key, value)


def test_static_frontend_wiring() -> None:
    html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    scripts = re.findall(r'<script src="([^"]+)"', html)
    local_scripts = [src.split("?", 1)[0] for src in scripts if src.startswith("/static/")]
    assert "/static/js/system/reminders.js" in local_scripts
    assert "/static/js/core/app.js" in local_scripts
    assert local_scripts.index("/static/js/system/reminders.js") < local_scripts.index("/static/js/core/app.js")
    for script in local_scripts:
        assert (ROOT / script.lstrip("/")).exists(), script

    ids = set(re.findall(r'\bid="([^"]+)"', html))
    reminder_ids = {
        "checkinBtn",
        "testMorningBtn",
        "testNightBtn",
        "saveRemindSettings",
        "remindMorningOn",
        "remindMorningTime",
        "remindNightTime",
        "remindWeatherOn",
        "remindWeatherTime",
        "checkinMode",
        "remindDailyScope",
        "remindDailyLimit",
        "remindSendPdf",
        "saveNotifySettings",
        "saveSecuritySettings",
        "testEmailBtn",
        "saveWeatherCity",
        "previewWeather",
        "sendWeatherPreview",
        "testWeatherPush",
        "textbookScanStatus",
        "textbookScanBar",
        "textbookParagraphDetail",
        "textbookParagraphDetailText",
        "copyTextbookParagraph",
        "readTextbookVision",
        "prevTextbookPage",
        "nextTextbookPage",
        "dashboardMantra",
    }
    assert reminder_ids <= ids

    reminders_js = (ROOT / "static" / "js" / "system" / "reminders.js").read_text(encoding="utf-8")
    core_js = (ROOT / "static" / "js" / "core" / "app.js").read_text(encoding="utf-8")
    assert "window.SakuraReminderControls" in reminders_js
    assert "window.SakuraReminderControls.bind()" in core_js
    assert "reminderControlsBound" in reminders_js
    assert "let lastAiChatAnswer" not in reminders_js


def test_notify_daily_endpoints() -> None:
    assert notify_daily.ENDPOINTS == {
        "daily": "/api/push/daily",
        "morning": "/api/push/morning",
        "night": "/api/push/night",
        "weather": "/api/push/weather",
    }


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
            display_page INTEGER,
            image_path TEXT NOT NULL DEFAULT '',
            page_text TEXT NOT NULL DEFAULT '',
            paragraphs_json TEXT NOT NULL DEFAULT '[]',
            rendered INTEGER NOT NULL DEFAULT 0,
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
    assert sakura_textbook.looks_like_question_document("5月模考试卷.pdf")
    assert sakura_textbook.looks_like_question_document("math.pdf", "2026 真题")
    assert not sakura_textbook.looks_like_question_document("lecture notes.pdf", "Computer Architecture")
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
    assert sakura_textbook.textbook_to_dict({
        "id": "empty",
        "filename": "empty.pdf",
        "title": "Empty",
        "page_count": 4,
        "saved_pages": 0,
    })["saved_pages"] == 0
    # Lazy import: register one unrendered placeholder per page, no rendering yet.
    sakura_textbook.insert_textbook_page_placeholders(
        textbook_conn, book_id="book1", page_count=4, created_at="now"
    )
    placeholder_rows = textbook_conn.execute(
        "SELECT page_number, display_page, rendered, image_path FROM textbook_pages ORDER BY page_number"
    ).fetchall()
    assert [r["page_number"] for r in placeholder_rows] == [1, 2, 3, 4]
    assert [r["display_page"] for r in placeholder_rows] == [None, None, None, None]
    assert all(r["rendered"] == 0 and r["image_path"] == "" for r in placeholder_rows)

    # Read-on-demand: rendering page 2 extracts text + paragraphs for the current response only.
    import tempfile

    lazy_dir = Path(tempfile.mkdtemp())
    real_pdf = lazy_dir / "lecture.pdf"
    _doc = fitz.open()
    _doc.new_page()
    _doc.new_page().insert_text((72, 100), "Definition one.", fontsize=12)
    _doc.save(real_pdf)
    _doc.close()
    page_row = textbook_conn.execute("SELECT * FROM textbook_pages WHERE page_number = 2").fetchone()
    rendered = sakura_textbook.render_textbook_page_view(
        {"id": "book1", "stored_path": str(real_pdf)},
        page_row,
        page_dir=lazy_dir,
        render_page_image=lambda _page, path: Path(path).write_bytes(b"PNG"),
    )
    assert rendered["rendered"] == 0
    assert "Definition one." in rendered["page_text"]
    assert json.loads(rendered["paragraphs_json"]) == ["Definition one."]
    assert rendered["display_page"] == 2
    assert rendered["image_path"] == str(lazy_dir / "book1_textbook_current.png")
    db_row2 = textbook_conn.execute("SELECT rendered, page_text FROM textbook_pages WHERE page_number = 2").fetchone()
    assert db_row2["rendered"] == 0 and db_row2["page_text"] == ""
    assert textbook_conn.execute("SELECT COUNT(*) c FROM textbook_pages WHERE rendered = 0").fetchone()["c"] == 4

    blank_pdf = lazy_dir / "scan.pdf"
    _scan = fitz.open()
    for _ in range(3):
        _scan.new_page(width=595, height=842)
    _scan.save(blank_pdf)
    _scan.close()
    textbook_conn.execute(
        "UPDATE textbook_pages SET rendered = 0, page_text = '', paragraphs_json = '[]', image_path = '' WHERE page_number = 3"
    )
    scan_row = textbook_conn.execute("SELECT * FROM textbook_pages WHERE page_number = 3").fetchone()
    ocr_rendered = sakura_textbook.render_textbook_page_view(
        {"id": "book1", "stored_path": str(blank_pdf)},
        scan_row,
        page_dir=lazy_dir,
        render_page_image=lambda _page, path: Path(path).write_bytes(b"PNG"),
        ocr_image_text=lambda path: "OCR first line.\nOCR second line.",
    )
    assert "OCR first line" in ocr_rendered["page_text"]
    assert json.loads(ocr_rendered["paragraphs_json"])

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
            "selected_paragraph_text": " cached paragraph ",
            "message": " explain ",
            "history": [{"role": "user", "content": "question"}],
        },
        parse_positive_int=lambda value, fallback: int(value) if value.isdigit() else fallback,
    )
    assert parsed_request == {
        "textbook_id": "book1",
        "page_number": 2,
        "paragraph_index": 3,
        "selected_paragraph_text": "cached paragraph",
        "message": "explain",
        "history": [{"role": "user", "content": "question"}],
    }
    cached_book, cached_page = sakura_textbook.build_textbook_selected_paragraph_context(
        textbook_conn,
        "book1",
        2,
        3,
        "Only this paragraph.",
        to_public_path=lambda path: path,
    )
    assert cached_book["title"] == "Lecture Notes"
    assert cached_page["page_number"] == 2
    assert cached_page["selected_paragraph"] == "Only this paragraph."
    assert cached_page["paragraphs"] == ["Only this paragraph."]
    assert cached_page["page_text"] == "Only this paragraph."
    textbook_conn.execute("UPDATE textbook_pages SET display_page = 35 WHERE page_number = 2")
    resolved_book, resolved_page = sakura_textbook.resolve_textbook_page_row(textbook_conn, "book1", 2)
    assert resolved_book["title"] == "Lecture Notes"
    assert resolved_page["page_number"] == 2
    assert resolved_page["display_page"] == 35
    try:
        sakura_textbook.resolve_textbook_page_row(textbook_conn, "book1", 35)
        assert False, "display_page must not resolve to a different PDF page"
    except ValueError:
        pass
    delete_result = sakura_textbook.delete_textbook_page(
        textbook_conn,
        "book1",
        2,
        delete_file=lambda _path: None,
    )
    assert delete_result["deleted_page"] == 2
    assert delete_result["next_page"] == 3
    assert "deleted_display_page" not in delete_result
    assert "next_display_page" not in delete_result
    assert textbook_conn.execute(
        "SELECT COUNT(*) c FROM textbook_pages WHERE page_number = 2"
    ).fetchone()["c"] == 0
    assert textbook_conn.execute(
        "SELECT COUNT(*) c FROM textbook_pages WHERE page_number = 1"
    ).fetchone()["c"] == 1
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


def test_scanned_textbook_requires_image_or_vision() -> None:
    assert sakura_textbook.looks_like_question_document("2026数学模拟卷.pdf")
    assert sakura_textbook.looks_like_question_document("考研数学真题卷.pdf")
    assert sakura_textbook.looks_like_question_document("冲刺A卷.pdf")
    assert sakura_textbook.looks_like_question_document("A卷.pdf", "教材")
    assert sakura_textbook.looks_like_question_document("阶段检测卷.pdf")
    assert not sakura_textbook.looks_like_question_document("高等数学第一卷.pdf")
    assert not sakura_textbook.looks_like_question_document("线性代数上卷.pdf", "教材")

    calls = []
    book = {"title": "Scan", "subject": "Math"}
    page = {
        "page_number": 3,
        "page_text": "",
        "paragraphs": [],
        "selected_paragraph": "",
        "image_path": "missing.png",
    }
    missing_image = sakura_textbook.explain_textbook(
        book,
        page,
        "explain",
        [],
        llm_enabled=True,
        call_llm_messages=lambda messages, temperature=0.3: calls.append(messages) or "text fallback",
        vision_enabled=True,
        call_llm_vision=lambda messages, temperature=0.3: "vision answer",
        image_to_data_url=lambda path: "",
    )
    assert not calls
    assert "AI" in missing_image

    no_vision = sakura_textbook.explain_textbook(
        book,
        page,
        "explain",
        [],
        llm_enabled=True,
        call_llm_messages=lambda messages, temperature=0.3: calls.append(messages) or "text fallback",
        vision_enabled=False,
        image_to_data_url=lambda path: "data:image/png;base64,abc",
    )
    assert not calls
    assert "AI" in no_vision

    vision = sakura_textbook.explain_textbook(
        book,
        page,
        "explain",
        [],
        llm_enabled=True,
        call_llm_messages=lambda messages, temperature=0.3: "text fallback",
        vision_enabled=True,
        call_llm_vision=lambda messages, temperature=0.3: "vision answer",
        image_to_data_url=lambda path: "data:image/png;base64,abc",
    )
    assert vision == "vision answer"
    direct_vision = sakura_textbook_runtime.explain_textbook_page_with_vision(
        book,
        {"page_number": 3, "display_page": 3, "page_text": "cached text", "image_path": "page.png"},
        "explain",
        vision_enabled=True,
        call_llm_vision=lambda messages, temperature=0.3: messages[1]["content"][0]["text"],
        image_to_data_url=lambda path: "data:image/png;base64,abc",
    )
    assert "cached text" in direct_vision and "任务：explain" in direct_vision


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

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        db_path = root / "gaoshu_demo.sqlite3"
        sqlite3.connect(db_path).close()
        export_path, filename = sakura_backup.build_backup_export_file(
            {"mode": ["light"]},
            db_path,
            {"uploads": root / "uploads", "pages": root / "pages"},
            now,
        )
        try:
            assert filename == "sakura_backup_light_20260102_030405.zip"
            assert export_path.exists()
            with zipfile.ZipFile(export_path) as zf:
                assert "manifest.json" in zf.namelist()
                assert "data/gaoshu_demo.sqlite3" in zf.namelist()
        finally:
            export_path.unlink(missing_ok=True)


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

    response = sakura_teacher_memory.run_teacher_chat_turn(
        conn,
        message="please review limits",
        context={"profile": {"headline": "steady"}, "top_gaps": [], "review_backlog": {}, "today_actions": []},
        call_llm_messages=lambda messages, temperature=0.35: "review answer",
        model="demo-model",
        base_url="https://api.example.com/v1",
    )
    assert response["answer"] == "review answer"
    assert response["has_key"] is True
    assert response["model"] == "demo-model"
    assert response["base_url"] == "https://api.example.com/v1"
    assert response["teacher_intent"] in sakura_ai.TEACHER_INTENTS
    assert conn.execute("SELECT COUNT(*) c FROM ai_teacher_turns").fetchone()["c"] == 2


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
            try:
                app.import_textbook_pdf(
                    "math mock exam.pdf",
                    pdf_bytes,
                    title="5月模考试卷",
                    subject="Math",
                )
            except ValueError as exc:
                assert "全真模拟卷" in str(exc)
            else:
                raise AssertionError("question-like PDF was accepted by textbook import")

            mock_result = app.import_pdf(
                "math mock exam.pdf",
                pdf_bytes,
                title="5月模考试卷",
                subject="Math",
                document_kind=app.MOCK_PAPER_KIND,
                split_questions=True,
            )
            assert mock_result["document_kind"] == app.MOCK_PAPER_KIND
            assert len(mock_result["questions"]) == 1

            conn = app.connect()
            try:
                textbooks = conn.execute("SELECT * FROM textbooks").fetchall()
                textbook_pages = conn.execute("SELECT * FROM textbook_pages").fetchall()
                mock_docs = conn.execute(
                    "SELECT * FROM documents WHERE document_kind = ?",
                    (app.MOCK_PAPER_KIND,),
                ).fetchall()
            finally:
                conn.close()
            assert len(textbooks) == 1
            assert len(mock_docs) == 1
            assert textbooks[0]["title"] == "Demo Textbook"
            assert Path(textbooks[0]["stored_path"]).exists()
            # Lazy import: one unrendered placeholder, no extracted text / image yet.
            assert len(textbook_pages) == 1
            assert textbook_pages[0]["rendered"] == 0
            assert textbook_pages[0]["page_text"] == ""
            assert textbook_pages[0]["image_path"] == ""

            # Reading page 1 renders it for the current response without persisting OCR text.
            conn = app.connect()
            try:
                _book, current_page = app.build_textbook_context(conn, textbook_result["textbook_id"], 1)
                rendered_row = conn.execute(
                    "SELECT * FROM textbook_pages WHERE page_number = 1"
                ).fetchone()
            finally:
                conn.close()
            assert "sin(x)/x" in current_page["page_text"]
            assert Path(current_page["image_path"]).exists()
            assert rendered_row["rendered"] == 0
            assert rendered_row["page_text"] == ""
            assert rendered_row["image_path"] == ""
        finally:
            for key, value in original_paths.items():
                setattr(app, key, value)
            gc.collect()


def main() -> None:
    test_http_file_serving()
    test_local_env_override_policy()
    test_question_detail_legacy_note_fallback()
    test_settings_payload_parsing()
    test_profile_history_loading()
    test_memory_compression_helper()
    test_email_notification_helpers()
    test_practice_pages_and_reminder_helpers()
    test_notification_summary_helpers()
    test_scheduled_dispatch_failure_is_logged()
    test_static_frontend_wiring()
    test_notify_daily_endpoints()
    test_pdf_helpers()
    test_chapter_carry_state()
    test_import_insert_and_ocr_helpers()
    test_question_update_helper()
    test_scanned_textbook_requires_image_or_vision()
    test_backup_options()
    test_teacher_turn_persistence()
    test_real_import_pdf_smoke()
    print("smoke_refactor_ok")


if __name__ == "__main__":
    main()
