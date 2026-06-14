from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from typing import Callable

from sakura.ai import client as sakura_ai

DEFAULT_MEMORY_SUBJECT = "未分科"
MEMORY_SETTINGS_ID = "singleton"
DEFAULT_MEMORY_COMPRESSION_PROMPT = """
你是 Sakura 做题集的“老师记忆压缩器”。请把原始对话或笔记压缩成一条长期可复用的老师记忆。

目标不是复述原文，而是提炼以后 AI 老师真正需要记住的信息：
1. 用户在该学科中的稳定偏好，例如喜欢先提示再完整解析、讨厌空泛建议。
2. 可复现的薄弱模式，例如某类概念混淆、审题偏差、公式遗忘、计算习惯。
3. 已验证有效的教学策略，例如先画图、先写条件、先做 Base 变式。
4. 后续回答时应该优先采用的提醒方式或训练安排。

输出要求：
- 只输出一条记忆，不要写标题，不要解释压缩过程。
- 80 到 180 个中文字符为宜。
- 必须具体、可执行、可长期复用。
- 不要保存一次性的闲聊、情绪宣泄、无证据的猜测或完整题解步骤。
- 即使原文是简短笔记、第三人称转述或测试性表达，只要包含学科、偏好、薄弱模式或教学策略，就应该形成记忆，不要误判为占位符。
- 只有完全没有学习信息时，才输出“暂不形成长期记忆：原因...”。
""".strip()


def normalize_memory_subject(subject: str | None) -> str:
    text = str(subject or "").strip()
    return (text or DEFAULT_MEMORY_SUBJECT)[:60]


def clamp_limit(value: int, default: int = 30, maximum: int = 200) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(1, min(maximum, parsed))


def load_teacher_memory_settings(conn) -> dict:
    row = conn.execute(
        "SELECT compression_prompt, updated_at FROM teacher_memory_settings WHERE id = ?",
        (MEMORY_SETTINGS_ID,),
    ).fetchone()
    prompt = str(row["compression_prompt"]).strip() if row else ""
    return {
        "compression_prompt": prompt or DEFAULT_MEMORY_COMPRESSION_PROMPT,
        "default_compression_prompt": DEFAULT_MEMORY_COMPRESSION_PROMPT,
        "is_custom": bool(prompt),
        "updated_at": row["updated_at"] if row else "",
    }


def save_teacher_memory_settings(conn, compression_prompt: str) -> dict:
    prompt = str(compression_prompt or "").strip()
    if not prompt:
        prompt = DEFAULT_MEMORY_COMPRESSION_PROMPT
    prompt = prompt[:3000]
    updated_at = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        """
        INSERT INTO teacher_memory_settings(id, compression_prompt, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            compression_prompt = excluded.compression_prompt,
            updated_at = excluded.updated_at
        """,
        (MEMORY_SETTINGS_ID, prompt, updated_at),
    )
    return {
        "compression_prompt": prompt,
        "default_compression_prompt": DEFAULT_MEMORY_COMPRESSION_PROMPT,
        "is_custom": prompt != DEFAULT_MEMORY_COMPRESSION_PROMPT,
        "updated_at": updated_at,
    }


def reset_teacher_memory_settings(conn) -> dict:
    conn.execute("DELETE FROM teacher_memory_settings WHERE id = ?", (MEMORY_SETTINGS_ID,))
    return load_teacher_memory_settings(conn)


def local_compress_memory(content: str, subject: str = "", instruction: str = "") -> str:
    text = re.sub(r"\s+", " ", str(content or "")).strip()
    if not text:
        return ""
    subject_text = normalize_memory_subject(subject)
    cues = []
    cue_words = [
        "偏好",
        "喜欢",
        "不喜欢",
        "容易",
        "总是",
        "经常",
        "混淆",
        "薄弱",
        "错因",
        "公式",
        "审题",
        "计算",
        "逻辑",
        "计划",
        "复习",
    ]
    for sentence in re.split(r"[。！？!?；;\n]+", text):
        sentence = sentence.strip()
        if not sentence:
            continue
        if any(word in sentence for word in cue_words):
            cues.append(sentence)
        if len(cues) >= 3:
            break
    core = "；".join(cues) if cues else text[:160]
    extra = f" 用户自定义要求：{instruction.strip()[:120]}" if instruction and instruction.strip() else ""
    return f"[{subject_text}] {core[:180]}。后续教学应基于这条长期模式给提示、纠偏和练习安排。{extra}"[:260]


def build_memory_compression_prompt(
    *,
    content: str,
    subject: str,
    source: str,
    compression_prompt: str,
    instruction: str = "",
) -> str:
    subject_text = normalize_memory_subject(subject)
    custom = str(instruction or "").strip()
    custom_block = f"\n\n用户本次额外要求：\n{custom}" if custom else ""
    return f"""
{compression_prompt}
{custom_block}

学科：{subject_text}
来源：{source or "chat"}

原始内容：
{str(content or "").strip()[:6000]}

请输出压缩后的老师记忆：
""".strip()


def compress_memory_content(
    *,
    content: str,
    subject: str,
    source: str,
    instruction: str,
    settings: dict,
    llm_enabled: bool,
    call_llm: Callable,
    on_error: Callable[[Exception], None] | None = None,
) -> dict:
    prompt = build_memory_compression_prompt(
        content=content,
        subject=subject,
        source=source,
        compression_prompt=settings["compression_prompt"],
        instruction=instruction,
    )
    used_ai = False
    error = ""
    summary = ""
    if llm_enabled:
        try:
            summary = call_llm(prompt, temperature=0.15).strip()
            used_ai = True
        except Exception as exc:
            if on_error:
                on_error(exc)
            error = str(exc)
    if not summary:
        summary = local_compress_memory(content, subject, instruction)
    return {
        "summary": summary[:2000],
        "used_ai": used_ai,
        "error": error,
        "memory_settings": settings,
    }


def ensure_teacher_memory_subject(conn, subject: str | None) -> str:
    normalized = normalize_memory_subject(subject)
    conn.execute(
        """
        INSERT OR IGNORE INTO teacher_memory_subjects(subject, created_at)
        VALUES (?, ?)
        """,
        (normalized, datetime.now().isoformat(timespec="seconds")),
    )
    return normalized


def load_teacher_memory_subjects(conn) -> list[str]:
    rows = conn.execute(
        """
        SELECT subject FROM teacher_memory_subjects WHERE subject <> ''
        UNION
        SELECT DISTINCT subject FROM teacher_memory WHERE subject <> ''
        UNION
        SELECT DISTINCT subject FROM documents WHERE subject <> ''
        UNION
        SELECT DISTINCT subject FROM textbooks WHERE subject <> ''
        UNION
        SELECT DISTINCT subject FROM mentor_experience WHERE subject <> ''
        ORDER BY subject
        """
    ).fetchall()
    subjects = [str(row["subject"]).strip() for row in rows if str(row["subject"]).strip()]
    if DEFAULT_MEMORY_SUBJECT not in subjects:
        subjects.insert(0, DEFAULT_MEMORY_SUBJECT)
    return subjects


def load_teacher_memories(conn, limit: int = 10, subject: str = "", search: str = "") -> list[dict]:
    where = []
    params: list[str] = []
    normalized_subject = str(subject or "").strip()
    if normalized_subject and normalized_subject != "__all__":
        where.append("subject = ?")
        params.append(normalize_memory_subject(normalized_subject))
    keyword = str(search or "").strip()
    if keyword:
        like = f"%{keyword}%"
        where.append("(content LIKE ? OR source LIKE ? OR subject LIKE ?)")
        params.extend([like, like, like])
    sql = "SELECT id, content, subject, source, created_at FROM teacher_memory"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(clamp_limit(limit))
    rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def save_teacher_memory(conn, content: str, source: str = "chat", subject: str = "") -> dict:
    content = (content or "").strip()
    if not content:
        raise ValueError("记忆内容不能为空")
    normalized_subject = ensure_teacher_memory_subject(conn, subject)
    memory = {
        "id": uuid.uuid4().hex,
        "content": content[:2000],
        "subject": normalized_subject,
        "source": (source or "chat")[:30],
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    conn.execute(
        "INSERT INTO teacher_memory (id, content, subject, source, created_at) VALUES (?, ?, ?, ?, ?)",
        (memory["id"], memory["content"], memory["subject"], memory["source"], memory["created_at"]),
    )
    return memory


def delete_teacher_memory(conn, memory_id: str) -> bool:
    row = conn.execute("SELECT id FROM teacher_memory WHERE id = ?", (memory_id,)).fetchone()
    if not row:
        return False
    conn.execute("DELETE FROM teacher_memory WHERE id = ?", (memory_id,))
    return True


def teacher_memory_prompt(conn, subject_hint: str = "") -> str:
    subject = normalize_memory_subject(subject_hint) if subject_hint else ""
    memories = load_teacher_memories(conn, limit=8, subject=subject) if subject else load_teacher_memories(conn, limit=8)
    if subject and len(memories) < 4:
        seen = {item["id"] for item in memories}
        for item in load_teacher_memories(conn, limit=8):
            if item["id"] not in seen:
                memories.append(item)
            if len(memories) >= 8:
                break
    if not memories:
        return "暂无主动导入的对话记忆。"
    return "\n".join(f"- [{item.get('subject') or DEFAULT_MEMORY_SUBJECT}] {item['content']}" for item in memories)


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


def run_teacher_chat_turn(
    conn,
    *,
    message: str,
    context: dict,
    call_llm_messages: Callable,
    model: str,
    base_url: str,
) -> dict:
    turn = sakura_ai.build_teacher_chat_turn(message, context, call_llm_messages=call_llm_messages)
    save_teacher_turn(
        conn,
        message=message,
        intent=turn["intent"],
        strategy=turn["strategy"],
        context=context,
        answer=turn["answer"],
        memory_candidate=turn["memory_candidate"],
    )
    return {
        "answer": turn["answer"],
        "has_key": True,
        "model": model,
        "base_url": base_url,
        "teacher_intent": turn["intent"],
        "teacher_strategy": turn["strategy"],
        "memory_candidate": turn["memory_candidate"],
    }


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
