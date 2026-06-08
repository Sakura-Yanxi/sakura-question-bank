from __future__ import annotations

import json
import re
import sys
import traceback
import uuid
from datetime import datetime
from typing import Callable


def guess_root_cause(
    question: dict,
    *,
    normalize_meta_tags: Callable,
    meta_tag_to_root_cause: dict[str, str],
) -> str:
    for tag in normalize_meta_tags(question.get("meta_tags")):
        mapped = meta_tag_to_root_cause.get(tag)
        if mapped:
            return mapped
    return "方法不会"


def local_insight(
    question: dict,
    *,
    default_category: str,
    default_chapter: str,
    knowledge_dependencies: dict[str, list[str]],
    normalize_meta_tags: Callable,
    meta_tag_to_root_cause: dict[str, str],
) -> dict:
    category = question.get("category") or default_category
    chapter = question.get("chapter") or ""
    knowledge_points = [kp for kp in (category, chapter) if kp and kp != default_category and kp != default_chapter]
    knowledge_points = knowledge_points or [category]
    root_cause = guess_root_cause(
        question,
        normalize_meta_tags=normalize_meta_tags,
        meta_tag_to_root_cause=meta_tag_to_root_cause,
    )
    tags = normalize_meta_tags(question.get("meta_tags"))
    misconception = (question.get("mistake_reason") or "、".join(tags) or "暂无具体误区记录").strip()[:200]
    prereq = []
    for key in (category, chapter):
        prereq.extend(knowledge_dependencies.get(key, []))
    seen: list[str] = []
    for item in prereq:
        if item not in seen:
            seen.append(item)
    return {
        "knowledge_points": knowledge_points[:5],
        "root_cause": root_cause,
        "misconception": misconception,
        "missing_prereq": seen[:5],
        "user_difficulty": {"简单": 2, "中等": 3, "困难": 4}.get(question.get("difficulty", "中等"), 3),
        "confidence": 0.4,
        "source": "local",
    }


def normalize_insight(
    raw: dict,
    question: dict,
    *,
    root_causes: list[str],
    default_category: str,
    default_chapter: str,
    knowledge_dependencies: dict[str, list[str]],
    normalize_meta_tags: Callable,
    meta_tag_to_root_cause: dict[str, str],
) -> dict:
    base = local_insight(
        question,
        default_category=default_category,
        default_chapter=default_chapter,
        knowledge_dependencies=knowledge_dependencies,
        normalize_meta_tags=normalize_meta_tags,
        meta_tag_to_root_cause=meta_tag_to_root_cause,
    )
    if not isinstance(raw, dict):
        return base

    kps = raw.get("knowledge_points")
    if isinstance(kps, str):
        kps = [kps]
    kps = [str(k).strip() for k in (kps or []) if str(k).strip()][:5]

    root_cause = str(raw.get("root_cause", "")).strip()
    if root_cause not in root_causes:
        root_cause = base["root_cause"]

    prereq = raw.get("missing_prereq")
    if isinstance(prereq, str):
        prereq = [prereq]
    prereq = [str(p).strip() for p in (prereq or []) if str(p).strip()][:5]

    try:
        difficulty = int(raw.get("user_difficulty", base["user_difficulty"]))
    except (TypeError, ValueError):
        difficulty = base["user_difficulty"]
    try:
        confidence = float(raw.get("confidence", 0.7))
    except (TypeError, ValueError):
        confidence = 0.7

    return {
        "knowledge_points": kps or base["knowledge_points"],
        "root_cause": root_cause,
        "misconception": str(raw.get("misconception", "")).strip()[:200] or base["misconception"],
        "missing_prereq": prereq or base["missing_prereq"],
        "user_difficulty": max(1, min(5, difficulty)),
        "confidence": max(0.0, min(1.0, confidence)),
        "source": "ai",
    }


def fallback_prose(question: dict, *, default_category: str) -> str:
    return (
        f"知识点：{question.get('category', default_category)}。\n"
        "建议先复盘这道题的核心定义、常见公式和第一步切入方法。"
        "如果是计算错误，把关键变形逐行写出；如果是方法不会，先找同类基础题练 2-3 道。"
    )


def build_analysis_prompt(
    question: dict,
    *,
    default_subject: str,
    default_category: str,
    default_chapter: str,
    normalize_meta_tags: Callable,
) -> str:
    return f"""
你是严谨的错题教练。请完成两件事，并严格按格式输出。

科目：{question.get('subject', default_subject)}
章节：{question.get('chapter', default_chapter)}
题目分类：{question.get('category', default_category)} / {question.get('subcategory', '')}
难度：{question.get('difficulty', '中等')}
做题状态：{question.get('status', '')}
学生勾选的错因标签：{', '.join(normalize_meta_tags(question.get('meta_tags'))) or '无'}
学生备注：{question.get('user_note') or '无'}
题目文字：
{(question.get('ocr_text') or '')[:3500]}

第一部分：用中文给出简洁可执行的错题分析，分四点：
1. 本题考察点
2. 可能错因
3. 解题切入
4. 下次练习建议

第二部分：另起一行，输出一个 ```json 代码块，字段固定如下，不要多余字段：
{{
  "knowledge_points": ["真实考察的知识点，1-3 个"],
  "root_cause": "必须是其中之一：概念缺失 / 计算失误 / 方法不会 / 审题偏差",
  "misconception": "一句话点明这名学生最可能的具体误区",
  "missing_prereq": ["为掌握本题需要补的前置知识点，可为空数组"],
  "user_difficulty": 1 到 5 的整数，表示这道题对该学生的难度,
  "confidence": 0 到 1 之间的小数，表示你对以上判断的置信度
}}
"""


def analyze_and_extract(
    question: dict,
    *,
    llm_enabled: bool,
    call_llm: Callable,
    extract_json_block: Callable[[str], dict],
    default_subject: str,
    default_category: str,
    default_chapter: str,
    root_causes: list[str],
    knowledge_dependencies: dict[str, list[str]],
    normalize_meta_tags: Callable,
    meta_tag_to_root_cause: dict[str, str],
) -> tuple[str, dict]:
    local = local_insight(
        question,
        default_category=default_category,
        default_chapter=default_chapter,
        knowledge_dependencies=knowledge_dependencies,
        normalize_meta_tags=normalize_meta_tags,
        meta_tag_to_root_cause=meta_tag_to_root_cause,
    )
    fallback = fallback_prose(question, default_category=default_category)
    if not llm_enabled:
        return fallback + "\n\n当前未配置 AI 接口密钥，使用本地简版分析与洞察。", local

    try:
        prompt = build_analysis_prompt(
            question,
            default_subject=default_subject,
            default_category=default_category,
            default_chapter=default_chapter,
            normalize_meta_tags=normalize_meta_tags,
        )
        content = call_llm(prompt, temperature=0.3)
        try:
            insight = normalize_insight(
                extract_json_block(content),
                question,
                root_causes=root_causes,
                default_category=default_category,
                default_chapter=default_chapter,
                knowledge_dependencies=knowledge_dependencies,
                normalize_meta_tags=normalize_meta_tags,
                meta_tag_to_root_cause=meta_tag_to_root_cause,
            )
        except (ValueError, json.JSONDecodeError):
            insight = local
        prose = re.sub(r"```(?:json)?\s*\{.*?\}\s*```", "", content, flags=re.S).strip() or fallback
        return prose, insight
    except Exception:
        print("LLM analyze+extract failed; falling back", file=sys.stderr)
        traceback.print_exc()
        return fallback, local


def upsert_insight(conn, question: dict, insight: dict, *, default_subject: str) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        """
        INSERT INTO insights (
            id, question_id, document_id, subject, knowledge_points, root_cause,
            misconception, missing_prereq, user_difficulty, confidence, source, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(question_id) DO UPDATE SET
            document_id = excluded.document_id,
            subject = excluded.subject,
            knowledge_points = excluded.knowledge_points,
            root_cause = excluded.root_cause,
            misconception = excluded.misconception,
            missing_prereq = excluded.missing_prereq,
            user_difficulty = excluded.user_difficulty,
            confidence = excluded.confidence,
            source = excluded.source,
            updated_at = excluded.updated_at
        """,
        (
            uuid.uuid4().hex,
            question.get("id"),
            question.get("document_id", ""),
            question.get("subject") or default_subject,
            json.dumps(insight["knowledge_points"], ensure_ascii=False),
            insight["root_cause"],
            insight["misconception"],
            json.dumps(insight["missing_prereq"], ensure_ascii=False),
            insight["user_difficulty"],
            insight["confidence"],
            insight["source"],
            now,
            now,
        ),
    )
