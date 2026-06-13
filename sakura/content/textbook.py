from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable

import fitz


QUESTION_DOCUMENT_PATTERN = re.compile(
    r"(模拟卷|模拟考试|模考试卷|模考|真题卷?|试卷|套卷|试题|押题|冲刺卷|预测卷|自测卷|练习卷|测试卷|考试卷|卷子)",
    re.I,
)
GENERIC_QUESTION_VOLUME_PATTERN = re.compile(r"[\w\u4e00-\u9fff]{1,24}卷", re.I)
TEXTBOOK_VOLUME_PATTERN = re.compile(r"(上卷|中卷|下卷|第一卷|第二卷|第三卷|第四卷|第五卷)")


class TextbookImportError(ValueError):
    pass


def looks_like_question_document(filename: str, title: str = "") -> bool:
    text = f"{title or ''} {filename or ''}"
    if QUESTION_DOCUMENT_PATTERN.search(text):
        return True
    if TEXTBOOK_VOLUME_PATTERN.search(text):
        return False
    return bool(GENERIC_QUESTION_VOLUME_PATTERN.search(text))


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
    saved_pages = item.get("saved_pages")
    item["saved_pages"] = int(item["page_count"] if saved_pages is None else saved_pages)
    item["question_like"] = looks_like_question_document(item.get("filename", ""), item.get("title", ""))
    return item


def textbook_page_to_dict(row, to_public_path: Callable[[str], str]) -> dict:
    item = dict(row)
    item["pdf_page_number"] = int(item.get("page_number") or 0)
    item["display_page"] = int(item.get("display_page") or item["pdf_page_number"] or 0)
    image_path = item.get("image_path") or ""
    item["image_url"] = to_public_path(image_path) if image_path else ""
    try:
        item["paragraphs"] = json.loads(item.get("paragraphs_json") or "[]")
    except json.JSONDecodeError:
        item["paragraphs"] = []
    return item


def load_textbooks(conn) -> list:
    return conn.execute(
        """
        SELECT
            t.*,
            COUNT(p.id) saved_pages,
            MIN(p.page_number) first_page,
            MAX(p.page_number) last_page,
            MIN(p.page_number) first_display_page,
            MAX(p.page_number) last_display_page
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


def _nearest_remaining_page(conn, textbook_id: str, page_number: int) -> int | None:
    """After removing page_number, pick the closest surviving page (next first, else previous)."""
    nxt = conn.execute(
        "SELECT MIN(page_number) n FROM textbook_pages WHERE textbook_id = ? AND page_number > ?",
        (textbook_id, page_number),
    ).fetchone()
    if nxt and nxt["n"] is not None:
        return int(nxt["n"])
    prev = conn.execute(
        "SELECT MAX(page_number) n FROM textbook_pages WHERE textbook_id = ? AND page_number < ?",
        (textbook_id, page_number),
    ).fetchone()
    if prev and prev["n"] is not None:
        return int(prev["n"])
    return None


def _header_footer_text(page) -> str:
    rect = page.rect
    band_height = min(max(rect.height * 0.13, 36), 96)
    top_clip = fitz.Rect(rect.x0, rect.y0, rect.x1, rect.y0 + band_height)
    bottom_clip = fitz.Rect(rect.x0, rect.y1 - band_height, rect.x1, rect.y1)
    parts = [
        (page.get_text("text", clip=top_clip, sort=True) or "").strip(),
        (page.get_text("text", clip=bottom_clip, sort=True) or "").strip(),
    ]
    return "\n".join(part for part in parts if part).strip()


def _header_footer_ocr_text(page, *, temp_dir: Path, page_key: str, ocr_image_text: Callable[[str], str] | None = None) -> str:
    if not ocr_image_text:
        return ""
    rect = page.rect
    band_height = min(max(rect.height * 0.16, 60), 140)
    clips = [
        ("top", fitz.Rect(rect.x0, rect.y0, rect.x1, rect.y0 + band_height)),
        ("bottom", fitz.Rect(rect.x0, rect.y1 - band_height, rect.x1, rect.y1)),
    ]
    parts: list[str] = []
    for suffix, clip in clips:
        clip_path = temp_dir / f"{page_key}_{suffix}.png"
        try:
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=clip, alpha=False)
            pix.save(clip_path)
            text = (ocr_image_text(str(clip_path)) or "").strip()
            if text:
                parts.append(text)
                if _extract_printed_page_candidates(text):
                    break
        except Exception:
            continue
        finally:
            try:
                if clip_path.exists():
                    clip_path.unlink()
            except Exception:
                pass
    return "\n".join(parts).strip()


def _extract_printed_page_candidates(text: str) -> list[tuple[int, int]]:
    candidates: list[tuple[int, int]] = []
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        direct = re.fullmatch(r"(?:第\s*)?(\d{1,4})(?:\s*页)?", line)
        if direct:
            candidates.append((int(direct.group(1)), 100))
            continue
        wrapped = re.fullmatch(r"[-—_·•()\[\]{}（）【】\s]*?(\d{1,4})[-—_·•()\[\]{}（）【】\s]*", line)
        if wrapped:
            candidates.append((int(wrapped.group(1)), 90))
            continue
        page_line = re.search(r"第\s*(\d{1,4})\s*页", line)
        if page_line:
            candidates.append((int(page_line.group(1)), 80))
        for token in re.findall(r"(?<!\d)(\d{1,4})(?!\d)", line):
            candidates.append((int(token), 30))
    filtered = [(value, score) for value, score in candidates if 0 < value <= 9999]
    filtered.sort(key=lambda item: (-item[1], item[0]))
    return filtered


def detect_printed_page_number(
    page,
    *,
    ocr_text: str = "",
    temp_dir: Path | None = None,
    page_key: str = "page",
    ocr_image_text: Callable[[str], str] | None = None,
) -> int | None:
    band_text = _header_footer_text(page)
    candidates = _extract_printed_page_candidates(band_text)
    if not candidates and temp_dir:
        band_ocr_text = _header_footer_ocr_text(
            page,
            temp_dir=temp_dir,
            page_key=page_key,
            ocr_image_text=ocr_image_text,
        )
        candidates = _extract_printed_page_candidates(band_ocr_text)
    if not candidates and ocr_text:
        lines = [line.strip() for line in ocr_text.splitlines() if line.strip()]
        edge_lines = "\n".join(lines[:3] + lines[-3:])
        candidates = _extract_printed_page_candidates(edge_lines)
    if not candidates:
        return None
    return int(candidates[0][0])


def resolve_textbook_page_row(conn, textbook_id: str, requested_page: int):
    book = conn.execute("SELECT * FROM textbooks WHERE id = ?", (textbook_id,)).fetchone()
    if not book:
        raise ValueError("教材不存在。")

    page = conn.execute(
        "SELECT * FROM textbook_pages WHERE textbook_id = ? AND page_number = ?",
        (textbook_id, requested_page),
    ).fetchone()
    if not page:
        raise ValueError("教材页不存在。")
    return dict(book), page


def delete_textbook_page(
    conn,
    textbook_id: str,
    page_number: int,
    *,
    delete_file: Callable[[str], None],
) -> dict | None:
    """Delete one page placeholder and its chats; other page numbers stay stable."""
    page = conn.execute(
        "SELECT image_path, page_number FROM textbook_pages WHERE textbook_id = ? AND page_number = ?",
        (textbook_id, page_number),
    ).fetchone()
    if not page:
        return None
    next_page = _nearest_remaining_page(conn, textbook_id, page_number)
    if page["image_path"]:
        delete_file(page["image_path"])
    conn.execute(
        "DELETE FROM textbook_chats WHERE textbook_id = ? AND page_number = ?",
        (textbook_id, page_number),
    )
    conn.execute(
        "DELETE FROM textbook_pages WHERE textbook_id = ? AND page_number = ?",
        (textbook_id, page_number),
    )
    saved_pages = conn.execute(
        "SELECT COUNT(*) c FROM textbook_pages WHERE textbook_id = ?",
        (textbook_id,),
    ).fetchone()["c"]
    return {
        "ok": True,
        "deleted_page": page_number,
        "next_page": next_page,
        "saved_pages": saved_pages,
    }


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


def insert_textbook_page_placeholders(conn, *, book_id: str, page_count: int, created_at: str) -> None:
    """Register page placeholders only; OCR/rendered text stays in the current response."""
    rows = [
        (uuid.uuid4().hex, book_id, n, None, "", "", "[]", 0, created_at)
        for n in range(1, page_count + 1)
    ]
    conn.executemany(
        """
        INSERT INTO textbook_pages (
            id, textbook_id, page_number, display_page, image_path, page_text, paragraphs_json, rendered, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def render_textbook_page_view(
    book,
    page_row,
    *,
    page_dir: Path,
    render_page_image: Callable,
    ocr_image_text: Callable[[str], str] | None = None,
    full_page_ocr: bool = True,
) -> dict:
    """Render one page for the current reader view without caching OCR text in the DB."""
    book_id = book["id"]
    page_number = page_row["page_number"]
    image_path = page_dir / f"{book_id}_textbook_current.png"
    text = ""
    paragraphs: list[str] = []
    image_value = ""
    display_page = int(page_number)
    ocr_text = ""
    try:
        pdf = fitz.open(book["stored_path"])
        try:
            page = pdf[page_number - 1]
            render_page_image(page, image_path)
            image_value = str(image_path)
            text = page.get_text("text", sort=True).strip()
            if not text and ocr_image_text and full_page_ocr:
                ocr_text = (ocr_image_text(image_value) or "").strip()
                text = ocr_text
            paragraphs = split_textbook_paragraphs(text)
        finally:
            pdf.close()
    except Exception:
        # Source PDF missing/corrupt — mark rendered anyway to avoid retrying every read; the
        # page just shows no image / no extracted text.
        text = ""
        paragraphs = []
        image_value = ""
    updated = dict(page_row)
    updated.update({
        "image_path": image_value,
        "page_text": text,
        "display_page": display_page,
        "paragraphs_json": json.dumps(paragraphs, ensure_ascii=False),
        "rendered": 0,
    })
    return updated


def insert_textbook(
    conn,
    *,
    book_id: str,
    title: str,
    subject: str,
    filename: str,
    stored_path: Path,
    page_count: int,
    created_at: str,
) -> None:
    conn.execute(
        """
        INSERT INTO textbooks (id, title, subject, filename, stored_path, page_count, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (book_id, title, subject, filename, str(stored_path), page_count, created_at),
    )


def imported_textbook_payload(*, book_id: str, title: str, subject: str, page_count: int) -> dict:
    return {"textbook_id": book_id, "title": title, "subject": subject, "page_count": page_count}


def save_textbook_chat_message(
    conn,
    *,
    textbook_id: str,
    page_number: int,
    role: str,
    content: str,
    content_limit: int,
    created_at: str | None = None,
) -> str:
    message_id = uuid.uuid4().hex
    conn.execute(
        "INSERT INTO textbook_chats (id, textbook_id, page_number, role, content, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (
            message_id,
            textbook_id,
            page_number,
            role,
            content[:content_limit],
            created_at or datetime.now().isoformat(timespec="seconds"),
        ),
    )
    return message_id


def parse_textbook_request(payload: dict, *, parse_positive_int: Callable[[str, int | None], int | None]) -> dict:
    history = payload.get("history") if isinstance(payload.get("history"), list) else []
    return {
        "textbook_id": str(payload.get("textbook_id", "")).strip(),
        "page_number": parse_positive_int(str(payload.get("page_number", "")), 1) or 1,
        "paragraph_index": parse_positive_int(str(payload.get("paragraph_index", "")), 0) or 0,
        "selected_paragraph_text": str(payload.get("selected_paragraph_text", "")).strip()[:8000],
        "message": str(payload.get("message", "")).strip(),
        "history": history,
    }


def import_textbook_pdf(
    filename: str,
    pdf_bytes: bytes,
    *,
    title: str = "",
    subject: str = "",
    upload_dir: Path,
    connect: Callable,
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
    if looks_like_question_document(filename, metadata["title"]):
        raise TextbookImportError("这个 PDF 看起来是模拟卷/真题/试卷，请到「全真模拟卷」导入；教材精读只处理教材、讲义和参考书。")
    pdf_path = upload_dir / f"{book_id}_{metadata['safe_name']}"
    pdf_path.write_bytes(pdf_bytes)
    title = metadata["title"]
    subject = metadata["subject"]
    now = datetime.now().isoformat(timespec="seconds")
    # Only read the page count here — pages are rendered lazily on first read, so importing a
    # large PDF stays fast and doesn't block the request rendering hundreds of images.
    pdf = fitz.open(pdf_path)
    try:
        page_count = pdf.page_count
    finally:
        pdf.close()
    with connect() as conn:
        insert_textbook(
            conn,
            book_id=book_id,
            title=title,
            subject=subject,
            filename=filename,
            stored_path=pdf_path,
            page_count=page_count,
            created_at=now,
        )
        insert_textbook_page_placeholders(conn, book_id=book_id, page_count=page_count, created_at=now)
    return imported_textbook_payload(book_id=book_id, title=title, subject=subject, page_count=page_count)


def build_textbook_context(
    conn,
    textbook_id: str,
    page_number: int,
    paragraph_index: int = 0,
    *,
    to_public_path: Callable[[str], str],
    page_dir: Path,
    render_page_image: Callable,
    ocr_image_text: Callable[[str], str] | None = None,
    full_page_ocr: bool = True,
) -> tuple[dict, dict]:
    book, page = resolve_textbook_page_row(conn, textbook_id, page_number)
    page = render_textbook_page_view(
        book,
        page,
        page_dir=page_dir,
        render_page_image=render_page_image,
        ocr_image_text=ocr_image_text,
        full_page_ocr=full_page_ocr,
    )
    page_item = textbook_page_to_dict(page, to_public_path)
    paragraphs = page_item.get("paragraphs") or []
    selected = ""
    if 0 < paragraph_index <= len(paragraphs):
        selected = paragraphs[paragraph_index - 1]
    return dict(book), {**page_item, "selected_paragraph": selected}


def build_textbook_selected_paragraph_context(
    conn,
    textbook_id: str,
    page_number: int,
    paragraph_index: int,
    selected_text: str,
    *,
    to_public_path: Callable[[str], str],
) -> tuple[dict, dict]:
    book, page_row = resolve_textbook_page_row(conn, textbook_id, page_number)
    selected = (selected_text or "").strip()
    page_data = dict(page_row)
    page_data.update({
        "page_text": selected,
        "paragraphs_json": json.dumps([selected], ensure_ascii=False) if selected else "[]",
        "display_page": int(page_number),
    })
    page_item = textbook_page_to_dict(page_data, to_public_path)
    page_item["paragraphs"] = [selected] if selected else []
    page_item["selected_paragraph"] = selected
    page_item["selected_paragraph_index"] = int(paragraph_index or 0)
    return dict(book), page_item


def explain_textbook(
    book: dict,
    page: dict,
    message: str,
    history: list[dict],
    *,
    llm_enabled: bool,
    call_llm_messages: Callable,
    vision_enabled: bool = False,
    call_llm_vision: Callable | None = None,
    image_to_data_url: Callable[[str], str] | None = None,
) -> str:
    selected = page.get("selected_paragraph") or ""
    paragraphs = page.get("paragraphs") or []
    paragraph_preview = "\n".join(f"{i + 1}. {p}" for i, p in enumerate(paragraphs[:12]))
    page_text = (page.get("page_text") or "").strip()
    system = (
        "你是 Sakura 做题集的教材精读老师。用中文回答，讲清概念、公式来源、直觉和常见误区。"
        "如果涉及数学公式，使用 Markdown + LaTeX；展示公式优先使用 \\[...\\]。"
        "不要假装读过整本书，只根据提供的页面、段落和学生问题解释。"
    )
    context = f"""
教材：{book.get('title')} / {book.get('subject')}
页码：{page.get('display_page') or page.get('page_number')}
选中段落：{selected or '未指定'}
本页段落：
{paragraph_preview}

本页全文（截断）：
{page_text[:5000] or '（本页无文本层，可能是扫描件）'}
"""
    if not llm_enabled:
        return (
            "当前未配置 AI 接口密钥，先给出本地精读提示：\n"
            f"1. 先定位第 {page.get('display_page') or page.get('page_number')} 页的核心概念。\n"
            "2. 把不懂的句子拆成“定义、条件、结论、推导依据”。\n"
            f"3. 你选中的段落是：{selected or '未指定具体段落'}\n"
            "配置 API Key 后可以获得逐句讲解和追问。"
        )

    # Scanned page (no text layer): if a vision model is configured, send the page image so the
    # model can actually read it. Otherwise tell the user plainly instead of letting the text
    # model hallucinate about a blank page.
    if not page_text:
        data_url = image_to_data_url(page.get("image_path", "")) if image_to_data_url else ""
        if vision_enabled and call_llm_vision and data_url:
            vision_messages = [
                {"role": "system", "content": system + "\n这一页没有文本层（扫描件），请直接根据下面的页面图片内容来讲解，不要编造图片以外的内容。"},
                {"role": "system", "content": context},
            ]
            for item in history[-6:]:
                if item.get("role") in {"user", "assistant"} and item.get("content"):
                    vision_messages.append({"role": item["role"], "content": str(item["content"])[:2000]})
            vision_messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": message},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            })
            return call_llm_vision(vision_messages, temperature=0.35)
        if not data_url:
            return (
                f"第 {page.get('display_page') or page.get('page_number')} 页是扫描件，没有可提取的文字，但本地页面图片没有读到，"
                "所以 AI 无法读取这一页的内容。\n\n"
                "可以尝试重新读取该页、重新导入教材，或换用带文本层的 PDF。"
            )
        if not vision_enabled:
            return (
                f"第 {page.get('display_page') or page.get('page_number')} 页是扫描件，没有可提取的文字，当前也未配置视觉模型，"
                "所以 AI 无法读取这一页的内容。\n\n"
                "解决办法：在「AI 设置」里填写一个支持图片输入的视觉模型（如 qwen-vl-max、gpt-4o、doubao-vision），"
                "保存后即可让 AI 直接看图讲解；或换用带文本层的电子版 PDF。"
            )

    messages = [{"role": "system", "content": system}, {"role": "system", "content": context}]
    for item in history[-8:]:
        if item.get("role") in {"user", "assistant"} and item.get("content"):
            messages.append({"role": item["role"], "content": str(item["content"])[:2000]})
    messages.append({"role": "user", "content": message})
    return call_llm_messages(messages, temperature=0.35)
