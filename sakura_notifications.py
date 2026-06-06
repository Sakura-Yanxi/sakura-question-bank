from __future__ import annotations

import json
import traceback
import urllib.request


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


def send_notification(title: str, content: str, *, wework_webhook: str = "", pushplus_token: str = "") -> dict:
    results = []
    if wework_webhook:
        results.append(send_wework_bot(wework_webhook, title, content))
    if pushplus_token:
        results.append(send_pushplus(pushplus_token, title, content))
    if not results:
        return {
            "ok": False,
            "configured": False,
            "detail": "No notification channel configured. Set WEWORK_BOT_WEBHOOK or PUSHPLUS_TOKEN.",
            "results": [],
        }
    return {
        "ok": any(item.get("ok") for item in results),
        "configured": True,
        "results": results,
        "detail": results,
    }
