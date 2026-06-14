from __future__ import annotations

import json
import traceback
import urllib.request
from datetime import date, datetime
from typing import Callable
from urllib.parse import parse_qs, urlparse

from sakura.system import email as sakura_email
from sakura.system import reminders as sakura_reminders


PUSHPLUS_URL = "https://www.pushplus.plus/send"
WEWORK_UPLOAD_URL = "https://qyapi.weixin.qq.com/cgi-bin/webhook/upload_media"
WEWORK_FILE_LIMIT_BYTES = 20 * 1024 * 1024


def is_private_app_url(url: str) -> bool:
    parsed = urlparse(str(url or ""))
    host = (parsed.hostname or "").lower()
    if not host:
        return True
    if host in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}:
        return True
    if host.startswith("192.168.") or host.startswith("10."):
        return True
    if host.startswith("172."):
        parts = host.split(".")
        if len(parts) >= 2:
            try:
                return 16 <= int(parts[1]) <= 31
            except ValueError:
                return False
    return False


def _compact_text(value: object, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text if text else fallback


def question_summary_lines(batch: dict, max_items: int = 8) -> list[str]:
    payload = batch.get("payload") or {}
    questions = payload.get("plan") or [
        question
        for group in payload.get("groups", [])
        for question in (group.get("questions") or [])
    ]
    if not questions:
        return ["- 本次没有筛选出到期错题，可以把今天当作轻复盘日。"]

    lines: list[str] = []
    for index, question in enumerate(questions[:max_items], start=1):
        subject = _compact_text(question.get("subject"), "未分科目")
        book = _compact_text(question.get("document_title") or question.get("filename"), "未命名资料")
        page = _compact_text(question.get("page_number"), "-")
        chapter = _compact_text(question.get("chapter") or question.get("category"), "未识别章节")
        status = _compact_text(question.get("status"), "待练")
        seq_no = _compact_text(question.get("question_no") or question.get("seq_no"))
        seq = f" 题号{seq_no}" if seq_no else ""
        lines.append(f"{index}. {subject} / {book} P{page}{seq}｜{chapter}｜{status}")
    extra = len(questions) - max_items
    if extra > 0:
        lines.append(f"- 还有 {extra} 道题没有展开，打开做题集查看完整批次。")
    return lines


def reminder_link_lines(app_url: str, practice_url: str = "", question_count: int = 0) -> list[str]:
    if is_private_app_url(app_url):
        return [
            "链接提示：当前公网地址是本地/内网地址，手机微信里通常打不开回填页面。",
            f"请在运行 Sakura 的电脑浏览器打开：{app_url}",
        ]
    lines = []
    if practice_url:
        lines.append(f"[手机快速回填本批次 {question_count} 道题]({practice_url})")
    lines.append(f"[打开完整 Sakura 做题集]({app_url})")
    return lines


def send_pushplus(token: str, title: str, content: str, template: str = "markdown") -> dict:
    if not token:
        return {"ok": False, "channel": "pushplus", "error": "未配置 PUSHPLUS_TOKEN，无法推送到微信。"}
    payload = json.dumps(
        {"token": token, "title": title, "content": content, "template": template},
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(PUSHPLUS_URL, data=payload, headers={"Content-Type": "application/json"})
    try:
        resp = json.loads(urllib.request.urlopen(req, timeout=15).read().decode("utf-8"))
        return {"ok": resp.get("code") == 200, "channel": "pushplus", "resp": resp}
    except Exception as exc:
        traceback.print_exc()
        return {"ok": False, "channel": "pushplus", "error": str(exc)}


def send_wework_bot(webhook: str, title: str, content: str) -> dict:
    if not webhook:
        return {"ok": False, "channel": "wework", "error": "WEWORK_BOT_WEBHOOK is not configured."}
    markdown = f"### {title}\n\n{content}".strip()
    payload = json.dumps(
        {"msgtype": "markdown", "markdown": {"content": markdown}},
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        webhook,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        resp = json.loads(urllib.request.urlopen(req, timeout=15).read().decode("utf-8"))
        return {"ok": resp.get("errcode") == 0, "channel": "wework", "resp": resp}
    except Exception as exc:
        traceback.print_exc()
        return {"ok": False, "channel": "wework", "error": str(exc)}


def wework_webhook_key(webhook: str) -> str:
    parsed = urlparse(str(webhook or ""))
    return (parse_qs(parsed.query).get("key") or [""])[0]


def send_wework_file(webhook: str, filename: str, file_bytes: bytes) -> dict:
    if not webhook:
        return {"ok": False, "channel": "wework_file", "error": "WEWORK_BOT_WEBHOOK is not configured."}
    key = wework_webhook_key(webhook)
    if not key:
        return {"ok": False, "channel": "wework_file", "error": "Enterprise WeChat webhook key is missing."}
    if not file_bytes:
        return {"ok": False, "channel": "wework_file", "error": "PDF file is empty."}
    if len(file_bytes) > WEWORK_FILE_LIMIT_BYTES:
        return {
            "ok": False,
            "channel": "wework_file",
            "error": f"PDF is too large for Enterprise WeChat robot file upload: {len(file_bytes)} bytes.",
        }

    boundary = f"sakura-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    safe_name = filename.replace("\\", "_").replace("/", "_") or "sakura-practice.pdf"
    head = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="media"; filename="{safe_name}"\r\n'
        "Content-Type: application/pdf\r\n\r\n"
    ).encode("utf-8")
    tail = f"\r\n--{boundary}--\r\n".encode("utf-8")
    upload_payload = head + file_bytes + tail
    upload_req = urllib.request.Request(
        f"{WEWORK_UPLOAD_URL}?key={key}&type=file",
        data=upload_payload,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        upload_resp = json.loads(urllib.request.urlopen(upload_req, timeout=30).read().decode("utf-8"))
        media_id = upload_resp.get("media_id")
        if upload_resp.get("errcode") != 0 or not media_id:
            return {"ok": False, "channel": "wework_file", "resp": upload_resp}
        payload = json.dumps(
            {"msgtype": "file", "file": {"media_id": media_id}},
            ensure_ascii=False,
        ).encode("utf-8")
        send_req = urllib.request.Request(
            webhook,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        send_resp = json.loads(urllib.request.urlopen(send_req, timeout=15).read().decode("utf-8"))
        return {
            "ok": send_resp.get("errcode") == 0,
            "channel": "wework_file",
            "filename": safe_name,
            "bytes": len(file_bytes),
            "upload": upload_resp,
            "resp": send_resp,
        }
    except Exception as exc:
        traceback.print_exc()
        return {"ok": False, "channel": "wework_file", "error": str(exc)}


def send_practice_pdf_if_available(
    reminder: dict,
    mode: str,
    *,
    send_pdf_enabled: str,
    connect: Callable,
    build_practice_batch_pdf: Callable,
    wework_webhook: str,
    current_email_settings: Callable[[], sakura_email.EmailSettings],
) -> dict | None:
    if send_pdf_enabled != "1":
        return {"ok": True, "channel": "practice_pdf", "skipped": True, "detail": "PDF sending is disabled."}
    if mode not in {"wework", "email", "local"}:
        return None
    batch_id = reminder.get("batch_id")
    if not batch_id:
        return None
    try:
        with connect() as conn:
            pdf_bytes, count = build_practice_batch_pdf(conn, batch_id)
        if count <= 0:
            return {"ok": True, "channel": "practice_pdf", "skipped": True, "detail": "本次复习包没有匹配题目，未生成 PDF。"}
        filename = f"sakura_daily_{date.today().isoformat()}_{count}q.pdf"
        results = []
        if mode in {"wework", "local"} and wework_webhook:
            results.append(send_wework_file(wework_webhook, filename, pdf_bytes))
        if mode in {"email", "local"}:
            email_settings = current_email_settings()
            if sakura_email.is_configured(email_settings):
                results.append(
                    sakura_email.send_email(
                        email_settings,
                        f"今日错题 PDF | {count} 道",
                        "今日错题 PDF 已生成，附件中可直接查看或打印。",
                        attachments=[(filename, pdf_bytes, "application/pdf")],
                    )
                )
        if not results:
            return {"ok": False, "channel": "practice_pdf", "error": "No file-capable channel is configured."}
        return {
            "ok": any(item.get("ok") for item in results),
            "channel": "practice_pdf",
            "filename": filename,
            "bytes": len(pdf_bytes),
            "results": results,
        }
    except Exception as exc:
        traceback.print_exc()
        return {"ok": False, "channel": "practice_pdf", "error": str(exc)}


def send_notification(
    title: str,
    content: str,
    *,
    wework_webhook: str = "",
    pushplus_token: str = "",
    email_settings: sakura_email.EmailSettings | None = None,
) -> dict:
    results = []
    if wework_webhook:
        results.append(send_wework_bot(wework_webhook, title, content))
    if pushplus_token:
        results.append(send_pushplus(pushplus_token, title, content))
    if email_settings and sakura_email.is_configured(email_settings):
        results.append(sakura_email.send_email(email_settings, title, content))
    if not results:
        return {
            "ok": False,
            "configured": False,
            "detail": "No notification channel configured. Set WEWORK_BOT_WEBHOOK, PUSHPLUS_TOKEN or EMAIL_*.",
            "results": [],
        }
    return {
        "ok": any(item.get("ok") for item in results),
        "configured": True,
        "results": results,
        "detail": results,
    }


def send_notification_for_mode(
    title: str,
    content: str,
    mode: str | None,
    *,
    wework_webhook: str,
    pushplus_token: str,
    email_settings: sakura_email.EmailSettings,
) -> dict:
    selected_mode = sakura_reminders.normalize_checkin_mode(mode or "wework")
    if selected_mode == "wework":
        if not wework_webhook:
            result = {
                "ok": False,
                "configured": False,
                "detail": "未配置企业微信机器人 Webhook。",
                "results": [],
            }
        else:
            result = send_notification(title, content, wework_webhook=wework_webhook)
    elif selected_mode == "pushplus":
        if not pushplus_token:
            result = {
                "ok": False,
                "configured": False,
                "detail": "未配置 PushPlus Token。",
                "results": [],
            }
        else:
            result = send_notification(title, content, pushplus_token=pushplus_token)
    elif selected_mode == "email":
        if not sakura_email.is_configured(email_settings):
            result = {
                "ok": False,
                "configured": False,
                "detail": "未配置邮箱 SMTP。",
                "results": [],
            }
        else:
            result = send_notification(title, content, email_settings=email_settings)
    else:
        result = send_notification(
            title,
            content,
            wework_webhook=wework_webhook,
            pushplus_token=pushplus_token,
            email_settings=email_settings,
        )
    result["selected_channel"] = selected_mode
    return result


def today_quote(quotes: list[str], day: date | None = None) -> str:
    day = day or date.today()
    return quotes[day.toordinal() % len(quotes)] if quotes else ""


def is_checked_in(conn, day: date | None = None) -> bool:
    day = day or date.today()
    row = conn.execute("SELECT 1 FROM checkins WHERE day = ?", (day.isoformat(),)).fetchone()
    return row is not None


def mark_checkin(conn, day: date | None = None) -> None:
    day = day or date.today()
    conn.execute(
        "INSERT OR IGNORE INTO checkins (day, created_at) VALUES (?, ?)",
        (day.isoformat(), datetime.now().isoformat(timespec="seconds")),
    )


def weather_city_from_state(state: dict, default_city: str, fallback: str = "北京") -> str:
    return (state.get("weather_city") or default_city or fallback).strip()


def build_daily_reminder(
    conn,
    *,
    today: date,
    backlog: dict,
    state: dict,
    parse_exam_date: Callable[[str | None], date],
    create_practice_batch: Callable,
    app_public_url: str,
) -> dict:
    """Build the daily wrong-question reminder markdown payload."""
    exam = parse_exam_date(state.get("exam_date"))
    days_left = (exam - today).days
    due_total = backlog["overdue"] + backlog["due_today"]
    batch = create_practice_batch(conn, "daily_push")
    app_url = app_public_url.rstrip("/")
    practice_url = f"{app_url}/practice/{batch['id']}"

    rows = conn.execute(
        """
        SELECT d.subject, COALESCE(NULLIF(d.title, ''), d.filename) book, COUNT(*) n
        FROM questions q
        JOIN documents d ON d.id = q.document_id
        WHERE q.status IN ('\u505a\u9519', '\u9700\u590d\u4e60', '\u534a\u4f1a')
           OR (q.ever_wrong = 1 AND q.mastered_at IS NULL
               AND q.next_review_at IS NOT NULL AND date(q.next_review_at) <= date(?))
        GROUP BY d.subject, book
        ORDER BY n DESC
        LIMIT 8
        """,
        (today.isoformat(),),
    ).fetchall()

    title = f"\u4eca\u65e5\u9519\u9898\u590d\u4e60 | \u5f85\u590d\u4e60 {due_total} \u9053 | \u8ddd\u8003\u8bd5 {days_left} \u5929"
    lines = [
        "### \u4eca\u65e5\u9519\u9898\u590d\u4e60\u63d0\u9192",
        f"- \u4eca\u5929\uff1a{today.month}\u6708{today.day}\u65e5\uff0c\u8ddd\u8003\u8bd5\u8fd8\u6709 **{days_left}** \u5929",
        f"- \u5230\u671f\u5f85\u590d\u4e60\uff1a**{due_total}** \u9053\uff08\u903e\u671f {backlog['overdue']} + \u4eca\u65e5 {backlog['due_today']}\uff09",
        f"- \u5728\u7ec3\u9519\u9898\u603b\u6570\uff1a{backlog['active_wrong']} \u9053",
        "",
    ]
    if rows:
        lines.append("**\u6309\u8d44\u6599\u5206\u5e03\uff1a**")
        for row in rows:
            subject = row["subject"] or "\u672a\u5206\u79d1\u76ee"
            lines.append(f"- {subject} / {row['book']}\uff1a{row['n']} \u9053")
    else:
        lines.append("\u4eca\u5929\u6ca1\u6709\u5230\u671f\u7684\u9519\u9898\uff0c\u4fdd\u6301\u8282\u594f\uff0c\u53ef\u4ee5\u9884\u4e60\u65b0\u5185\u5bb9\u3002")
    lines.append("")
    lines.append("**\u4eca\u65e5\u63a8\u9001\u9898\u76ee\uff1a**")
    lines.extend(question_summary_lines(batch))
    lines.append("")
    lines.extend(reminder_link_lines(app_url, practice_url, batch["question_count"]))
    return {
        "title": title,
        "content": "\n".join(lines),
        "due_total": due_total,
        "days_left": days_left,
        "batch_id": batch["id"],
        "practice_url": practice_url,
    }


def build_weather_reminder(city: str, *, fetch_weather: Callable[[str], dict], app_public_url: str) -> dict:
    info = fetch_weather(city)
    display_city = info["resolved_city"] or city
    title = f"明天天气提醒 | {display_city}"

    def show(value) -> str:
        # Weather providers can return null for some fields (e.g. precipitation_probability_max);
        # render a dash instead of the literal string "None" in the pushed reminder.
        return "-" if value is None or value == "" else str(value)

    lines = [
        f"### 明天天气提醒：{display_city}",
        f"- 日期：**{show(info['date'])}**",
        f"- 天气：**{show(info['weather_text'])}**",
        f"- 温度：**{show(info['temp_min'])}°C ~ {show(info['temp_max'])}°C**",
        f"- 降水概率：**{show(info['rain_probability'])}%**",
        f"- 最大风速：**{show(info['wind_max'])} km/h**",
        "",
        "晚上提前看一下天气，第二天出门少一点临时慌张。",
        f"[打开 Sakura 做题集]({app_public_url.rstrip('/')})",
    ]
    return {"title": title, "content": "\n".join(lines), "weather": info}


def build_morning_reminder(base: dict, *, quote: str, app_public_url: str) -> dict:
    checkin_url = f"{app_public_url.rstrip('/')}/api/today/done"
    content = (
        f"> 「{quote}」\n\n"
        f"{base['content']}\n\n"
        f"---\n"
        f"做完今天的复习了吗？点这里打卡：\n"
        f"[我已完成]({checkin_url})\n\n"
        f"（晚上会检查；没打卡的话，会提醒你补上。）"
    )
    return {
        "title": f"早安 | {base['title']}",
        "content": content,
        "due_total": base["due_total"],
        "batch_id": base.get("batch_id", ""),
        "practice_url": base.get("practice_url", ""),
    }


def build_night_check(
    *,
    checked_in: bool,
    quote: str,
    nag: str,
    backlog: dict,
    app_public_url: str,
) -> dict:
    app_url = app_public_url.rstrip("/")
    if checked_in:
        return {
            "skip": False,
            "title": "今日已完成 | 干得漂亮",
            "content": f"> 「{quote}」\n\n今天的复习已打卡完成。早点休息，明天继续保持节奏。",
        }
    due_total = backlog["overdue"] + backlog["due_today"]
    content = (
        f"### 今日未打卡\n\n"
        f"{nag}\n\n"
        f"- 还有 **{due_total}** 道到期错题等着你\n"
        f"[现在去做]({app_url}) | 做完点 [我已完成]({app_url}/api/today/done)"
    )
    return {"skip": False, "title": "今天还没打卡，别装看不见", "content": content}
