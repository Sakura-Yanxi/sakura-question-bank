from __future__ import annotations

import html
import re
import smtplib
import ssl
import traceback
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr


TRUE_VALUES = {"1", "true", "yes", "on", "ssl"}


@dataclass(frozen=True)
class EmailSettings:
    enabled: str = "0"
    host: str = ""
    port: str = "465"
    use_ssl: str = "1"
    use_starttls: str = "0"
    user: str = ""
    password: str = ""
    to: str = ""
    from_email: str = ""
    from_name: str = "Sakura 做题集"


def normalize_onoff(value: str | int | bool, default: str = "0") -> str:
    text = str(value).strip().lower()
    if text in TRUE_VALUES:
        return "1"
    if text in {"0", "false", "no", "off", "none", "plain"}:
        return "0"
    return default


def normalize_port(value: str | int, default: str = "465") -> str:
    try:
        port = int(str(value).strip())
    except ValueError:
        return default
    if 1 <= port <= 65535:
        return str(port)
    return default


def split_recipients(value: str) -> list[str]:
    parts = re.split(r"[,;\s]+", value or "")
    return [part.strip() for part in parts if part.strip()]


def is_configured(settings: EmailSettings) -> bool:
    return (
        normalize_onoff(settings.enabled) == "1"
        and bool(settings.host.strip())
        and bool(settings.user.strip())
        and bool(settings.password.strip())
        and bool(split_recipients(settings.to))
    )


def settings_public_view(settings: EmailSettings) -> dict:
    return {
        "email_enabled": normalize_onoff(settings.enabled),
        "email_host": settings.host,
        "email_port": normalize_port(settings.port),
        "email_use_ssl": normalize_onoff(settings.use_ssl, "1"),
        "email_use_starttls": normalize_onoff(settings.use_starttls),
        "email_from_name": settings.from_name,
        "has_email": is_configured(settings),
        "masked_email_user": mask_email(settings.user),
        "masked_email_to": mask_email_list(settings.to),
        "masked_email_from": mask_email(settings.from_email),
        "has_email_password": bool(settings.password),
    }


def mask_email(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    if "@" not in value:
        keep = 3 if len(value) <= 8 else 5
        return value[:keep] + "xxxx"
    name, domain = value.split("@", 1)
    if len(name) <= 2:
        masked_name = name[:1] + "x"
    else:
        masked_name = name[:2] + "xxxx"
    return f"{masked_name}@{domain}"


def mask_email_list(value: str) -> str:
    recipients = split_recipients(value)
    if not recipients:
        return ""
    masked = [mask_email(item) for item in recipients[:2]]
    if len(recipients) > 2:
        masked.append(f"+{len(recipients) - 2}")
    return ", ".join(masked)


def markdown_to_html(content: str) -> str:
    text = html.escape(content or "")
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(
        r"\[([^\]]+)\]\((https?://[^)]+)\)",
        r'<a href="\2">\1</a>',
        text,
    )
    paragraphs = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        if block.startswith("### "):
            paragraphs.append(f"<h3>{block[4:]}</h3>")
        else:
            paragraphs.append(f"<p>{block.replace(chr(10), '<br>')}</p>")
    return "\n".join(paragraphs)


def send_email(settings: EmailSettings, title: str, content: str) -> dict:
    if not is_configured(settings):
        return {
            "ok": False,
            "channel": "email",
            "configured": False,
            "error": "EMAIL is not configured. Set EMAIL_ENABLED, EMAIL_HOST, EMAIL_USER, EMAIL_PASSWORD and EMAIL_TO.",
        }

    recipients = split_recipients(settings.to)
    sender = (settings.from_email or settings.user).strip()
    msg = EmailMessage()
    msg["Subject"] = title
    msg["From"] = formataddr((settings.from_name or "Sakura 做题集", sender))
    msg["To"] = ", ".join(recipients)
    msg.set_content(content or "", subtype="plain", charset="utf-8")
    msg.add_alternative(
        f"""<!doctype html>
<html>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;line-height:1.65;color:#1f2937;">
{markdown_to_html(content or "")}
</body>
</html>""",
        subtype="html",
    )

    port = int(normalize_port(settings.port))
    try:
        if normalize_onoff(settings.use_ssl, "1") == "1":
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(settings.host, port, timeout=20, context=context) as smtp:
                smtp.login(settings.user, settings.password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(settings.host, port, timeout=20) as smtp:
                smtp.ehlo()
                if normalize_onoff(settings.use_starttls) == "1":
                    smtp.starttls(context=ssl.create_default_context())
                    smtp.ehlo()
                smtp.login(settings.user, settings.password)
                smtp.send_message(msg)
        return {"ok": True, "channel": "email", "to": mask_email_list(settings.to)}
    except Exception as exc:
        traceback.print_exc()
        return {"ok": False, "channel": "email", "error": str(exc)}
