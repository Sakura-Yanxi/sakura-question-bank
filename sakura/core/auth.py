from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from html import escape as html_escape
from urllib.parse import unquote


PUBLIC_AUTH_PATHS = {"/login", "/api/health"}


def auth_enabled(admin_password: str) -> bool:
    return bool(admin_password)


def auth_secret(admin_password: str, auth_secret_value: str) -> str:
    return auth_secret_value or admin_password or "sakura-local-dev"


def sign_session(payload: str, *, admin_password: str, auth_secret_value: str) -> str:
    secret = auth_secret(admin_password, auth_secret_value)
    return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def make_session_token(*, admin_password: str, auth_secret_value: str, max_age_seconds: int) -> str:
    expires = int(time.time()) + max_age_seconds
    nonce = secrets.token_urlsafe(18)
    payload = f"{expires}:{nonce}"
    return f"{payload}:{sign_session(payload, admin_password=admin_password, auth_secret_value=auth_secret_value)}"


def verify_session_token(token: str, *, admin_password: str, auth_secret_value: str) -> bool:
    parts = (token or "").split(":")
    if len(parts) != 3:
        return False
    expires, nonce, signature = parts
    payload = f"{expires}:{nonce}"
    expected = sign_session(payload, admin_password=admin_password, auth_secret_value=auth_secret_value)
    if not hmac.compare_digest(signature, expected):
        return False
    try:
        return int(expires) >= int(time.time())
    except ValueError:
        return False


def is_public_path(path: str) -> bool:
    return (
        path in PUBLIC_AUTH_PATHS
        or path.startswith("/practice/")
        or path.startswith("/api/practice/")
    )


def cookie_value(cookie_header: str, name: str) -> str:
    for part in (cookie_header or "").split(";"):
        if "=" not in part:
            continue
        key, value = part.strip().split("=", 1)
        if key == name:
            return unquote(value)
    return ""


def login_page(error: str = "") -> str:
    error_html = f"<div class='error'>{html_escape(error)}</div>" if error else ""
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Sakura 做题集 · 登录</title>
  <style>
    :root {{ color-scheme: light; --pink:#ec4899; --ink:#14213d; --muted:#718096; --line:#eadfea; }}
    * {{ box-sizing: border-box; }}
    body {{ margin:0; min-height:100vh; display:grid; place-items:center; font-family: Inter, "Microsoft YaHei", system-ui, sans-serif; background: radial-gradient(circle at 20% 10%, #fff0f7 0, transparent 28%), linear-gradient(135deg,#f8fbff,#fff7fb 48%,#f5fffb); color:var(--ink); }}
    .card {{ width:min(420px, calc(100vw - 32px)); background:rgba(255,255,255,.92); border:1px solid var(--line); border-radius:26px; padding:34px; box-shadow:0 28px 80px rgba(236,72,153,.16); }}
    .logo {{ width:58px; height:58px; border-radius:18px; display:grid; place-items:center; background:#fff0f7; color:var(--pink); font-size:28px; font-weight:900; margin-bottom:18px; }}
    h1 {{ margin:0 0 8px; font-size:28px; letter-spacing:0; }}
    p {{ margin:0 0 24px; color:var(--muted); line-height:1.7; }}
    label {{ display:grid; gap:8px; font-weight:800; color:#4a5568; }}
    input {{ width:100%; height:52px; border:1px solid #e6d8e6; border-radius:16px; padding:0 16px; font-size:16px; outline:none; }}
    input:focus {{ border-color:var(--pink); box-shadow:0 0 0 4px rgba(236,72,153,.12); }}
    button {{ width:100%; height:52px; margin-top:18px; border:0; border-radius:16px; color:white; background:linear-gradient(135deg,#ec4899,#f472b6); font-size:16px; font-weight:900; cursor:pointer; box-shadow:0 18px 34px rgba(236,72,153,.25); }}
    .error {{ margin-bottom:16px; padding:10px 12px; border-radius:14px; background:#fff5f5; color:#dc2626; font-weight:700; }}
    small {{ display:block; margin-top:16px; color:#94a3b8; line-height:1.6; }}
  </style>
</head>
<body>
  <main class="card">
    <div class="logo">S</div>
    <h1>Sakura 做题集</h1>
    <p>请输入管理员密码后进入学习面板。这样别人知道域名，也不能随意修改题库、API 和推送配置。</p>
    {error_html}
    <form method="post" action="/login">
      <label>管理员密码
        <input name="password" type="password" autocomplete="current-password" autofocus required />
      </label>
      <button type="submit">进入 Sakura</button>
    </form>
    <small>登录状态会在当前浏览器保留 14 天。忘记密码时可在服务器 .env 修改 SAKURA_ADMIN_PASSWORD。</small>
  </main>
</body>
</html>"""
