from __future__ import annotations

import json
import re
import uuid
from datetime import datetime


def load_teacher_memories(conn, limit: int = 10) -> list[dict]:
    rows = conn.execute(
        "SELECT id, content, source, created_at FROM teacher_memory ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def save_teacher_memory(conn, content: str, source: str = "chat") -> dict:
    content = (content or "").strip()
    if not content:
        raise ValueError("记忆内容不能为空")
    memory = {
        "id": uuid.uuid4().hex,
        "content": content[:2000],
        "source": (source or "chat")[:30],
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    conn.execute(
        "INSERT INTO teacher_memory (id, content, source, created_at) VALUES (?, ?, ?, ?)",
        (memory["id"], memory["content"], memory["source"], memory["created_at"]),
    )
    return memory


def delete_teacher_memory(conn, memory_id: str) -> bool:
    row = conn.execute("SELECT id FROM teacher_memory WHERE id = ?", (memory_id,)).fetchone()
    if not row:
        return False
    conn.execute("DELETE FROM teacher_memory WHERE id = ?", (memory_id,))
    return True


def teacher_memory_prompt(conn) -> str:
    memories = load_teacher_memories(conn, limit=8)
    if not memories:
        return "暂无主动导入的对话记忆。"
    return "\n".join(f"- {item['content']}" for item in memories)


def parse_tags(value) -> list[str]:
    if isinstance(value, list):
        raw = value
    else:
        text = str(value or "").strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
            raw = parsed if isinstance(parsed, list) else re.split(r"[,，、\s]+", text)
        except json.JSONDecodeError:
            raw = re.split(r"[,，、\s]+", text)
    return [str(item).strip()[:30] for item in raw if str(item).strip()][:12]


def mentor_experience_to_dict(row) -> dict:
    item = dict(row)
    try:
        item["tags"] = json.loads(item.get("tags") or "[]")
    except (TypeError, json.JSONDecodeError):
        item["tags"] = []
    return item


def load_mentor_experiences(conn, limit: int = 30) -> list[dict]:
    rows = conn.execute(
        """
        SELECT * FROM mentor_experience
        ORDER BY reliability DESC, created_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [mentor_experience_to_dict(row) for row in rows]


def parse_reliability(value, fallback: int = 3) -> int:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        parsed = fallback
    return max(1, min(5, parsed))


def save_mentor_experience(conn, payload: dict) -> dict:
    content = str(payload.get("content", "")).strip()
    if not content:
        raise ValueError("经验内容不能为空")
    item = {
        "id": uuid.uuid4().hex,
        "title": str(payload.get("title", "")).strip()[:80],
        "content": content[:3000],
        "subject": str(payload.get("subject", "")).strip()[:60],
        "tags": parse_tags(payload.get("tags", "")),
        "source": str(payload.get("source", "")).strip()[:80],
        "reliability": parse_reliability(payload.get("reliability", "3")),
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    conn.execute(
        """
        INSERT INTO mentor_experience (id, title, content, subject, tags, source, reliability, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            item["id"],
            item["title"],
            item["content"],
            item["subject"],
            json.dumps(item["tags"], ensure_ascii=False),
            item["source"],
            item["reliability"],
            item["created_at"],
        ),
    )
    return item


def delete_mentor_experience(conn, exp_id: str) -> bool:
    row = conn.execute("SELECT id FROM mentor_experience WHERE id = ?", (exp_id,)).fetchone()
    if not row:
        return False
    conn.execute("DELETE FROM mentor_experience WHERE id = ?", (exp_id,))
    return True


def save_teacher_turn(
    conn,
    *,
    message: str,
    intent: str,
    strategy: dict,
    context: dict,
    answer: str,
    memory_candidate: str,
) -> str:
    turn_id = uuid.uuid4().hex
    context_json = json.dumps(
        {
            "profile": context.get("profile", {}),
            "top_gaps": context.get("top_gaps", [])[:5],
            "review_backlog": context.get("review_backlog", {}),
            "today_actions": context.get("today_actions", [])[:5],
        },
        ensure_ascii=False,
    )
    conn.execute(
        """
        INSERT INTO ai_teacher_turns (id, user_message, intent, strategy, context_json, answer, memory_candidate, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            turn_id,
            message[:2000],
            intent,
            strategy.get("key", ""),
            context_json,
            answer[:8000],
            memory_candidate,
            datetime.now().isoformat(timespec="seconds"),
        ),
    )
    return turn_id


def select_relevant_mentor_experiences(conn, message: str = "", subject_hint: str = "", limit: int = 5) -> list[dict]:
    experiences = load_mentor_experiences(conn, limit=80)
    text = (message or "").lower()
    tokens = [token for token in re.split(r"[,，、\s。！？；;:：/\\-]+", text) if len(token) >= 2]
    ranked = []
    for item in experiences:
        haystack = " ".join(
            [
                item.get("title", ""),
                item.get("content", ""),
                item.get("subject", ""),
                " ".join(item.get("tags", [])),
            ]
        ).lower()
        score = item.get("reliability", 3) * 0.2
        if subject_hint and subject_hint == item.get("subject"):
            score += 2
        for token in tokens:
            if token and token in haystack:
                score += 1
        if score > 0.5:
            ranked.append((score, item))
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in ranked[:limit]]
