from __future__ import annotations

from pathlib import Path


def unlink_if_inside(root: Path, path_value: str | Path | None) -> None:
    """Delete a file only when it belongs to the Sakura data directory."""
    if not path_value:
        return
    root_path = root.resolve()
    path = Path(path_value).resolve()
    try:
        path.relative_to(root_path)
    except ValueError:
        return
    if path.exists() and path.is_file():
        path.unlink()


def prune_empty_documents(conn, *, data_dir: Path) -> int:
    rows = conn.execute(
        """
        SELECT d.id, d.stored_path
        FROM documents d
        LEFT JOIN questions q ON q.document_id = d.id
        GROUP BY d.id
        HAVING COUNT(q.id) = 0
        """
    ).fetchall()
    for row in rows:
        unlink_if_inside(data_dir, row["stored_path"])
        conn.execute("DELETE FROM documents WHERE id = ?", (row["id"],))
    return len(rows)


def load_documents(conn, *, data_dir: Path) -> list:
    prune_empty_documents(conn, data_dir=data_dir)
    return conn.execute(
        """
        SELECT d.*,
               COUNT(q.id) question_count,
               SUM(CASE WHEN q.status = '做错' THEN 1 ELSE 0 END) wrong_count,
               SUM(CASE WHEN q.status IN ('需复习', '半会') THEN 1 ELSE 0 END) review_count
        FROM documents d
        LEFT JOIN questions q ON q.document_id = d.id
        GROUP BY d.id
        ORDER BY d.created_at DESC
        """
    ).fetchall()


def insert_document(
    conn,
    *,
    doc_id: str,
    title: str,
    subject: str,
    document_kind: str,
    filename: str,
    stored_path: Path,
    page_count: int,
    created_at: str,
) -> None:
    conn.execute(
        """
        INSERT INTO documents (id, title, subject, document_kind, filename, stored_path, page_count, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (doc_id, title, subject, document_kind, filename, str(stored_path), page_count, created_at),
    )


def imported_document_payload(
    *,
    doc_id: str,
    title: str,
    subject: str,
    document_kind: str,
    filename: str,
    questions: list[dict],
) -> dict:
    return {
        "document_id": doc_id,
        "title": title,
        "subject": subject,
        "document_kind": document_kind,
        "filename": filename,
        "page_count": len(questions),
        "questions": questions,
    }


def update_document(conn, doc_id: str, *, title: str, subject: str, document_kind: str):
    doc = conn.execute("SELECT id FROM documents WHERE id = ?", (doc_id,)).fetchone()
    if not doc:
        return None
    conn.execute(
        "UPDATE documents SET title = ?, subject = ?, document_kind = ? WHERE id = ?",
        (title, subject, document_kind, doc_id),
    )
    return conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()


def delete_question(conn, q_id: str, *, data_dir: Path) -> dict | None:
    row = conn.execute("SELECT document_id, image_path FROM questions WHERE id = ?", (q_id,)).fetchone()
    if not row:
        return None
    doc_id = row["document_id"]
    unlink_if_inside(data_dir, row["image_path"])
    conn.execute("DELETE FROM questions WHERE id = ?", (q_id,))
    remaining = conn.execute("SELECT COUNT(*) remaining FROM questions WHERE document_id = ?", (doc_id,)).fetchone()["remaining"]
    document_deleted = False
    if remaining == 0:
        doc = conn.execute("SELECT stored_path FROM documents WHERE id = ?", (doc_id,)).fetchone()
        if doc:
            unlink_if_inside(data_dir, doc["stored_path"])
        conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        document_deleted = True
    return {"ok": True, "document_id": doc_id, "document_deleted": document_deleted}


def delete_document(conn, doc_id: str, *, data_dir: Path) -> bool:
    doc = conn.execute("SELECT stored_path FROM documents WHERE id = ?", (doc_id,)).fetchone()
    if not doc:
        return False
    question_rows = conn.execute("SELECT image_path FROM questions WHERE document_id = ?", (doc_id,)).fetchall()
    for row in question_rows:
        unlink_if_inside(data_dir, row["image_path"])
    unlink_if_inside(data_dir, doc["stored_path"])
    conn.execute("DELETE FROM questions WHERE document_id = ?", (doc_id,))
    conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    return True
