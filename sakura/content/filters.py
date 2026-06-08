from __future__ import annotations


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
        value = query.get(key, [""])[0]
        if value and key in keys:
            clauses.append(f"q.{key} = ?")
            params.append(value)
    subject = query.get("subject", [""])[0]
    if subject and "subject" in keys:
        clauses.append("d.subject = ?")
        params.append(subject)
    search = query.get("search", [""])[0].strip()
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
        ("status", "document_id", "chapter", "subject", "search"),
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
        ("category", "status", "document_id", "subject", "search"),
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
