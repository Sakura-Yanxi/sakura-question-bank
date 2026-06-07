from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


QUESTION_UPDATE_FIELDS = {
    "status",
    "mistake_reason",
    "meta_tags",
    "user_note",
    "category",
    "subcategory",
    "chapter",
    "difficulty",
    "question_no",
    "ai_analysis",
    "ai_hint",
    "ai_variations",
}


class QuestionServiceError(ValueError):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


class QuestionUpdateError(QuestionServiceError):
    pass


def load_question_index(conn, where: str, params: list[str]) -> tuple[list, list, list]:
    rows = conn.execute(
        f"""
        SELECT q.*, d.filename, d.title document_title, d.subject, d.document_kind
        FROM questions q
        JOIN documents d ON d.id = q.document_id
        {where}
        ORDER BY q.created_at DESC, q.page_number ASC
        """,
        params,
    ).fetchall()
    stats = conn.execute(
        """
        SELECT q.category, COUNT(*) total,
               SUM(CASE WHEN status = '做错' THEN 1 ELSE 0 END) wrong
        FROM questions q
        JOIN documents d ON d.id = q.document_id
        {where}
        GROUP BY q.category
        ORDER BY total DESC
        """.format(where=where),
        params,
    ).fetchall()
    subject_stats = conn.execute(
        """
        SELECT d.subject, COUNT(*) total,
               SUM(CASE WHEN q.status = '做错' THEN 1 ELSE 0 END) wrong
        FROM questions q
        JOIN documents d ON d.id = q.document_id
        {where}
        GROUP BY d.subject
        ORDER BY total DESC
        """.format(where=where),
        params,
    ).fetchall()
    return rows, stats, subject_stats


def load_question_detail(conn, q_id: str):
    return conn.execute(
        """
        SELECT q.*, d.filename, d.title document_title, d.subject, d.document_kind
        FROM questions q
        JOIN documents d ON d.id = q.document_id
        WHERE q.id = ?
        """,
        (q_id,),
    ).fetchone()


def load_question_for_ai(conn, q_id: str):
    return conn.execute(
        """
        SELECT q.*, d.subject, d.document_kind
        FROM questions q
        JOIN documents d ON d.id = q.document_id
        WHERE q.id = ?
        """,
        (q_id,),
    ).fetchone()


def insert_imported_question(
    conn,
    *,
    q_id: str,
    doc_id: str,
    page_number: int,
    seq_no: int,
    question_no: str,
    image_path,
    question_text: str,
    classification: dict,
    created_at: str,
) -> dict:
    conn.execute(
        """
        INSERT INTO questions (
            id, document_id, page_number, seq_no, question_no, image_path, ocr_text, category,
            subcategory, chapter, difficulty, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            q_id,
            doc_id,
            page_number,
            seq_no,
            question_no,
            str(image_path),
            question_text,
            classification["category"],
            classification["subcategory"],
            classification["chapter"],
            classification["difficulty"],
            created_at,
        ),
    )
    return {
        "id": q_id,
        "page_number": page_number,
        "seq_no": seq_no,
        "question_no": question_no,
        "category": classification["category"],
        "subcategory": classification["subcategory"],
        "chapter": classification["chapter"],
    }


def load_chapter_stats(conn, doc_id: str) -> tuple[object | None, list[dict]]:
    doc = conn.execute("SELECT id, title, filename FROM documents WHERE id = ?", (doc_id,)).fetchone()
    if not doc:
        return None, []
    rows = conn.execute(
        """
        SELECT chapter,
               MIN(page_number) first_page,
               COUNT(*) total,
               SUM(CASE WHEN status = '做对' THEN 1 ELSE 0 END) correct,
               SUM(CASE WHEN status = '做错' THEN 1 ELSE 0 END) wrong,
               SUM(CASE WHEN status IN ('半会', '需复习') THEN 1 ELSE 0 END) review,
               SUM(CASE WHEN status = '未做' THEN 1 ELSE 0 END) todo
        FROM questions
        WHERE document_id = ?
        GROUP BY chapter
        ORDER BY first_page ASC
        """,
        (doc_id,),
    ).fetchall()
    stats = []
    for row in rows:
        done = (row["correct"] or 0) + (row["wrong"] or 0) + (row["review"] or 0)
        correct_rate = round(((row["correct"] or 0) / done) * 100, 1) if done else 0
        item = dict(row)
        item["correct_rate"] = correct_rate
        stats.append(item)
    return doc, stats


def update_question(
    conn,
    q_id: str,
    payload: dict,
    *,
    normalize_meta_tags,
    wrongish_statuses: set[str],
    schedule_for_status,
) -> object:
    updates = {key: value for key, value in payload.items() if key in QUESTION_UPDATE_FIELDS}
    if not updates:
        raise QuestionUpdateError("没有可更新字段。", 400)

    current = conn.execute("SELECT * FROM questions WHERE id = ?", (q_id,)).fetchone()
    if not current:
        raise QuestionUpdateError("题目不存在。", 404)

    normalized_meta_tags = None
    if "meta_tags" in updates:
        normalized_meta_tags = normalize_meta_tags(updates["meta_tags"])
        updates["meta_tags"] = json.dumps(normalized_meta_tags, ensure_ascii=False)
    if updates.get("status") in wrongish_statuses:
        existing_tags = normalized_meta_tags if normalized_meta_tags is not None else normalize_meta_tags(current["meta_tags"])
        if not existing_tags:
            raise QuestionUpdateError("标记错题前，请至少选择一个元认知错因标签。", 400)
    if updates.get("status") in {*wrongish_statuses, "做对"}:
        updates["last_reviewed_at"] = datetime.now().isoformat(timespec="seconds")
        updates["review_count"] = "review_count + 1"
        updates.update(schedule_for_status(current, updates["status"]))

    assignments = []
    params = []
    for key, value in updates.items():
        if key == "review_count":
            assignments.append("review_count = review_count + 1")
        else:
            assignments.append(f"{key} = ?")
            params.append(value)
    params.append(q_id)
    conn.execute(f"UPDATE questions SET {', '.join(assignments)} WHERE id = ?", params)
    return load_question_detail(conn, q_id)


def rescan_document_chapters(
    conn,
    doc_id: str,
    *,
    normalize_document_kind,
    extract_text_and_chapters,
    classify_by_rules,
    default_category: str,
    default_chapter: str,
    mock_paper_kind: str,
) -> dict:
    doc = conn.execute("SELECT stored_path, document_kind, subject FROM documents WHERE id = ?", (doc_id,)).fetchone()
    if not doc:
        raise QuestionServiceError("做题本不存在。", 404)
    pdf_path = Path(doc["stored_path"])
    if not pdf_path.exists():
        raise QuestionServiceError("原始 PDF 文件不存在，无法重扫。", 404)

    document_kind = normalize_document_kind(doc["document_kind"])
    pages = extract_text_and_chapters(pdf_path, document_kind)
    updated = 0
    for page in pages:
        category, subcategory, difficulty = classify_by_rules(page["text"])
        if document_kind != mock_paper_kind and category == default_category and page["chapter"] != default_chapter:
            category = page["chapter"]
            subcategory = "章节归类"
        cursor = conn.execute(
            """
            UPDATE questions
            SET ocr_text = ?, chapter = ?, category = ?, subcategory = ?, difficulty = ?
            WHERE document_id = ? AND page_number = ?
            """,
            (
                page["text"],
                page["chapter"],
                category,
                subcategory,
                difficulty,
                doc_id,
                page["page_number"],
            ),
        )
        updated += max(cursor.rowcount, 0)
    return {"ok": True, "pages": len(pages), "updated": updated}
