from __future__ import annotations

import uuid
from datetime import date, datetime


STATUS_WRONG = "\u505a\u9519"
STATUS_REVIEW = "\u9700\u590d\u4e60"
STATUS_HALF = "\u534a\u4f1a"
STATUS_RIGHT = "\u505a\u5bf9"
WRONGISH_STATUSES = (STATUS_WRONG, STATUS_REVIEW, STATUS_HALF)
MIN_DAILY_LIMIT = 1
MAX_DAILY_LIMIT = 80


def parse_positive_int(value: str, fallback: int | None = None) -> int | None:
    try:
        parsed = int(str(value).strip())
        return parsed if parsed > 0 else fallback
    except (TypeError, ValueError):
        return fallback


def normalize_daily_limit(value: int | str, default: int = 20) -> int:
    parsed = parse_positive_int(str(value), default) or default
    return max(MIN_DAILY_LIMIT, min(MAX_DAILY_LIMIT, parsed))


def flatten_daily_groups(groups: list[dict]) -> list[dict]:
    return [question for group in groups for question in group.get("questions") or []]


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


def delete_daily_rule(conn, rule_id: str) -> bool:
    row = conn.execute("SELECT id FROM daily_rules WHERE id = ?", (rule_id,)).fetchone()
    if not row:
        return False
    conn.execute("DELETE FROM daily_rules WHERE id = ?", (rule_id,))
    return True


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
        clauses.append("q.status = ?")
        params.append(STATUS_WRONG)
    elif status_group == "review":
        clauses.append("q.status IN (?, ?)")
        params.extend([STATUS_REVIEW, STATUS_HALF])
    elif status_group == "all_wrong_history":
        clauses.append("q.ever_wrong = 1")
    else:
        clauses.append(
            "(q.status IN (?, ?, ?) OR (q.ever_wrong = 1 AND q.mastered_at IS NULL AND q.next_review_at IS NOT NULL AND date(q.next_review_at) <= date(?)))"
        )
        params.extend(WRONGISH_STATUSES)
        params.append(today_iso)
    return " AND ".join(clauses), params

def select_daily_questions_for_rule(conn, rule: dict, today_iso: str, used_ids: set[str], row_to_dict) -> list[dict]:
    where, params = daily_rule_where(rule, today_iso)
    if used_ids:
        where += f" AND q.id NOT IN ({','.join('?' for _ in used_ids)})"
        params.extend(list(used_ids))

    broad_scope = not rule.get("category") and not rule.get("chapter")
    weak_order = "COALESCE(chapter_accuracy, 0.5) ASC, ABS(RANDOM()) ASC," if broad_scope else ""
    attempted = f"'{STATUS_RIGHT}', '{STATUS_WRONG}', '{STATUS_REVIEW}', '{STATUS_HALF}'"
    rows = conn.execute(
        f"""
        SELECT
            q.*, d.filename, d.title document_title, d.subject, d.document_kind,
            (
                SELECT SUM(CASE WHEN qs.status = '{STATUS_RIGHT}' THEN 1 ELSE 0 END) * 1.0
                       / NULLIF(SUM(CASE WHEN qs.status IN ({attempted}) THEN 1 ELSE 0 END), 0)
                FROM questions qs
                WHERE qs.document_id = q.document_id
                  AND COALESCE(qs.chapter, '') = COALESCE(q.chapter, '')
            ) chapter_accuracy
        FROM questions q
        JOIN documents d ON d.id = q.document_id
        WHERE {where}
        ORDER BY
            {weak_order}
            CASE q.status WHEN '{STATUS_WRONG}' THEN 0 WHEN '{STATUS_REVIEW}' THEN 1 WHEN '{STATUS_HALF}' THEN 2 ELSE 3 END,
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
        item["chapter_accuracy"] = row["chapter_accuracy"]
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


def limit_daily_groups(groups: list[dict], max_count: int) -> tuple[list[dict], list[dict], int]:
    max_count = normalize_daily_limit(max_count)
    available = len(flatten_daily_groups(groups))
    if available <= max_count:
        return groups, flatten_daily_groups(groups), available

    limited_groups = []
    plan = []
    remaining = max_count
    for group in groups:
        if remaining <= 0:
            break
        questions = list(group.get("questions") or [])
        kept = questions[:remaining]
        if kept:
            limited_group = dict(group)
            limited_group["questions"] = kept
            limited_groups.append(limited_group)
            plan.extend(kept)
            remaining -= len(kept)
    return limited_groups, plan, available


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
    daily_scope: str = "active_wrong",
    daily_limit: int = 20,
) -> dict:
    today = date.today().isoformat()
    daily_limit = normalize_daily_limit(daily_limit)
    custom_groups, custom_rules = build_custom_daily_groups(conn, row_to_dict)
    if custom_rules:
        groups, plan, available_count = limit_daily_groups(custom_groups, daily_limit)
        capped = available_count > daily_limit
        message = (
            f"\u5df2\u542f\u7528\u81ea\u5b9a\u4e49\u6bcf\u65e5\u7ec3\u4e60\u89c4\u5219\uff1b\u89c4\u5219\u5408\u8ba1\u5339\u914d {available_count} \u9053\uff0c\u672c\u6b21\u6309\u6bcf\u65e5\u603b\u4e0a\u9650\u63a8\u9001 {len(plan)} \u9053\u3002"
            if plan
            else "\u5df2\u542f\u7528\u81ea\u5b9a\u4e49\u6bcf\u65e5\u7ec3\u4e60\u89c4\u5219\uff0c\u4f46\u4eca\u65e5\u6ca1\u6709\u5339\u914d\u9898\u76ee\uff1b\u53ef\u4ee5\u6362\u7ae0\u8282\u3001\u53d6\u6d88\u7ae0\u8282\u9650\u5236\uff0c\u6216\u628a\u63a8\u9001\u8303\u56f4\u6539\u6210\u201c\u5386\u53f2\u66fe\u9519\u9898\u201d\u3002"
        )
        return {
            "date": today,
            "groups": groups,
            "plan": plan,
            "custom_rules": custom_rules,
            "scope": "custom_rules",
            "limit": daily_limit,
            "available_count": available_count,
            "capped": capped,
            "message": message,
        }

    if daily_scope == "due":
        where_clause = """
        q.ever_wrong = 1
        AND q.mastered_at IS NULL
        AND q.next_review_at IS NOT NULL
        AND date(q.next_review_at) <= date(?)
        """
        params = (today,)
        scope_message = "\u672c\u6b21\u63a8\u9001\u4ec5\u5305\u542b\u827e\u5bbe\u6d69\u65af\u5230\u671f\u590d\u4e60\u9898\u3002"
    elif daily_scope == "all_wrong_history":
        where_clause = "q.ever_wrong = 1"
        params = ()
        scope_message = "\u672c\u6b21\u63a8\u9001\u5305\u542b\u5386\u53f2\u66fe\u9519\u9898\uff0c\u9002\u5408\u5468\u672b\u6216\u96c6\u4e2d\u590d\u76d8\u3002"
    else:
        daily_scope = "active_wrong"
        where_clause = """
        q.status IN ('\u505a\u9519', '\u9700\u590d\u4e60', '\u534a\u4f1a')
        OR (
            q.ever_wrong = 1
            AND q.mastered_at IS NULL
            AND q.next_review_at IS NOT NULL
            AND date(q.next_review_at) <= date(?)
        )
        """
        params = (today,)
        scope_message = "\u672c\u6b21\u63a8\u9001\u5305\u542b\u5f53\u524d\u9519\u9898\u3001\u9700\u590d\u4e60\u9898\u548c\u5230\u671f\u9898\u3002"

    available_count = conn.execute(
        f"""
        SELECT COUNT(*)
        FROM questions q
        JOIN documents d ON d.id = q.document_id
        WHERE {where_clause}
        """,
        params,
    ).fetchone()[0]

    rows = conn.execute(
        f"""
        SELECT q.*, d.filename, d.title document_title, d.subject, d.document_kind
        FROM questions q
        JOIN documents d ON d.id = q.document_id
        WHERE {where_clause}
        ORDER BY
            d.subject ASC,
            COALESCE(NULLIF(d.title, ''), d.filename) ASC,
            CASE q.status
                WHEN '\u505a\u9519' THEN 0
                WHEN '\u9700\u590d\u4e60' THEN 1
                WHEN '\u534a\u4f1a' THEN 2
                WHEN '\u505a\u5bf9' THEN 3
                ELSE 4
            END,
            q.review_stage ASC,
            COALESCE(q.next_review_at, q.last_reviewed_at, q.created_at) ASC,
            q.page_number ASC
        LIMIT ?
        """,
        (*params, daily_limit),
    ).fetchall()
    dependency_map = weak_chapter_dependencies(conn)
    groups_map: dict[str, dict] = {}
    used_ids: set[str] = set()
    for row in rows:
        item = row_to_dict(row)
        item["daily_kind"] = "review"
        used_ids.add(item["id"])
        book_name = item.get("document_title") or item.get("filename") or "\u505a\u9898\u672c"
        group_key = f"{item.get('subject') or default_subject} / {item.get('document_kind') or default_document_kind} / {book_name}"
        if group_key not in groups_map:
            groups_map[group_key] = {"title": group_key, "questions": []}
        groups_map[group_key]["questions"].append(item)
    for group_key, dependencies in dependency_map.items():
        if daily_scope == "all_wrong_history" or len(used_ids) >= daily_limit:
            continue
        if group_key not in groups_map:
            continue
        subject = group_key.split(" / ", 1)[0]
        foundations = find_foundation_questions(conn, subject, dependencies, used_ids)
        if foundations:
            groups_map[group_key]["questions"].append(foundations[0])
            used_ids.add(foundations[0]["id"])
    groups = [group for group in groups_map.values() if group["questions"]]
    plan = [question for group in groups for question in group["questions"]][:daily_limit]
    return {
        "date": today,
        "groups": groups,
        "plan": plan,
        "scope": daily_scope,
        "limit": daily_limit,
        "available_count": available_count,
        "capped": available_count > daily_limit,
        "message": f"{scope_message} \u6700\u591a\u63a8\u9001 {daily_limit} \u9053\uff1b\u82e5\u9009\u62e9\u4f01\u4e1a\u5fae\u4fe1\u6216\u90ae\u7bb1\uff0c\u4f1a\u968f\u63a8\u9001\u9644\u5e26 PDF\u3002",
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


def latest_daily_push_batch_payload(conn, row_to_dict) -> dict | None:
    today = date.today().isoformat()
    batch = conn.execute(
        """
        SELECT b.id, b.day
        FROM practice_batches b
        JOIN practice_batch_items i ON i.batch_id = b.id
        WHERE b.source IN ('daily_push', 'push')
        GROUP BY b.id
        ORDER BY
            CASE WHEN b.day = ? THEN 0 ELSE 1 END,
            b.created_at DESC
        LIMIT 1
        """,
        (today,),
    ).fetchone()
    if not batch:
        return None
    payload = practice_batch_payload(conn, batch["id"], row_to_dict)
    if payload and payload.get("batch"):
        payload["is_today"] = payload["batch"].get("day") == today
    return payload


def apply_practice_feedback(
    conn,
    batch_id: str,
    q_id: str,
    status: str,
    note: str,
    normalize_label,
    schedule_for_status,
    row_to_dict,
    insert_review_note=None,
) -> dict:
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
    clean_note = note.strip()[:1000]
    updates = {
        "status": status,
        "user_note": clean_note or current["user_note"],
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
        (status, clean_note, completed_at, batch_id, q_id),
    )
    if insert_review_note and clean_note:
        insert_review_note(
            conn,
            q_id,
            status=status,
            note=clean_note,
            meta_tags=current["meta_tags"],
            source="daily",
            created_at=completed_at,
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
    return row_to_dict(row) | {"quick_status": status, "quick_note": clean_note, "remaining": remaining}
