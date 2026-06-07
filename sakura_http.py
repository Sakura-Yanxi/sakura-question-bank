from __future__ import annotations

import json
from http import HTTPStatus
from pathlib import Path


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


def content_type_for_path(path: Path) -> str:
    content_types = {
        ".html": "text/html; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".js": "application/javascript; charset=utf-8",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".pdf": "application/pdf",
    }
    return content_types.get(path.suffix.lower(), "application/octet-stream")


def serve_file(handler, path: Path, root: Path) -> None:
    resolved = path.resolve()
    if not str(resolved).startswith(str(root)) or not resolved.exists() or resolved.is_dir():
        return text_response(handler, "Not found", HTTPStatus.NOT_FOUND)
    body = resolved.read_bytes()
    handler.send_response(200)
    handler.send_header("Content-Type", content_type_for_path(resolved))
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)
