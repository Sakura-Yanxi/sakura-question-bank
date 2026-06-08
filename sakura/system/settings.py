from __future__ import annotations

import re
from urllib.parse import urlparse


def mask_secret(value: str) -> str:
    value = value or ""
    if not value:
        return ""
    keep = 4 if len(value) <= 12 else 8
    return value[:keep] + "xxxx"


def mask_public_url(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    parsed = urlparse(value)
    if parsed.scheme and parsed.netloc:
        host = parsed.netloc
        if re.match(r"^\d+\.\d+\.", host):
            parts = host.split(".")
            return f"{parsed.scheme}://{parts[0]}.{parts[1]}.xxxx"
        keep = min(len(host), 6 if re.match(r"^\d+\.\d+", host) else 10)
        return f"{parsed.scheme}://{host[:keep]}xxxx"
    return mask_secret(value)


def mask_email(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    if "@" not in value:
        return mask_secret(value)
    name, domain = value.split("@", 1)
    if len(name) <= 2:
        masked_name = name[:1] + "x"
    else:
        masked_name = name[:2] + "xxxx"
    return f"{masked_name}@{domain}"


def llm_settings_view(api_key: str, base_url: str, model: str) -> dict:
    return {
        "has_key": bool(api_key),
        "masked_key": mask_secret(api_key),
        "base_url": base_url,
        "model": model,
        "key_env": "LLM_API_KEY" if api_key else "",
    }


def notification_settings_view(
    wework_webhook: str,
    pushplus_token: str,
    app_public_url: str,
    email_settings: dict | None = None,
) -> dict:
    email_settings = email_settings or {}
    return {
        "has_wework": bool(wework_webhook),
        "masked_wework": mask_secret(wework_webhook),
        "has_pushplus": bool(pushplus_token),
        "masked_pushplus": mask_secret(pushplus_token),
        "app_public_url": "",
        "masked_app_public_url": mask_public_url(app_public_url),
        **email_settings,
    }


def normalize_public_url(value: str) -> str:
    clean = value.strip().rstrip("/")
    parsed = urlparse(clean)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("公网地址必须是完整 URL，例如：https://your-domain.example")
    return clean
