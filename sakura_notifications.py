from __future__ import annotations

import json
import traceback
import urllib.request
from datetime import date, datetime
from typing import Callable

import sakura_email


PUSHPLUS_URL = "https://www.pushplus.plus/send"


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
        WHERE q.status IN ('做错', '需复习', '半会')
           OR (q.ever_wrong = 1 AND q.mastered_at IS NULL
               AND q.next_review_at IS NOT NULL AND date(q.next_review_at) <= date(?))
        GROUP BY d.subject, book
        ORDER BY n DESC
        LIMIT 8
        """,
        (today.isoformat(),),
    ).fetchall()

    title = f"今日错题复习 | 待复习 {due_total} 道 | 距考试 {days_left} 天"
    lines = [
        "### 今日错题复习提醒",
        f"- 今天：{today.month}月{today.day}日，距考试还有 **{days_left}** 天",
        f"- 到期待复习：**{due_total}** 道（逾期 {backlog['overdue']} + 今日 {backlog['due_today']}）",
        f"- 在练错题总数：{backlog['active_wrong']} 道",
        "",
    ]
    if rows:
        lines.append("**按资料分布：**")
        for row in rows:
            lines.append(f"- {row['subject'] or '未分类'} / {row['book']}：{row['n']} 道")
    else:
        lines.append("今天没有到期的错题，保持节奏，可以预习新内容。")
    lines.append("")
    lines.append(f"[手机快速回填本批次 {batch['question_count']} 道题]({practice_url})")
    lines.append(f"[打开完整 Sakura 做题集]({app_url})")
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
    lines = [
        f"### 明天天气提醒：{display_city}",
        f"- 日期：**{info['date']}**",
        f"- 天气：**{info['weather_text']}**",
        f"- 温度：**{info['temp_min']}°C ~ {info['temp_max']}°C**",
        f"- 降水概率：**{info['rain_probability']}%**",
        f"- 最大风速：**{info['wind_max']} km/h**",
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
