# -*- coding: utf-8 -*-
"""
Sakura reminder trigger helper.

Purpose:
    Trigger the running Sakura service to send morning, night, weather, or
    daily review notifications. The service decides the configured channel:
    Enterprise WeChat, PushPlus, email, or all local channels.

Dependencies:
    Python standard library only.

Usage:
    # Recommended: call the running Sakura service.
    APP_PUBLIC_URL=http://127.0.0.1:8000 python notify_daily.py

    # Trigger a specific reminder kind.
    python notify_daily.py --morning
    python notify_daily.py --night
    python notify_daily.py --weather

    # Fallback: import app.py locally and dispatch without HTTP.
    PUSHPLUS_TOKEN=你的token python notify_daily.py --local

Notes:
    On the server, the built-in Sakura scheduler is preferred. This helper is
    still useful for crontab, QingLong, or Windows Task Scheduler fallback jobs.
"""
import json
import os
import sys
import urllib.request

APP_PUBLIC_URL = os.getenv("APP_PUBLIC_URL", "http://127.0.0.1:8000")


ENDPOINTS = {
    "daily": "/api/push/daily",
    "morning": "/api/push/morning",
    "night": "/api/push/night",
    "weather": "/api/push/weather",
}


def via_server(mode: str) -> dict:
    """Ask the running Sakura service to build and send the reminder."""
    payload = json.dumps({"scheduled": True}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(f"{APP_PUBLIC_URL.rstrip('/')}{ENDPOINTS[mode]}", data=payload,
                                 method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def via_local(mode: str) -> dict:
    """Fallback path: import app.py and dispatch from local state."""
    import app
    app.init_db()
    return app.dispatch_scheduled_reminder(mode)


def main() -> None:
    args = sys.argv[1:]
    use_local = "--local" in args
    mode = "daily"
    if "--morning" in args:
        mode = "morning"
    elif "--night" in args:
        mode = "night"
    elif "--weather" in args:
        mode = "weather"
    try:
        result = via_local(mode) if use_local else via_server(mode)
    except Exception as exc:
        print(f"[notify_daily] 推送失败（{mode}）：{exc}")
        sys.exit(1)
    if result.get("ok"):
        print(f"[notify_daily] 已推送（{mode}）：{result.get('title')}")
    else:
        print(f"[notify_daily] 未推送（{mode}）：{result.get('detail') or result}")
        sys.exit(1)


if __name__ == "__main__":
    main()
