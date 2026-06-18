from __future__ import annotations

from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Callable, Iterable
import re

import fitz


def query_first(query: dict, key: str, default: str = "") -> str:
    values = query.get(key, [])
    if not isinstance(values, (list, tuple)):
        values = [values]
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return default


def select_mistake_rows(
    conn,
    query: dict,
    *,
    mistakes_only: bool,
    build_question_filters: Callable[[dict, tuple[str, ...]], tuple[str, list]],
) -> list:
    """Apply mistake-export filters and return rows ready for PDF rendering."""
    where, params = build_question_filters(
        query,
        ("category", "status", "document_id", "chapter", "subject", "search"),
    )
    raw_ids = query_first(query, "ids")
    if raw_ids:
        selected_ids = [item for item in raw_ids.split(",") if re.fullmatch(r"[0-9a-fA-F]{32}", item)]
        if selected_ids:
            placeholders = ",".join("?" for _ in selected_ids)
            where = f"{where} AND q.id IN ({placeholders})" if where else f"WHERE q.id IN ({placeholders})"
            params.extend(selected_ids)
        else:
            where = f"{where} AND 1 = 0" if where else "WHERE 1 = 0"

    status_group = query_first(query, "status_group")
    if status_group == "review" and not raw_ids:
        cond = "(q.status IN ('半会', '需复习') OR (q.ever_wrong = 1 AND q.mastered_at IS NULL AND COALESCE(q.status, '') <> '做错'))"
        where = f"{where} AND {cond}" if where else f"WHERE {cond}"

    if mistakes_only:
        cond = "(q.status IN ('做错', '半会', '需复习') OR (q.ever_wrong = 1 AND q.mastered_at IS NULL))"
        where = f"{where} AND {cond}" if where else f"WHERE {cond}"

    return conn.execute(
        f"""
        SELECT q.*, COALESCE(NULLIF(d.title, ''), d.filename) document_title, d.subject, d.stored_path
        FROM questions q
        JOIN documents d ON d.id = q.document_id
        {where}
        ORDER BY d.subject ASC, document_title ASC, q.seq_no ASC, q.page_number ASC
        """,
        params,
    ).fetchall()


def build_filtered_mistakes_pdf(
    conn,
    query: dict,
    *,
    mistakes_only: bool,
    build_question_filters: Callable[[dict, tuple[str, ...]], tuple[str, list]],
    normalize_meta_tags: Callable[[object], list[str]],
) -> tuple[bytes, int]:
    rows = select_mistake_rows(
        conn,
        query,
        mistakes_only=mistakes_only,
        build_question_filters=build_question_filters,
    )
    return build_mistakes_pdf(rows, normalize_meta_tags)


def select_practice_batch_rows(conn, batch_id: str) -> list:
    return conn.execute(
        """
        SELECT
            q.*,
            COALESCE(NULLIF(d.title, ''), d.filename) document_title,
            d.subject,
            d.stored_path
        FROM practice_batch_items p
        JOIN questions q ON q.id = p.question_id
        JOIN documents d ON d.id = q.document_id
        WHERE p.batch_id = ?
        ORDER BY p.position ASC
        """,
        (batch_id,),
    ).fetchall()


def build_practice_batch_pdf(
    conn,
    batch_id: str,
    normalize_meta_tags: Callable[[object], list[str]],
) -> tuple[bytes, int]:
    return build_mistakes_pdf(select_practice_batch_rows(conn, batch_id), normalize_meta_tags)


def image_to_print_jpeg(image_path: Path, max_width: int = 1500, max_height: int = 2100) -> bytes:
    """Compress a question image into a print-friendly JPEG stream."""
    from PIL import Image, ImageOps

    with Image.open(image_path) as image:
        image = ImageOps.exif_transpose(image)
        if image.mode not in {"RGB", "L"}:
            image = image.convert("RGB")
        elif image.mode == "L":
            image = image.convert("RGB")
        image.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
        out = BytesIO()
        image.save(out, format="JPEG", quality=86, optimize=True, progressive=True)
        return out.getvalue()


def preferred_cjk_font() -> str | None:
    for path in (
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\NotoSansSC-VF.ttf",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\simsun.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.otf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    ):
        if Path(path).exists():
            return path
    return None


def text_panel_png(lines: list[tuple[str, int, tuple[int, int, int]]], width: int, height: int, align: str = "left") -> bytes | None:
    """Render Chinese title text with Pillow to avoid PyMuPDF CJK spacing issues."""
    from PIL import Image, ImageDraw, ImageFont

    font_path = preferred_cjk_font()
    if not font_path:
        return None
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    y = max(10, (height - sum(size + 12 for _, size, _ in lines)) // 2)
    for text, size, color in lines:
        font = ImageFont.truetype(font_path, size=size) if font_path else ImageFont.load_default()
        if len(text) > 120:
            text = text[:117] + "..."
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        x = 0 if align == "left" else max(0, (width - text_w) // 2)
        draw.text((x, y), text, fill=color, font=font)
        y += size + 12
    out = BytesIO()
    image.save(out, format="PNG", optimize=True)
    return out.getvalue()


def insert_text_panel(
    page: fitz.Page,
    rect: fitz.Rect,
    lines: list[tuple[str, int, tuple[int, int, int]]],
    *,
    align: str = "left",
    image_width: int = 1600,
    image_height: int = 420,
    prefer_text: bool = False,
) -> None:
    image = None if prefer_text else text_panel_png(lines, width=image_width, height=image_height, align=align)
    if image:
        page.insert_image(rect, stream=image, keep_proportion=True)
        return

    y = rect.y0 + max(0, (rect.height - sum(size + 10 for _, size, _ in lines)) / 2)
    for text, size, color in lines:
        text = str(text or "")
        if len(text) > 120:
            text = text[:117] + "..."
        font_size = max(8, min(size * 0.36, rect.height * 0.34))
        textbox = fitz.Rect(rect.x0, y, rect.x1, min(rect.y1, y + size * 1.35))
        page.insert_textbox(
            textbox,
            text,
            fontsize=font_size,
            fontname="china-s",
            color=tuple(channel / 255 for channel in color),
            align=1 if align == "center" else 0,
        )
        y += font_size * 1.45


def build_mistakes_pdf(
    rows: Iterable,
    normalize_meta_tags: Callable[[object], list[str]],
) -> tuple[bytes, int]:
    """Render selected mistake rows as a compact printable PDF."""
    items = [dict(row) for row in rows]
    doc = fitz.open()
    width, height, margin = 595.0, 842.0, 36.0

    today = date.today()
    cover = doc.new_page(width=width, height=height)
    insert_text_panel(
        cover,
        fitz.Rect(margin, 220, width - margin, 380),
        [
            ("错题本导出", 88, (32, 36, 46)),
            (f"共 {len(items)} 道 · 生成于 {today.isoformat()}", 44, (107, 114, 128)),
        ],
        align="center",
        image_width=1600,
        image_height=420,
        prefer_text=True,
    )

    source_cache: dict[str, fitz.Document] = {}
    try:
        for item in items:
            source_path = Path(item.get("stored_path") or "")
            page_index = int(item.get("page_number") or 0) - 1
            if source_path.exists() and source_path.is_file():
                try:
                    key = str(source_path.resolve())
                    source_doc = source_cache.get(key)
                    if source_doc is None:
                        source_doc = fitz.open(source_path)
                        source_cache[key] = source_doc
                    if 0 <= page_index < source_doc.page_count:
                        doc.insert_pdf(source_doc, from_page=page_index, to_page=page_index)
                        continue
                except Exception:
                    pass

            page = doc.new_page(width=width, height=height)
            meta = normalize_meta_tags(item.get("meta_tags"))
            head = (
                f"第{item.get('seq_no') or item.get('page_number')}题　"
                f"{item.get('document_title') or ''}　"
                f"{item.get('chapter') or ''}　[{item.get('status') or ''}]"
            )
            sub = f"错因：{'、'.join(meta) or '—'}"
            note = (item.get("user_note") or "").strip()
            if note:
                sub += f"　备注：{note[:40]}"
            insert_text_panel(
                page,
                fitz.Rect(margin, 22, width - margin, 76),
                [
                    (head, 34, (32, 36, 46)),
                    (sub, 24, (107, 114, 128)),
                ],
                image_width=1600,
                image_height=170,
            )

            img_path = Path(item.get("image_path", ""))
            img_rect = fitz.Rect(margin, 84, width - margin, height - margin)
            if img_path.exists():
                try:
                    page.insert_image(img_rect, stream=image_to_print_jpeg(img_path), keep_proportion=True)
                except Exception:
                    page.insert_textbox(img_rect, "（题图加载失败）", fontsize=11, fontname="china-s", align=1)
            else:
                page.insert_textbox(img_rect, "（题图文件已丢失）", fontsize=11, fontname="china-s", align=1)

        pdf_bytes = doc.tobytes(garbage=4, deflate=True)
    finally:
        for source_doc in source_cache.values():
            source_doc.close()
        doc.close()
    return pdf_bytes, len(items)
