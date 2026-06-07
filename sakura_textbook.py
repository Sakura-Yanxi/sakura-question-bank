from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable

import fitz


def split_textbook_paragraphs(text: str) -> list[str]:
    clean_lines = [line.strip() for line in (text or "").replace("\r\n", "\n").split("\n")]
    paragraphs: list[str] = []
    buffer: list[str] = []
    for line in clean_lines:
        if not line:
            if buffer:
                paragraphs.append(" ".join(buffer).strip())
                buffer = []
            continue
        buffer.append(line)
        if len("".join(buffer)) > 180 or re.search(r"[。！？；.!?;]$", line):
            paragraphs.append(" ".join(buffer).strip())
            buffer = []
    if buffer:
        paragraphs.append(" ".join(buffer).strip())
    paragraphs = [p for p in paragraphs if p]
    if not paragraphs and text.strip():
        paragraphs = [text.strip()]
    return paragraphs


def textbook_to_dict(row) -> dict:
    item = dict(row)
    item["page_count"] = int(item.get("page_count") or 0)
    item["saved_pages"] = int(item.get("saved_pages") or item["page_count"] or 0)
    return item


def textbook_page_to_dict(row, to_public_path: Callable[[str], str]) -> dict:
    item = dict(row)
    item["image_url"] = to_public_path(item.get("image_path") or "")
    try:
        item["paragraphs"] = json.loads(item.get("paragraphs_json") or "[]")
    except json.JSONDecodeError:
        item["paragraphs"] = []
    return item


def load_textbooks(conn) -> list:
    return conn.execute(
        """
        SELECT t.*, COUNT(p.id) saved_pages
        FROM textbooks t
        LEFT JOIN textbook_pages p ON p.textbook_id = t.id
        GROUP BY t.id
        ORDER BY t.created_at DESC
        """
    ).fetchall()


def delete_textbook(conn, textbook_id: str, *, delete_file: Callable[[str], None]) -> bool:
    book = conn.execute("SELECT stored_path FROM textbooks WHERE id = ?", (textbook_id,)).fetchone()
    if not book:
        return False
    page_rows = conn.execute("SELECT image_path FROM textbook_pages WHERE textbook_id = ?", (textbook_id,)).fetchall()
    for row in page_rows:
        delete_file(row["image_path"])
    delete_file(book["stored_path"])
    conn.execute("DELETE FROM textbook_chats WHERE textbook_id = ?", (textbook_id,))
    conn.execute("DELETE FROM textbook_pages WHERE textbook_id = ?", (textbook_id,))
    conn.execute("DELETE FROM textbooks WHERE id = ?", (textbook_id,))
    return True


def textbook_import_metadata(
    filename: str,
    title: str,
    subject: str,
    *,
    normalize_label: Callable[[str, str], str],
    default_subject: str,
) -> dict:
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", filename) or "textbook.pdf"
    return {
        "safe_name": safe_name,
        "title": title.strip() or Path(filename).stem,
        "subject": normalize_label(subject, default_subject),
    }


def import_textbook_pdf(
    filename: str,
    pdf_bytes: bytes,
    *,
    title: str = "",
    subject: str = "",
    upload_dir: Path,
    page_dir: Path,
    connect: Callable,
    render_page_image: Callable,
    normalize_label: Callable[[str, str], str],
    default_subject: str,
) -> dict:
    book_id = uuid.uuid4().hex
    metadata = textbook_import_metadata(
        filename,
        title,
        subject,
        normalize_label=normalize_label,
        default_subject=default_subject,
    )
    pdf_path = upload_dir / f"{book_id}_{metadata['safe_name']}"
    pdf_path.write_bytes(pdf_bytes)
    title = metadata["title"]
    subject = metadata["subject"]
    now = datetime.now().isoformat(timespec="seconds")
    pdf = fitz.open(pdf_path)
    page_count = pdf.page_count
    try:
        with connect() as conn:
            conn.execute(
                """
                INSERT INTO textbooks (id, title, subject, filename, stored_path, page_count, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (book_id, title, subject, filename, str(pdf_path), page_count, now),
            )
            for index, page in enumerate(pdf, start=1):
                page_id = uuid.uuid4().hex
                text = page.get_text("text", sort=True).strip()
                paragraphs = split_textbook_paragraphs(text)
                image_path = page_dir / f"{book_id}_textbook_page_{index:03d}.png"
                render_page_image(page, image_path)
                conn.execute(
                    """
                    INSERT INTO textbook_pages (
                        id, textbook_id, page_number, image_path, page_text, paragraphs_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (page_id, book_id, index, str(image_path), text, json.dumps(paragraphs, ensure_ascii=False), now),
                )
    finally:
        pdf.close()
    return {"textbook_id": book_id, "title": title, "subject": subject, "page_count": page_count}


def build_textbook_context(
    conn,
    textbook_id: str,
    page_number: int,
    paragraph_index: int = 0,
    *,
    to_public_path: Callable[[str], str],
) -> tuple[dict, dict]:
    book = conn.execute("SELECT * FROM textbooks WHERE id = ?", (textbook_id,)).fetchone()
    if not book:
        raise ValueError("教材不存在。")
    page = conn.execute(
        "SELECT * FROM textbook_pages WHERE textbook_id = ? AND page_number = ?",
        (textbook_id, page_number),
    ).fetchone()
    if not page:
        raise ValueError("教材页不存在。")
    page_item = textbook_page_to_dict(page, to_public_path)
    paragraphs = page_item.get("paragraphs") or []
    selected = ""
    if 0 < paragraph_index <= len(paragraphs):
        selected = paragraphs[paragraph_index - 1]
    return dict(book), {**page_item, "selected_paragraph": selected}


def explain_textbook(
    book: dict,
    page: dict,
    message: str,
    history: list[dict],
    *,
    llm_enabled: bool,
    call_llm_messages: Callable,
) -> str:
    selected = page.get("selected_paragraph") or ""
    paragraphs = page.get("paragraphs") or []
    paragraph_preview = "\n".join(f"{i + 1}. {p}" for i, p in enumerate(paragraphs[:12]))
    system = (
        "你是 Sakura 做题集的教材精读老师。用中文回答，讲清概念、公式来源、直觉和常见误区。"
        "如果涉及数学公式，使用 Markdown + LaTeX；展示公式优先使用 \\[...\\]。"
        "不要假装读过整本书，只根据提供的页面、段落和学生问题解释。"
    )
    context = f"""
教材：{book.get('title')} / {book.get('subject')}
页码：{page.get('page_number')}
选中段落：{selected or '未指定'}
本页段落：
{paragraph_preview}

本页全文（截断）：
{(page.get('page_text') or '')[:5000]}
"""
    messages = [{"role": "system", "content": system}, {"role": "system", "content": context}]
    for item in history[-8:]:
        if item.get("role") in {"user", "assistant"} and item.get("content"):
            messages.append({"role": item["role"], "content": str(item["content"])[:2000]})
    messages.append({"role": "user", "content": message})
    if not llm_enabled:
        return (
            "当前未配置 AI 接口密钥，先给出本地精读提示：\n"
            f"1. 先定位第 {page.get('page_number')} 页的核心概念。\n"
            "2. 把不懂的句子拆成“定义、条件、结论、推导依据”。\n"
            f"3. 你选中的段落是：{selected or '未指定具体段落'}\n"
            "配置 API Key 后可以获得逐句讲解和追问。"
        )
    return call_llm_messages(messages, temperature=0.35)
