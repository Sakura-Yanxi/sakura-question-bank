from __future__ import annotations

import json
import sqlite3
import time
import traceback
from datetime import datetime
from typing import Callable


def reminder_kinds_for_minute(minute: str, schedules: list[tuple[str, str, str]]) -> list[str]:
    return [kind for kind, enabled, target_minute in schedules if enabled == "1" and target_minute == minute]


def scheduled_reminder_kinds(now: datetime | None, schedules: list[tuple[str, str, str]]) -> list[str]:
    now = now or datetime.now()
    return reminder_kinds_for_minute(now.strftime("%H:%M"), schedules)


def claim_reminder_dispatch(conn: sqlite3.Connection, kind: str, now: datetime) -> bool:
    day = now.date().isoformat()
    minute_key = now.strftime("%Y-%m-%d %H:%M")
    stamp = now.isoformat(timespec="seconds")
    try:
        conn.execute(
            """
            INSERT INTO reminder_dispatch_log (day, kind, minute_key, status, detail_json, created_at, updated_at)
            VALUES (?, ?, ?, 'running', '{}', ?, ?)
            """,
            (day, kind, minute_key, stamp, stamp),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def finish_reminder_dispatch(conn: sqlite3.Connection, kind: str, now: datetime, status: str, detail: dict) -> None:
    conn.execute(
        """
        UPDATE reminder_dispatch_log
        SET status = ?, detail_json = ?, updated_at = ?
        WHERE day = ? AND kind = ? AND minute_key = ?
        """,
        (
            status,
            json.dumps(detail, ensure_ascii=False, default=str)[:4000],
            datetime.now().isoformat(timespec="seconds"),
            now.date().isoformat(),
            kind,
            now.strftime("%Y-%m-%d %H:%M"),
        ),
    )
    conn.commit()


def dispatch_scheduled_reminder(
    kind: str,
    *,
    mode: str | None,
    default_mode: str,
    connect: Callable[[], sqlite3.Connection],
    build_payload: Callable[[sqlite3.Connection, str], dict],
    send_payload: Callable[[dict, str, bool], tuple[dict, dict | None]],
    channels_configured: Callable[[str], bool],
    response_detail: Callable[[dict], object],
    response_configured: Callable[[dict, str], bool],
    print_exception: Callable[[], None] = traceback.print_exc,
) -> dict:
    selected_mode = mode or default_mode
    now = datetime.now()
    conn = connect()
    try:
        if not claim_reminder_dispatch(conn, kind, now):
            return {"ok": True, "skipped": True, "kind": kind, "detail": "already dispatched for this minute"}
        try:
            payload = build_payload(conn, kind)
            conn.commit()
            attach_pdf = kind in {"daily", "morning"}
            result, _ = send_payload(payload, selected_mode, attach_pdf)
        except Exception as exc:
            print_exception()
            result = {
                "ok": False,
                "selected_channel": selected_mode,
                "detail": str(exc),
                "configured": channels_configured(selected_mode),
            }
            payload = {"title": f"{kind} reminder failed"}
        finish_reminder_dispatch(
            conn,
            kind,
            now,
            "sent" if result.get("ok") else "failed",
            {"title": payload.get("title"), "result": result},
        )
    finally:
        conn.close()
    selected_channel = result.get("selected_channel", selected_mode)
    return {
        "ok": bool(result.get("ok")),
        "kind": kind,
        "selected_channel": selected_channel,
        "title": payload.get("title", ""),
        "detail": response_detail(result),
        "configured": response_configured(result, selected_channel),
    }


def reminder_scheduler_loop(
    *,
    enabled: Callable[[], bool],
    scheduled_kinds: Callable[[datetime], list[str]],
    dispatch: Callable[[str], dict],
    poll_seconds: int,
    print_func: Callable[..., None] = print,
    print_exception: Callable[[], None] = traceback.print_exc,
    sleep: Callable[[float], None] = time.sleep,
    now_factory: Callable[[], datetime] = datetime.now,
) -> None:
    print_func("[sakura scheduler] internal reminder scheduler started", flush=True)
    while True:
        try:
            if enabled():
                for kind in scheduled_kinds(now_factory()):
                    result = dispatch(kind)
                    print_func(f"[sakura scheduler] {kind}: {result}", flush=True)
        except Exception:
            print_exception()
        sleep(poll_seconds)

