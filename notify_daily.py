# -*- coding: utf-8 -*-
"""
每日错题复习微信提醒（PushPlus）。

用途：定时触发，把"今日待复习错题 + 倒计时"推送到微信。
适合放进青龙面板、系统 crontab、或 Windows 计划任务里定时跑。

依赖：仅 Python 标准库，无需 pip install。

用法：
    # 方式一（推荐）：调用正在运行的做题集服务（需先 python app.py）
    APP_PUBLIC_URL=http://127.0.0.1:8000 python notify_daily.py

    # 方式二：服务没在跑时，直接读本地数据库生成并推送（需 PUSHPLUS_TOKEN）
    PUSHPLUS_TOKEN=你的token python notify_daily.py --local

青龙面板：
    1. 「环境变量」里加 PUSHPLUS_TOKEN（和 APP_PUBLIC_URL，可选）。
    2. 「定时任务」新建：命令 `task notify_daily.py`，cron 例如 `0 8 * * *`（每天 8:00）。
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
    """让正在运行的服务自己汇总并推送。"""
    req = urllib.request.Request(f"{APP_PUBLIC_URL.rstrip('/')}{ENDPOINTS[mode]}", data=b"{}",
                                 method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def via_local(mode: str) -> dict:
    """服务没在跑时，直接 import app 读库并推送。"""
    import app
    app.init_db()
    with app.connect() as conn:
        if mode == "morning":
            payload = app.build_morning_reminder(conn)
        elif mode == "night":
            payload = app.build_night_check(conn)
        elif mode == "weather":
            payload = app.build_weather_reminder(conn)
        else:
            payload = app.build_daily_reminder(conn)
    result = app.send_notification(payload["title"], payload["content"])
    return {"ok": result["ok"], "title": payload["title"], "detail": result.get("detail") or result.get("resp") or result.get("error")}


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
