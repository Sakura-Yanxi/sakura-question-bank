from __future__ import annotations

import json
import re
from urllib.parse import quote
from http import HTTPStatus
from pathlib import Path

MAX_JSON_BODY_BYTES = 2 * 1024 * 1024
MAX_FORM_BODY_BYTES = 64 * 1024


class BadRequestError(ValueError):
    pass


def read_json_body(headers, rfile, *, max_bytes: int = MAX_JSON_BODY_BYTES) -> dict:
    raw = read_limited_body(headers, rfile, max_bytes=max_bytes)
    if not raw:
        return {}
    try:
        data = json.loads(raw.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise BadRequestError("请求体必须是 UTF-8 编码。") from exc
    except json.JSONDecodeError as exc:
        raise BadRequestError("请求体不是合法 JSON。") from exc
    if not isinstance(data, dict):
        raise BadRequestError("JSON 请求体必须是对象。")
    return data


def read_limited_body(headers, rfile, *, max_bytes: int) -> bytes:
    raw_length = headers.get("Content-Length", "0")
    try:
        length = int(raw_length)
    except (TypeError, ValueError) as exc:
        raise BadRequestError("请求体长度无效。") from exc
    if length <= 0:
        return b""
    if length > max_bytes:
        raise BadRequestError("请求体过大。")
    return rfile.read(length)


def json_response(handler, payload: dict | list, status: int = 200) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def text_response(handler, text: str, status: int = 200, content_type: str = "text/plain") -> None:
    body = text.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", f"{content_type}; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def redirect_response(handler, location: str, status: int = HTTPStatus.FOUND) -> None:
    handler.send_response(status)
    handler.send_header("Location", location)
    handler.end_headers()


def content_disposition_attachment(filename: str) -> str:
    clean = re.sub(r'[\r\n"\\]+', "_", str(filename or "download"))
    clean = clean.strip() or "download"
    ascii_name = re.sub(r"[^A-Za-z0-9._-]+", "_", clean).strip("._") or "download"
    encoded = quote(clean, safe="")
    return f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{encoded}'


def content_type_for_path(path: Path) -> str:
    content_types = {
        ".html": "text/html; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".js": "application/javascript; charset=utf-8",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".svg": "image/svg+xml",
        ".pdf": "application/pdf",
    }
    return content_types.get(path.suffix.lower(), "application/octet-stream")


def serve_file(handler, path: Path, root: Path) -> None:
    resolved = path.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError:
        return text_response(handler, "Not found", HTTPStatus.NOT_FOUND)
    if not resolved.exists() or resolved.is_dir():
        return text_response(handler, "Not found", HTTPStatus.NOT_FOUND)
    body = resolved.read_bytes()
    handler.send_response(200)
    handler.send_header("Content-Type", content_type_for_path(resolved))
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)
