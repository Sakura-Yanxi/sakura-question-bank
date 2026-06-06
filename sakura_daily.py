from __future__ import annotations

import uuid
from datetime import date, datetime


def parse_positive_int(value: str, fallback: int | None = None) -> int | None:
    try:
        parsed = int(str(value).strip())
        return parsed if parsed > 0 else fallback
    except (TypeError, ValueError):
        return fallback


def daily_rule_to_dict(row) -> dict:
    item = dict(row)
    item["enabled"] = bool(item.get("enabled"))
    item["limit_count"] = int(item.get("limit_count") or 5)
    return item


def load_daily_rules(conn, enabled_only: bool = False) -> list[dict]:
    where = "WHERE enabled = 1" if enabled_only else ""
    rows = conn.execute(
        f"SELECT * FROM daily_rules {where} ORDER BY enabled DESC, updated_at DESC, created_at DESC"
    ).fetchall()
    return [daily_rule_to_dict(row) for row in rows]


def save_daily_rule(conn, payload: dict) -> dict:
    now = datetime.now().isoformat(timespec="seconds")
    rule_id = str(payload.get("id") or uuid.uuid4().hex)
    limit_count = parse_positive_int(str(payload.get("limit_count", "")), 5) or 5
    limit_count = max(1, min(30, limit_count))
    status_group = str(payload.get("status_group") or "active_wrong")
    if status_group not in {"active_wrong", "due", "wrong", "review", "all_wrong_history"}:
        status_group = "active_wrong"
    values = {
        "id": rule_id,
        "name": str(payload.get("name") or "").strip()[:100],
        "enabled": 1 if payload.get("enabled", True) else 0,
        "document_id": str(payload.get("document_id") or "").strip(),
        "subject": str(payload.get("subject") or "").strip(),
        "category": str(payload.get("category") or "").strip(),
        "chapter": str(payload.get("chapter") or "").strip(),
        "status_group": status_group,
        "limit_count": limit_count,
        "created_at": now,
        "updated_at": now,
    }
    existing = conn.execute("SELECT created_at FROM daily_rules WHERE id = ?", (rule_id,)).fetchone()
    if existing:
        values["created_at"] = existing["created_at"]
    conn.execute(
        """
        INSERT INTO daily_rules (
            id, name, enabled, document_id, subject, category, chapter,
            status_group, limit_count, created_at, updated_at
        ) VALUES (
            :id, :name, :enabled, :document_id, :subject, :category, :chapter,
            :status_group, :limit_count, :created_at, :updated_at
        )
        ON CONFLICT(id) DO UPDATE SET
            name = excluded.name,
            enabled = excluded.enabled,
            document_id = excluded.document_id,
            subject = excluded.subject,
            category = excluded.category,
            chapter = excluded.chapter,
            status_group = excluded.status_group,
            limit_count = excluded.limit_count,
            updated_at = excluded.updated_at
        """,
        values,
    )
    row = conn.execute("SELECT * FROM daily_rules WHERE id = ?", (rule_id,)).fetchone()
    return daily_rule_to_dict(row)


def daily_rule_where(rule: dict, today_iso: str) -> tuple[str, list[str]]:
    clauses = []
    params: list[str] = []
    if rule.get("document_id"):
        clauses.append("q.document_id = ?")
        params.append(rule["document_id"])
    if rule.get("subject"):
        clauses.append("d.subject = ?")
        params.append(rule["subject"])
    if rule.get("category"):
        clauses.append("q.category = ?")
        params.append(rule["category"])
    if rule.get("chapter"):
        clauses.append("q.chapter = ?")
        params.append(rule["chapter"])
    status_group = rule.get("status_group") or "active_wrong"
    if status_group == "due":
        clauses.append(
            "(q.ever_wrong = 1 AND q.mastered_at IS NULL AND q.next_review_at IS NOT NULL AND date(q.next_review_at) <= date(?))"
        )
        params.append(today_iso)
    elif status_group == "wrong":
        clauses.append("q.status = '做错'")
    elif status_group == "review":
        clauses.append("q.status IN ('需复习', '半会')")
    elif status_group == "all_wrong_history":
        clauses.append("q.ever_wrong = 1")
    else:
        clauses.append(
            "(q.status IN ('做错', '需复习', '半会') OR (q.ever_wrong = 1 AND q.mastered_at IS NULL AND q.next_review_at IS NOT NULL AND date(q.next_review_at) <= date(?)))"
        )
        params.append(today_iso)
    return " AND ".join(clauses), params


def select_daily_questions_for_rule(conn, rule: dict, today_iso: str, used_ids: set[str], row_to_dict) -> list[dict]:
    where, params = daily_rule_where(rule, today_iso)
    if used_ids:
        where += f" AND q.id NOT IN ({','.join('?' for _ in used_ids)})"
        params.extend(list(used_ids))
    rows = conn.execute(
        f"""
        SELECT q.*, d.filename, d.title document_title, d.subject, d.document_kind
        FROM questions q
        JOIN documents d ON d.id = q.document_id
        WHERE {where}
        ORDER BY
            CASE q.status WHEN '做错' THEN 0 WHEN '需复习' THEN 1 WHEN '半会' THEN 2 ELSE 3 END,
            q.review_stage ASC,
            COALESCE(q.next_review_at, q.last_reviewed_at, q.created_at) ASC,
            q.page_number ASC
        LIMIT ?
        """,
        [*params, int(rule.get("limit_count") or 5)],
    ).fetchall()
    result = []
    for row in rows:
        item = row_to_dict(row)
        item["daily_kind"] = "custom"
        item["daily_rule_id"] = rule["id"]
        result.append(item)
    return result


def build_custom_daily_groups(conn, row_to_dict) -> tuple[list[dict], list[dict]]:
    today_iso = date.today().isoformat()
    rules = load_daily_rules(conn, enabled_only=True)
    groups = []
    used_ids: set[str] = set()
    for rule in rules:
        questions = select_daily_questions_for_rule(conn, rule, today_iso, used_ids, row_to_dict)
        for q in questions:
            used_ids.add(q["id"])
        if questions:
            title = rule.get("name") or "自定义错题推送"
            groups.append({"title": title, "rule": rule, "questions": questions})
    return groups, rules


def daily_rule_option_where(query: dict, skip: str = "") -> tuple[str, list[str]]:
    clauses = []
    params: list[str] = []
    mapping = {
        "document_id": "q.document_id",
        "subject": "d.subject",
        "category": "q.category",
        "chapter": "q.chapter",
    }
    for key, column in mapping.items():
        if key == skip:
            continue
        value = query.get(key, [""])[0].strip()
        if value:
            clauses.append(f"{column} = ?")
            params.append(value)
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    return where, params


def get_daily_rule_options(conn, query: dict, document_to_dict) -> dict:
    doc_where, doc_params = daily_rule_option_where(query, skip="document_id")
    subject_where, subject_params = daily_rule_option_where(query, skip="subject")
    category_where, category_params = daily_rule_option_where(query, skip="category")
    chapter_where, chapter_params = daily_rule_option_where(query, skip="chapter")

    documents = [
        document_to_dict(row)
        for row in conn.execute(
            f"""
            SELECT DISTINCT d.*
            FROM documents d
            JOIN questions q ON q.document_id = d.id
            {doc_where}
            ORDER BY d.subject ASC, COALESCE(NULLIF(d.title, ''), d.filename) ASC
            """,
            doc_params,
        ).fetchall()
    ]
    subjects = [
        row["subject"]
        for row in conn.execute(
            f"""
            SELECT d.subject, MIN(q.page_number) first_page
            FROM questions q
            JOIN documents d ON d.id = q.document_id
            {subject_where}
            GROUP BY d.subject
            HAVING d.subject <> ''
            ORDER BY first_page ASC, d.subject ASC
            """,
            subject_params,
        ).fetchall()
    ]
    categories = [
        row["category"]
        for row in conn.execute(
            f"""
            SELECT q.category, MIN(q.page_number) first_page
            FROM questions q
            JOIN documents d ON d.id = q.document_id
            {category_where}
            GROUP BY q.category
            HAVING q.category <> ''
            ORDER BY first_page ASC, q.category ASC
            """,
            category_params,
        ).fetchall()
    ]
    chapters = [
        row["chapter"]
        for row in conn.execute(
            f"""
            SELECT q.chapter, MIN(q.page_number) first_page
            FROM questions q
            JOIN documents d ON d.id = q.document_id
            {chapter_where}
            GROUP BY q.chapter
            HAVING q.chapter <> ''
            ORDER BY first_page ASC, q.chapter ASC
            """,
            chapter_params,
        ).fetchall()
    ]
    return {"documents": documents, "subjects": subjects, "categories": categories, "chapters": chapters}


def build_daily_payload(
    conn,
    *,
    row_to_dict,
    weak_chapter_dependencies,
    find_foundation_questions,
    default_subject: str,
    default_document_kind: str,
) -> dict:
    today = date.today().isoformat()
    custom_groups, custom_rules = build_custom_daily_groups(conn, row_to_dict)
    if custom_rules:
        groups = custom_groups
        return {
            "date": today,
            "groups": groups,
            "plan": [question for group in groups for question in group["questions"]],
            "custom_rules": custom_rules,
            "message": "已启用自定义每日练习规则；系统会按做题本、科目、知识点和章节筛选错题。",
        }

    rows = conn.execute(
        """
        SELECT q.*, d.filename, d.title document_title, d.subject, d.document_kind
        FROM questions q
        JOIN documents d ON d.id = q.document_id
        WHERE q.status IN ('做错', '需复习', '半会')
           OR (
               q.ever_wrong = 1
               AND q.mastered_at IS NULL
               AND q.next_review_at IS NOT NULL
               AND date(q.next_review_at) <= date(?)
           )
        ORDER BY
            d.subject ASC,
            COALESCE(NULLIF(d.title, ''), d.filename) ASC,
            CASE q.status
                WHEN '做错' THEN 0
                WHEN '需复习' THEN 1
                WHEN '半会' THEN 2
                WHEN '做对' THEN 3
                ELSE 4
            END,
            q.review_stage ASC,
            COALESCE(q.next_review_at, q.last_reviewed_at, q.created_at) ASC
        """,
        (today,),
    ).fetchall()
    dependency_map = weak_chapter_dependencies(conn)
    groups_map: dict[str, dict] = {}
    used_ids: set[str] = set()
    for row in rows:
        item = row_to_dict(row)
        item["daily_kind"] = "review"
        used_ids.add(item["id"])
        book_name = item.get("document_title") or item.get("filename") or "做题本"
        group_key = f"{item.get('subject') or default_subject} / {item.get('document_kind') or default_document_kind} / {book_name}"
        if group_key not in groups_map:
            groups_map[group_key] = {"title": group_key, "questions": []}
        if len(groups_map[group_key]["questions"]) < 4:
            groups_map[group_key]["questions"].append(item)
    for group_key, dependencies in dependency_map.items():
        if group_key not in groups_map or len(groups_map[group_key]["questions"]) >= 5:
            continue
        subject = group_key.split(" / ", 1)[0]
        foundations = find_foundation_questions(conn, subject, dependencies, used_ids)
        if foundations:
            groups_map[group_key]["questions"].append(foundations[0])
            used_ids.add(foundations[0]["id"])
    groups = [group for group in groups_map.values() if group["questions"]]
    return {
        "date": today,
        "groups": groups,
        "plan": [question for group in groups for question in group["questions"]],
        "message": "每日练习由当前错题、到期复习题和低正确率章节的前置基础题组成；每组最多 5 道，其中约 20% 用于补基础。",
    }


def create_practice_batch(conn, payload_builder, source: str = "push") -> dict:
    payload = payload_builder(conn)
    questions = payload.get("plan") or []
    now = datetime.now().isoformat(timespec="seconds")
    batch_id = uuid.uuid4().hex
    title = f"{date.today().isoformat()} 每日错题回填"
    conn.execute(
        "INSERT INTO practice_batches (id, day, source, title, created_at) VALUES (?, ?, ?, ?, ?)",
        (batch_id, date.today().isoformat(), source, title, now),
    )
    for index, question in enumerate(questions, start=1):
        conn.execute(
            """
            INSERT OR IGNORE INTO practice_batch_items (batch_id, question_id, position)
            VALUES (?, ?, ?)
            """,
            (batch_id, question["id"], index),
        )
    return {"id": batch_id, "title": title, "question_count": len(questions), "payload": payload}


def practice_batch_payload(conn, batch_id: str, row_to_dict) -> dict | None:
    batch = conn.execute("SELECT * FROM practice_batches WHERE id = ?", (batch_id,)).fetchone()
    if not batch:
        return None
    rows = conn.execute(
        """
        SELECT
            p.position, p.quick_status, p.quick_note, p.completed_at batch_completed_at,
            q.id, q.document_id, q.page_number, q.seq_no, q.question_no, q.image_path,
            q.ocr_text, q.category, q.subcategory, q.chapter, q.difficulty, q.status,
            q.user_note, q.meta_tags, q.ever_wrong, q.review_stage, q.next_review_at,
            q.retention_stage, q.mastered_at,
            d.filename, d.title document_title, d.subject, d.document_kind
        FROM practice_batch_items p
        JOIN questions q ON q.id = p.question_id
        JOIN documents d ON d.id = q.document_id
        WHERE p.batch_id = ?
        ORDER BY p.position ASC
        """,
        (batch_id,),
    ).fetchall()
    questions = []
    for row in rows:
        item = row_to_dict(row)
        item["batch_position"] = row["position"]
        item["quick_status"] = row["quick_status"]
        item["quick_note"] = row["quick_note"]
        item["batch_completed_at"] = row["batch_completed_at"]
        questions.append(item)
    done = sum(1 for item in questions if item.get("quick_status"))
    batch_dict = dict(batch)
    batch_dict["question_count"] = len(questions)
    batch_dict["done_count"] = done
    return {"batch": batch_dict, "questions": questions}


def apply_practice_feedback(conn, batch_id: str, q_id: str, status: str, note: str, normalize_label, schedule_for_status, row_to_dict) -> dict:
    status = normalize_label(status, "")
    if status not in {"做对", "做错", "半会", "需复习"}:
        raise ValueError("状态只能是：做对、做错、半会、需复习。")
    current = conn.execute("SELECT * FROM questions WHERE id = ?", (q_id,)).fetchone()
    if not current:
        raise ValueError("题目不存在。")
    item = conn.execute(
        "SELECT 1 FROM practice_batch_items WHERE batch_id = ? AND question_id = ?",
        (batch_id, q_id),
    ).fetchone()
    if not item:
        raise ValueError("这道题不属于当前推送批次。")
    now = datetime.now()
    updates = {
        "status": status,
        "user_note": note.strip()[:1000] or current["user_note"],
        "last_reviewed_at": now.isoformat(timespec="seconds"),
        "review_count": "review_count + 1",
    }
    updates.update(schedule_for_status(current, status, now))
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
    completed_at = now.isoformat(timespec="seconds")
    conn.execute(
        """
        UPDATE practice_batch_items
        SET quick_status = ?, quick_note = ?, completed_at = ?
        WHERE batch_id = ? AND question_id = ?
        """,
        (status, note.strip()[:1000], completed_at, batch_id, q_id),
    )
    remaining = conn.execute(
        "SELECT COUNT(*) n FROM practice_batch_items WHERE batch_id = ? AND quick_status = ''",
        (batch_id,),
    ).fetchone()["n"]
    if remaining == 0:
        conn.execute("UPDATE practice_batches SET completed_at = ? WHERE id = ?", (completed_at, batch_id))
    row = conn.execute(
        """
        SELECT q.*, d.filename, d.title document_title, d.subject, d.document_kind
        FROM questions q
        JOIN documents d ON d.id = q.document_id
        WHERE q.id = ?
        """,
        (q_id,),
    ).fetchone()
    return row_to_dict(row) | {"quick_status": status, "quick_note": note.strip()[:1000], "remaining": remaining}
