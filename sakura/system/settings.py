from __future__ import annotations

import re
from urllib.parse import urlparse

from sakura.system import email as sakura_email
from sakura.system import reminders as sakura_reminders


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


def llm_settings_view(
    api_key: str,
    base_url: str,
    model: str,
    vision_model: str = "",
    vision_api_key: str = "",
    vision_base_url: str = "",
) -> dict:
    # Vision is usable once a model name is set AND a key is available — either its own, or the
    # text model's key it falls back to.
    effective_vision_key = vision_api_key or api_key
    return {
        "has_key": bool(api_key),
        "masked_key": mask_secret(api_key),
        "base_url": base_url,
        "model": model,
        "vision_model": vision_model or "",
        "vision_has_key": bool(vision_api_key),
        "vision_masked_key": mask_secret(vision_api_key),
        "vision_base_url": vision_base_url or "",
        "vision_enabled": bool(vision_model and effective_vision_key),
        "key_env": "LLM_API_KEY" if api_key else "",
    }


def llm_runtime_updates(
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    vision_model: str | None = None,
    vision_api_key: str | None = None,
    vision_base_url: str | None = None,
) -> dict[str, str]:
    updates: dict[str, str] = {}
    if api_key is not None and api_key.strip():
        updates["LLM_API_KEY"] = api_key.strip()
    if base_url is not None and base_url.strip():
        updates["LLM_BASE_URL"] = base_url.strip().rstrip("/")
    if model is not None and model.strip():
        updates["LLM_MODEL"] = model.strip()
    # Vision fields are intentionally clearable: empty model disables image reading,
    # empty key/base_url falls back to the text model settings.
    if vision_model is not None:
        updates["LLM_VISION_MODEL"] = vision_model.strip()
    if vision_api_key is not None:
        updates["LLM_VISION_API_KEY"] = vision_api_key.strip()
    if vision_base_url is not None:
        updates["LLM_VISION_BASE_URL"] = vision_base_url.strip().rstrip("/")
    return updates


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


def notification_runtime_updates(
    *,
    wework_webhook: str | None = None,
    pushplus_token: str | None = None,
    app_public_url: str | None = None,
    email_enabled: str | None = None,
    email_host: str | None = None,
    email_port: str | None = None,
    email_use_ssl: str | None = None,
    email_use_starttls: str | None = None,
    email_user: str | None = None,
    email_password: str | None = None,
    email_to: str | None = None,
    email_from: str | None = None,
    email_from_name: str | None = None,
    current_email_port: str = "465",
    current_email_use_ssl: str = "1",
    current_email_use_starttls: str = "0",
) -> dict[str, str]:
    updates: dict[str, str] = {}
    if wework_webhook is not None and wework_webhook.strip():
        updates["WEWORK_BOT_WEBHOOK"] = wework_webhook.strip()
    if pushplus_token is not None and pushplus_token.strip():
        updates["PUSHPLUS_TOKEN"] = pushplus_token.strip()
    if app_public_url is not None and app_public_url.strip():
        updates["APP_PUBLIC_URL"] = app_public_url.strip().rstrip("/")
    if email_enabled is not None and email_enabled.strip():
        updates["EMAIL_ENABLED"] = sakura_email.normalize_onoff(email_enabled)
    if email_host is not None and email_host.strip():
        updates["EMAIL_HOST"] = email_host.strip()
    if email_port is not None and email_port.strip():
        updates["EMAIL_PORT"] = sakura_email.normalize_port(email_port, current_email_port)
    if email_use_ssl is not None and email_use_ssl.strip():
        updates["EMAIL_USE_SSL"] = sakura_email.normalize_onoff(email_use_ssl, current_email_use_ssl)
    if email_use_starttls is not None and email_use_starttls.strip():
        updates["EMAIL_USE_STARTTLS"] = sakura_email.normalize_onoff(email_use_starttls, current_email_use_starttls)
    if email_user is not None and email_user.strip():
        updates["EMAIL_USER"] = email_user.strip()
    if email_password is not None and email_password.strip():
        updates["EMAIL_PASSWORD"] = email_password.strip()
    if email_to is not None and email_to.strip():
        updates["EMAIL_TO"] = email_to.strip()
    if email_from is not None and email_from.strip():
        updates["EMAIL_FROM"] = email_from.strip()
    if email_from_name is not None and email_from_name.strip():
        updates["EMAIL_FROM_NAME"] = email_from_name.strip()
    return updates


def reminder_settings_from_values(
    *,
    morning_on: str,
    morning_time: str,
    night_on: str,
    night_time: str,
    weather_on: str,
    weather_time: str,
    checkin_mode: str,
    daily_scope: str,
    daily_limit: str,
    send_pdf: str,
) -> sakura_reminders.ReminderSettings:
    return sakura_reminders.ReminderSettings(
        morning_on=morning_on,
        morning_time=morning_time,
        night_on=night_on,
        night_time=night_time,
        weather_on=weather_on,
        weather_time=weather_time,
        checkin_mode=checkin_mode,
        daily_scope=daily_scope,
        daily_limit=daily_limit,
        send_pdf=send_pdf,
    )


def reminder_settings_view(
    settings: sakura_reminders.ReminderSettings,
    cron_status: dict | None = None,
    scheduler: dict | None = None,
) -> dict:
    payload = settings.as_payload(cron_status)
    if scheduler is not None:
        payload["scheduler"] = scheduler
    return payload


def reminder_runtime_updates(
    current: sakura_reminders.ReminderSettings,
    payload: dict,
) -> tuple[sakura_reminders.ReminderSettings, dict[str, str]]:
    settings = sakura_reminders.merge_settings(current, payload)
    return settings, settings.as_env()


def normalize_public_url(value: str) -> str:
    clean = value.strip().rstrip("/")
    parsed = urlparse(clean)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("公网地址必须是完整 URL，例如：https://your-domain.example")
    return clean
