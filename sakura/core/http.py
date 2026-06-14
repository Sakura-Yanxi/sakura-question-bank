from __future__ import annotations

import json
import re
import warnings
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


def read_multipart_form(headers, rfile):
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="'cgi' is deprecated.*", category=DeprecationWarning)
        import cgi

    return cgi.FieldStorage(fp=rfile, headers=headers, environ={"REQUEST_METHOD": "POST"})


def first_form_file(form, *field_names: str):
    for name in field_names:
        if name not in form:
            continue
        item = form[name]
        if isinstance(item, list):
            item = item[0] if item else None
        return item
    return None


def uploaded_filename(file_item) -> str:
    return str(getattr(file_item, "filename", "") or "")


def uploaded_file_has_suffix(file_item, suffix: str) -> bool:
    return uploaded_filename(file_item).lower().endswith(suffix.lower())


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


def send_attachment_bytes(
    handler,
    body: bytes,
    *,
    filename: str,
    content_type: str,
    status: int = 200,
) -> None:
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Disposition", content_disposition_attachment(filename))
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def stream_attachment_file(
    handler,
    path: Path,
    *,
    filename: str,
    content_type: str,
    chunk_size: int = 1024 * 1024,
) -> None:
    handler.send_response(200)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Disposition", content_disposition_attachment(filename))
    handler.send_header("Content-Length", str(path.stat().st_size))
    handler.end_headers()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            handler.wfile.write(chunk)


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


def to_public_path(path: str | Path, *, page_dir: Path, static_dir: Path) -> str:
    absolute = Path(path).resolve()
    try:
        return "/data/pages/" + absolute.relative_to(page_dir).as_posix()
    except ValueError:
        pass
    try:
        return "/static/" + absolute.relative_to(static_dir).as_posix()
    except ValueError:
        normalized = str(path).replace("\\", "/")
        marker = normalized.rfind("/data/pages/")
        if marker != -1:
            return normalized[marker:]
        name = Path(normalized).name
        return "/data/pages/" + name if name else ""


def public_file_base_for_path(path: str, *, page_dir: Path, static_dir: Path) -> Path | None:
    if path.startswith("/static/"):
        return static_dir
    if path.startswith("/data/pages/"):
        return page_dir
    return None
