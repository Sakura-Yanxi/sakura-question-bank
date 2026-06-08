from __future__ import annotations

import json
import re
from datetime import datetime, timedelta


PASSWORD_MIN_LENGTH = 12
LOCK_THRESHOLD = 5
WINDOW_SECONDS = 60
LOCK_DURATIONS = [300, 600, 3600, 365 * 24 * 3600]


def utcnow() -> datetime:
    return datetime.now()


def iso(dt: datetime | None) -> str:
    return dt.isoformat(timespec="seconds") if dt else ""


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def duration_label(seconds: int) -> str:
    if seconds >= 365 * 24 * 3600:
        return "1 年"
    if seconds >= 3600:
        return f"{seconds // 3600} 小时"
    return f"{seconds // 60} 分钟"


def password_policy_view() -> dict:
    return {
        "min_length": PASSWORD_MIN_LENGTH,
        "requires": ["字母", "数字", "特殊字符"],
        "lock_threshold": LOCK_THRESHOLD,
        "window_seconds": WINDOW_SECONDS,
        "lock_steps": [duration_label(item) for item in LOCK_DURATIONS],
    }


def validate_admin_password(password: str) -> list[str]:
    errors = []
    if len(password) < PASSWORD_MIN_LENGTH:
        errors.append(f"密码至少 {PASSWORD_MIN_LENGTH} 位。")
    if not re.search(r"[A-Za-z]", password):
        errors.append("密码必须包含字母。")
    if not re.search(r"\d", password):
        errors.append("密码必须包含数字。")
    if not re.search(r"[^A-Za-z0-9\s]", password):
        errors.append("密码必须包含特殊字符。")
    if re.search(r"\s", password):
        errors.append("密码不能包含空格或换行。")
    return errors


def client_ip(headers, client_address) -> str:
    for key in ("CF-Connecting-IP", "X-Real-IP", "X-Forwarded-For"):
        value = headers.get(key)
        if not value:
            continue
        first = value.split(",", 1)[0].strip()
        if first:
            return first[:80]
    if client_address:
        return str(client_address[0])[:80]
    return "unknown"


def user_agent(headers) -> str:
    return (headers.get("User-Agent") or "").strip()[:500]


def security_settings_view(admin_password: str) -> dict:
    return {
        "auth_enabled": bool(admin_password),
        "password_configured": bool(admin_password),
        "policy": password_policy_view(),
    }


def recent_security_events(conn, limit: int = 8) -> list[dict]:
    rows = conn.execute(
        """
        SELECT ip, event_type, detail_json, created_at
        FROM login_security_events
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (max(1, min(int(limit or 8), 30)),),
    ).fetchall()
    items = []
    for row in rows:
        detail = {}
        try:
            detail = json.loads(row["detail_json"] or "{}")
        except json.JSONDecodeError:
            detail = {}
        items.append({
            "ip": row["ip"],
            "event_type": row["event_type"],
            "detail": detail,
            "created_at": row["created_at"],
        })
    return items


def record_security_event(conn, ip: str, user_agent_value: str, event_type: str, detail: dict | None = None, now: datetime | None = None) -> None:
    created = iso(now or utcnow())
    payload = {
        **(detail or {}),
        "user_agent": user_agent_value[:240],
    }
    conn.execute(
        """
        INSERT INTO login_security_events (ip, user_agent, event_type, detail_json, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (ip, user_agent_value[:500], event_type[:40], json.dumps(payload, ensure_ascii=False), created),
    )


def current_lock(conn, ip: str, now: datetime | None = None) -> dict:
    now = now or utcnow()
    row = conn.execute("SELECT * FROM login_rate_limits WHERE ip = ?", (ip,)).fetchone()
    if not row:
        return {"locked": False, "remaining_seconds": 0, "locked_until": "", "lock_level": 0}
    locked_until = parse_iso(row["locked_until"])
    if locked_until and locked_until > now:
        remaining = max(1, int((locked_until - now).total_seconds()))
        return {
            "locked": True,
            "remaining_seconds": remaining,
            "locked_until": iso(locked_until),
            "lock_level": row["lock_level"] or 0,
        }
    return {"locked": False, "remaining_seconds": 0, "locked_until": "", "lock_level": row["lock_level"] or 0}


def record_login_success(conn, ip: str, user_agent_value: str) -> None:
    now = utcnow()
    conn.execute("DELETE FROM login_rate_limits WHERE ip = ?", (ip,))
    record_security_event(conn, ip, user_agent_value, "login_success", {}, now)


def record_login_failure(conn, ip: str, user_agent_value: str) -> dict:
    now = utcnow()
    locked = current_lock(conn, ip, now)
    if locked["locked"]:
        record_security_event(conn, ip, user_agent_value, "login_blocked", locked, now)
        return {
            **locked,
            "alert": False,
            "fail_count": LOCK_THRESHOLD,
            "remaining_attempts": 0,
        }

    row = conn.execute("SELECT * FROM login_rate_limits WHERE ip = ?", (ip,)).fetchone()
    if row:
        window_started = parse_iso(row["window_started_at"]) or now
        lock_level = int(row["lock_level"] or 0)
        fail_count = int(row["fail_count"] or 0)
        if (now - window_started).total_seconds() > WINDOW_SECONDS:
            window_started = now
            fail_count = 0
    else:
        window_started = now
        lock_level = 0
        fail_count = 0

    fail_count += 1
    if fail_count >= LOCK_THRESHOLD:
        next_level = lock_level + 1
        duration = LOCK_DURATIONS[min(next_level - 1, len(LOCK_DURATIONS) - 1)]
        locked_until = now + timedelta(seconds=duration)
        conn.execute(
            """
            INSERT INTO login_rate_limits(ip, fail_count, window_started_at, locked_until, lock_level, last_failed_at, user_agent)
            VALUES (?, 0, ?, ?, ?, ?, ?)
            ON CONFLICT(ip) DO UPDATE SET
                fail_count = excluded.fail_count,
                window_started_at = excluded.window_started_at,
                locked_until = excluded.locked_until,
                lock_level = excluded.lock_level,
                last_failed_at = excluded.last_failed_at,
                user_agent = excluded.user_agent
            """,
            (ip, iso(now), iso(locked_until), next_level, iso(now), user_agent_value[:500]),
        )
        result = {
            "locked": True,
            "remaining_seconds": duration,
            "locked_until": iso(locked_until),
            "lock_level": next_level,
            "lock_duration": duration_label(duration),
            "alert": True,
            "fail_count": LOCK_THRESHOLD,
            "remaining_attempts": 0,
        }
        record_security_event(conn, ip, user_agent_value, "login_locked", result, now)
        return result

    conn.execute(
        """
        INSERT INTO login_rate_limits(ip, fail_count, window_started_at, locked_until, lock_level, last_failed_at, user_agent)
        VALUES (?, ?, ?, '', ?, ?, ?)
        ON CONFLICT(ip) DO UPDATE SET
            fail_count = excluded.fail_count,
            window_started_at = excluded.window_started_at,
            locked_until = excluded.locked_until,
            lock_level = excluded.lock_level,
            last_failed_at = excluded.last_failed_at,
            user_agent = excluded.user_agent
        """,
        (ip, fail_count, iso(window_started), lock_level, iso(now), user_agent_value[:500]),
    )
    result = {
        "locked": False,
        "remaining_seconds": 0,
        "locked_until": "",
        "lock_level": lock_level,
        "alert": False,
        "fail_count": fail_count,
        "remaining_attempts": max(0, LOCK_THRESHOLD - fail_count),
    }
    record_security_event(conn, ip, user_agent_value, "login_failed", result, now)
    return result


def login_failure_message(result: dict) -> str:
    if result.get("locked"):
        return f"登录失败次数过多，当前来源已锁定到 {result.get('locked_until')}。"
    remaining = result.get("remaining_attempts", 0)
    return f"密码不正确，请重新输入。1 分钟内还可尝试 {remaining} 次。"
