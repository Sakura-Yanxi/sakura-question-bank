from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timedelta


def period_bounds(period: str, today: date | None = None) -> tuple[date, date]:
    today = today or date.today()
    if period == "month":
        start = today.replace(day=1)
    else:
        start = today - timedelta(days=today.weekday())
    return start, today


def build_reflection_payload(conn, period: str) -> dict:
    start_date, end_date = period_bounds(period)
    start_iso = start_date.isoformat()
    end_iso = end_date.isoformat()
    days = (end_date - start_date).days + 1
    rows = conn.execute(
        """
        SELECT q.*, d.title document_title, d.subject, d.document_kind
        FROM questions q
        JOIN documents d ON d.id = q.document_id
        WHERE q.last_reviewed_at IS NOT NULL
          AND q.status <> '未做'
          AND date(q.last_reviewed_at) >= date(?)
          AND date(q.last_reviewed_at) <= date(?)
        ORDER BY q.last_reviewed_at DESC
        """,
        (start_iso, end_iso),
    ).fetchall()
    subject_stats = conn.execute(
        """
        SELECT d.subject,
               COUNT(*) total,
               SUM(CASE WHEN q.status = '做对' THEN 1 ELSE 0 END) correct,
               SUM(CASE WHEN q.status = '做错' THEN 1 ELSE 0 END) wrong,
               SUM(CASE WHEN q.status IN ('半会', '需复习') THEN 1 ELSE 0 END) review
        FROM questions q
        JOIN documents d ON d.id = q.document_id
        WHERE q.last_reviewed_at IS NOT NULL
          AND q.status <> '未做'
          AND date(q.last_reviewed_at) >= date(?)
          AND date(q.last_reviewed_at) <= date(?)
        GROUP BY d.subject
        ORDER BY total DESC, wrong DESC, review DESC
        """,
        (start_iso, end_iso),
    ).fetchall()
    chapter_stats = conn.execute(
        """
        SELECT d.subject, q.chapter, q.category,
               COUNT(*) total,
               SUM(CASE WHEN q.status = '做对' THEN 1 ELSE 0 END) correct,
               SUM(CASE WHEN q.status = '做错' THEN 1 ELSE 0 END) wrong,
               SUM(CASE WHEN q.status IN ('半会', '需复习') THEN 1 ELSE 0 END) review
        FROM questions q
        JOIN documents d ON d.id = q.document_id
        WHERE q.last_reviewed_at IS NOT NULL
          AND q.status <> '未做'
          AND date(q.last_reviewed_at) >= date(?)
          AND date(q.last_reviewed_at) <= date(?)
        GROUP BY d.subject, q.chapter, q.category
        ORDER BY wrong DESC, review DESC, total DESC
        LIMIT 18
        """,
        (start_iso, end_iso),
    ).fetchall()
    questions = [dict(row) for row in rows]
    wrong_questions = [q for q in questions if q["status"] in {"做错", "半会", "需复习"}]
    return {
        "period": period,
        "days": days,
        "total": len(questions),
        "correct": sum(1 for q in questions if q["status"] == "做对"),
        "wrong": sum(1 for q in questions if q["status"] == "做错"),
        "review": sum(1 for q in questions if q["status"] in {"半会", "需复习"}),
        "subjects": [dict(row) for row in subject_stats],
        "chapters": [dict(row) for row in chapter_stats],
        "wrong_questions": wrong_questions[:15],
    }


def save_reflection(conn, period: str, summary: dict, reflection: str) -> str:
    start, end = period_bounds(period)
    ref_id = uuid.uuid4().hex
    conn.execute(
        "INSERT INTO reflections (id, period, period_start, period_end, summary_json, reflection_text, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            ref_id,
            period,
            start.isoformat(),
            end.isoformat(),
            json.dumps(summary, ensure_ascii=False, default=str),
            reflection,
            datetime.now().isoformat(),
        ),
    )
    return ref_id


def list_reflections(conn, limit: int = 30) -> list[dict]:
    rows = conn.execute(
        """
        SELECT id, period, period_start, period_end, summary_json, reflection_text, created_at
        FROM reflections
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        try:
            item["summary"] = json.loads(item.pop("summary_json"))
        except (json.JSONDecodeError, TypeError):
            item["summary"] = {}
        item["delete_url"] = f"/api/reflections/{item['id']}"
        items.append(item)
    return items


def delete_reflection(conn, ref_id: str) -> bool:
    row = conn.execute("SELECT id FROM reflections WHERE id = ?", (ref_id,)).fetchone()
    if not row:
        return False
    conn.execute("DELETE FROM reflections WHERE id = ?", (ref_id,))
    return True


def build_reflection_download(conn, ref_id: str) -> tuple[str, str] | None:
    row = conn.execute(
        "SELECT id, period, period_start, period_end, reflection_text, created_at FROM reflections WHERE id = ?",
        (ref_id,),
    ).fetchone()
    if not row:
        return None
    lines_out = [
        "# 历史知识归档",
        "",
        f"周期：{row['period']}（{row['period_start']} ~ {row['period_end']}）",
        f"生成时间：{row['created_at']}",
        "",
        "---",
        "",
        row["reflection_text"],
    ]
    text = "\n".join(lines_out)
    filename = f"reflection_{row['period_start']}_{row['period_end']}.txt"
    return filename, text


def local_reflection(payload: dict) -> str:
    weak = payload["chapters"][:5]
    subject_lines = "\n".join(
        f"- {item['subject']}：做题 {item['total']}，做对 {item['correct'] or 0}，做错 {item['wrong'] or 0}，需复习 {item['review'] or 0}"
        for item in payload.get("subjects", [])
    ) or "- 本周期还没有已标记的做题记录。"
    weak_lines = "\n".join(
        f"- {item['subject']} / {item['chapter']}：错题 {item['wrong'] or 0}，需复习 {item['review'] or 0}"
        for item in weak
    ) or "- 暂无明显薄弱章节。"
    return (
        f"{'本月' if payload['period'] == 'month' else '本周'}总结与反思\n"
        f"共完成/复盘 {payload['total']} 道题，做对 {payload['correct']}，做错 {payload['wrong']}，需复习 {payload['review']}。\n\n"
        "科目统计：\n"
        f"{subject_lines}\n\n"
        "当前薄弱点：\n"
        f"{weak_lines}\n\n"
        "建议：优先复盘本周期错题集中的高频章节，再补 2-3 道同章节基础题和 1 道变式题。"
    )


def reflection_prompt(payload: dict) -> str:
    compact_wrong = [
        {
            "subject": q.get("subject"),
            "chapter": q.get("chapter"),
            "category": q.get("category"),
            "status": q.get("status"),
            "mistake_reason": q.get("mistake_reason"),
            "user_note": q.get("user_note"),
            "text": (q.get("ocr_text") or "")[:300],
        }
        for q in payload["wrong_questions"]
    ]
    return f"""
你是学习复盘教练。请根据下面的做题记录生成中文总结与反思。
周期：{'本月' if payload['period'] == 'month' else '本周'}
统计口径：只统计本周期内被标记为做对、做错、半会或需复习的题目，不把单纯导入但未做的题目计入。
总统计：完成/复盘 {payload['total']}，做对 {payload['correct']}，做错 {payload['wrong']}，需复习 {payload['review']}
科目统计：
{json.dumps(payload.get('subjects', []), ensure_ascii=False)}
章节统计：
{json.dumps(payload['chapters'], ensure_ascii=False)}
代表性错题：
{json.dumps(compact_wrong, ensure_ascii=False)}

请输出：
1. 本周期学习内容概览，必须按科目分别说明
2. 重难点与薄弱章节
3. 错题暴露出的具体不足
4. 下个周期规划，包含优先级和练习建议
5. 需要警惕的做题习惯问题
"""


def generate_reflection(payload: dict, *, llm_enabled: bool, call_llm) -> str:
    if payload.get("force_local") or not llm_enabled:
        return local_reflection(payload)
    try:
        return call_llm(reflection_prompt(payload), temperature=0.35) or local_reflection(payload)
    except Exception:
        return local_reflection(payload)
