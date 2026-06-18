from __future__ import annotations


def query_values(query: dict, key: str) -> list[str]:
    raw_values = query.get(key, [])
    if not isinstance(raw_values, (list, tuple)):
        raw_values = [raw_values]
    values: list[str] = []
    seen: set[str] = set()
    for raw in raw_values:
        value = str(raw or "").strip()
        if value and value not in seen:
            values.append(value)
            seen.add(value)
    return values


def get_filter_options(conn) -> dict:
    subjects = [
        row["subject"]
        for row in conn.execute(
            "SELECT DISTINCT subject FROM documents WHERE subject <> '' ORDER BY subject"
        ).fetchall()
    ]
    categories = [
        row["category"]
        for row in conn.execute(
            """
            SELECT category, MIN(page_number) first_page
            FROM questions
            WHERE category <> ''
            GROUP BY category
            ORDER BY first_page ASC, category ASC
            """
        ).fetchall()
    ]
    chapters = [
        row["chapter"]
        for row in conn.execute(
            """
            SELECT chapter, MIN(page_number) first_page
            FROM questions
            WHERE chapter <> ''
            GROUP BY chapter
            ORDER BY first_page ASC, chapter ASC
            """
        ).fetchall()
    ]
    return {"subjects": subjects, "categories": categories, "chapters": chapters}


def build_question_filters(query: dict, keys: tuple[str, ...]) -> tuple[str, list[str]]:
    clauses = []
    params: list[str] = []
    for key in ("category", "status", "document_id", "chapter"):
        values = query_values(query, key)
        if values and key in keys:
            if len(values) == 1:
                clauses.append(f"q.{key} = ?")
            else:
                clauses.append(f"q.{key} IN ({','.join('?' for _ in values)})")
            params.extend(values)
    subject = next(iter(query_values(query, "subject")), "")
    if subject and "subject" in keys:
        clauses.append("d.subject = ?")
        params.append(subject)
    document_kind = next(iter(query_values(query, "document_kind")), "")
    if document_kind and "document_kind" in keys:
        clauses.append("d.document_kind = ?")
        params.append(document_kind)
    status_group = next(iter(query_values(query, "status_group")), "")
    if status_group == "review" and "status_group" in keys:
        clauses.append(
            "(q.status IN ('半会', '需复习') OR (q.ever_wrong = 1 AND q.mastered_at IS NULL AND COALESCE(q.status, '') <> '做错'))"
        )
    search = next(iter(query_values(query, "search")), "")
    if search and "search" in keys:
        clauses.append(
            """
            (
                q.question_no LIKE ?
                OR q.ocr_text LIKE ?
                OR q.category LIKE ?
                OR q.subcategory LIKE ?
                OR q.chapter LIKE ?
                OR q.mistake_reason LIKE ?
                OR q.meta_tags LIKE ?
                OR q.user_note LIKE ?
            )
            """
        )
        params.extend([f"%{search}%"] * 8)
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    return where, params


def get_scoped_filter_options(conn, query: dict) -> dict:
    subjects = [
        row["subject"]
        for row in conn.execute(
            "SELECT DISTINCT subject FROM documents WHERE subject <> '' ORDER BY subject"
        ).fetchall()
    ]
    category_where, category_params = build_question_filters(
        query,
        ("status", "status_group", "document_id", "chapter", "subject", "document_kind", "search"),
    )
    category_where = f"{category_where} AND q.category <> ''" if category_where else "WHERE q.category <> ''"
    categories = [
        row["category"]
        for row in conn.execute(
            f"""
            SELECT q.category, MIN(q.page_number) first_page
            FROM questions q
            JOIN documents d ON d.id = q.document_id
            {category_where}
            GROUP BY q.category
            ORDER BY first_page ASC, q.category ASC
            """,
            category_params,
        ).fetchall()
    ]
    chapter_where, chapter_params = build_question_filters(
        query,
        ("category", "status", "status_group", "document_id", "subject", "document_kind", "search"),
    )
    chapter_where = f"{chapter_where} AND q.chapter <> ''" if chapter_where else "WHERE q.chapter <> ''"
    chapters = [
        row["chapter"]
        for row in conn.execute(
            f"""
            SELECT q.chapter, MIN(q.page_number) first_page
            FROM questions q
            JOIN documents d ON d.id = q.document_id
            {chapter_where}
            GROUP BY q.chapter
            ORDER BY first_page ASC, q.chapter ASC
            """,
            chapter_params,
        ).fetchall()
    ]
    return {"subjects": subjects, "categories": categories, "chapters": chapters}
