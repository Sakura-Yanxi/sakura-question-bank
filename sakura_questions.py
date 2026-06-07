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
