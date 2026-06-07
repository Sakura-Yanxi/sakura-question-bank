from __future__ import annotations


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
