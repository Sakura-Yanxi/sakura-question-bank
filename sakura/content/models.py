from __future__ import annotations

import json
import re
from typing import Callable


def extract_question_no(text: str) -> str:
    """Best-effort printed question number extraction, used for quick locating."""
    if not text:
        return ""
    for line in text.splitlines()[:8]:
        s = line.strip()
        if not s or "公众号" in s or "微信" in s:
            continue
        if re.match(r"^\d+\.\d+", s):
            continue
        m = re.match(r"^(\d{1,3})\s*[.、．。)）]?\s*\S", s)
        if m:
            return str(int(m.group(1)))
    return ""


def normalize_document_kind(
    value: str | None,
    *,
    normalize_label: Callable[[str, str], str],
    default_document_kind: str,
    mock_paper_kind: str,
    document_kinds: set[str],
) -> str:
    clean = normalize_label(value or "", default_document_kind)
    if clean.lower() in {"mock", "mock_paper", "paper", "exam"}:
        return mock_paper_kind
    if clean.lower() in {"book", "workbook"}:
        return default_document_kind
    return clean if clean in document_kinds else default_document_kind


def row_to_dict(
    row,
    *,
    to_public_path: Callable[[str], str],
    normalize_document_kind: Callable[[str | None], str],
    normalize_meta_tags: Callable,
) -> dict:
    item = dict(row)
    item["image_url"] = to_public_path(item["image_path"])
    item["meta_tags"] = normalize_meta_tags(item.get("meta_tags"))
    if "document_kind" in item:
        item["document_kind"] = normalize_document_kind(item.get("document_kind"))
    item["question_no"] = (item.get("question_no") or "").strip() or extract_question_no(item.get("ocr_text", ""))
    return item


def question_detail_to_dict(
    conn,
    row,
    *,
    row_to_dict: Callable,
    load_question_review_notes: Callable,
) -> dict:
    item = row_to_dict(row)
    notes = load_question_review_notes(conn, item["id"])
    if not notes and item.get("user_note"):
        notes = [
            {
                "id": "legacy-user-note",
                "question_id": item["id"],
                "status": item.get("status") or "",
                "note": item.get("user_note") or "",
                "meta_tags": item.get("meta_tags") or [],
                "source": "legacy",
                "created_at": item.get("last_reviewed_at") or item.get("created_at") or "",
            }
        ]
    item["review_notes"] = notes
    return item


def document_to_dict(row, normalize_document_kind: Callable[[str | None], str]) -> dict:
    item = dict(row)
    item["document_kind"] = normalize_document_kind(item.get("document_kind"))
    return item


def question_payload(row, *, normalize_document_kind: Callable[[str | None], str], normalize_meta_tags: Callable) -> dict:
    item = dict(row)
    item["meta_tags"] = normalize_meta_tags(item.get("meta_tags"))
    if "document_kind" in item:
        item["document_kind"] = normalize_document_kind(item.get("document_kind"))
    return item


def get_meta_tag_stats(conn, *, meta_tags: list[str], normalize_meta_tags: Callable, doc_id: str | None = None) -> list[dict]:
    params = []
    where = "WHERE q.status IN ('做错', '半会', '需复习')"
    if doc_id:
        where += " AND q.document_id = ?"
        params.append(doc_id)
    rows = conn.execute(f"SELECT q.meta_tags FROM questions q {where}", params).fetchall()
    counts = {tag: 0 for tag in meta_tags}
    for row in rows:
        for tag in normalize_meta_tags(row["meta_tags"]):
            counts[tag] += 1
    max_count = max(counts.values(), default=0) or 1
    return [{"tag": tag, "count": count, "ratio": round(count / max_count, 3)} for tag, count in counts.items()]
