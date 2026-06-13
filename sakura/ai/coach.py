from __future__ import annotations

import json
import math
import sys
import traceback
from datetime import date, datetime, timedelta
from typing import Callable

from sakura.ai import profile as sakura_profile


COACH_STATE_ALLOWED_FIELDS = {
    "daily_minutes",
    "exam_date",
    "cadence",
    "focus_subject",
    "last_profile_at",
    "last_plan_at",
    "plan_json",
    "weather_city",
}


def get_coach_state(
    conn,
    *,
    coach_state_id: str,
    default_daily_minutes: int,
    exam_date: date,
) -> dict:
    row = conn.execute("SELECT * FROM coach_state WHERE id = ?", (coach_state_id,)).fetchone()
    if not row:
        conn.execute(
            "INSERT INTO coach_state (id, daily_minutes, exam_date, cadence, focus_subject, plan_json) VALUES (?, ?, ?, ?, ?, '{}')",
            (coach_state_id, default_daily_minutes, exam_date.isoformat(), "immediate", ""),
        )
        row = conn.execute("SELECT * FROM coach_state WHERE id = ?", (coach_state_id,)).fetchone()
    item = dict(row)
    if not item.get("exam_date"):
        item["exam_date"] = exam_date.isoformat()
    return item


def save_coach_state(
    conn,
    *,
    coach_state_id: str,
    default_daily_minutes: int,
    exam_date: date,
    fields: dict,
) -> dict:
    get_coach_state(
        conn,
        coach_state_id=coach_state_id,
        default_daily_minutes=default_daily_minutes,
        exam_date=exam_date,
    )
    updates = {k: v for k, v in fields.items() if k in COACH_STATE_ALLOWED_FIELDS and v is not None}
    if updates:
        assignments = ", ".join(f"{key} = ?" for key in updates)
        conn.execute(f"UPDATE coach_state SET {assignments} WHERE id = ?", [*updates.values(), coach_state_id])
    return get_coach_state(
        conn,
        coach_state_id=coach_state_id,
        default_daily_minutes=default_daily_minutes,
        exam_date=exam_date,
    )


def parse_exam_date(value: str | None, fallback: date) -> date:
    try:
        return date.fromisoformat((value or "").strip())
    except (TypeError, ValueError):
        return fallback


def profile_summary_from_latest(latest: dict | None) -> dict | None:
    if not latest:
        return None
    profile = latest.get("profile") or {}
    return {
        "version": latest.get("version", 0),
        "evidence_count": profile.get("evidence_count", 0),
        "knowledge_count": profile.get("knowledge_count", 0),
        "avg_mastery": profile.get("avg_mastery", 0),
        "velocity": profile.get("velocity", ""),
        "headline": profile.get("headline", ""),
        "created_at": latest.get("created_at", ""),
    }


def cached_plan_from_state(state: dict) -> dict:
    try:
        parsed = json.loads(state.get("plan_json") or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def recent_learning_evidence(conn, limit: int = 8) -> list[dict]:
    rows = conn.execute(
        """
        SELECT q.id, q.status, q.category, q.chapter, q.difficulty,
               q.mistake_reason, q.meta_tags, q.review_stage, q.retention_stage,
               q.next_review_at, q.created_at,
               d.subject, d.title document_title
        FROM questions q
        JOIN documents d ON d.id = q.document_id
        WHERE q.status IN ('做错', '半会', '需复习') OR q.ever_wrong = 1
        ORDER BY COALESCE(q.last_reviewed_at, q.created_at) DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    evidence = []
    for row in rows:
        item = dict(row)
        try:
            item["meta_tags"] = json.loads(item.get("meta_tags") or "[]")
        except (TypeError, json.JSONDecodeError):
            item["meta_tags"] = []
        evidence.append(item)
    return evidence


def build_ai_teacher_context(
    conn,
    message: str = "",
    *,
    get_coach_state: Callable,
    load_latest_profile: Callable,
    parse_exam_date: Callable[[str | None], date],
    gather_knowledge_stats: Callable,
    teacher_memory_prompt: Callable,
    select_relevant_mentor_experiences: Callable,
    default_daily_minutes: int,
    minutes_per_question: int,
    root_cause_prescriptions: dict[str, str],
    knowledge_dependencies: dict[str, list[str]],
    find_foundation_questions: Callable,
    mock_paper_kind: str,
    today: date | None = None,
) -> dict:
    today = today or date.today()
    state = get_coach_state(conn)
    latest = load_latest_profile(conn)
    profile = latest["profile"] if latest else {}
    gaps = rank_gaps_from_profile(profile, top_n=5, root_cause_prescriptions=root_cause_prescriptions) if profile else []
    backlog = compute_review_backlog(conn, today)
    exam = parse_exam_date(state.get("exam_date"))
    days_left = (exam - today).days
    daily_minutes = int(state.get("daily_minutes") or default_daily_minutes)
    today_actions = build_today_actions(
        conn,
        gaps,
        backlog,
        daily_minutes,
        days_left < 14,
        state.get("focus_subject", ""),
        minutes_per_question=minutes_per_question,
        knowledge_dependencies=knowledge_dependencies,
        find_foundation_questions=find_foundation_questions,
        mock_paper_kind=mock_paper_kind,
    ) if profile else []
    subject_hint = state.get("focus_subject", "")
    mentor_experiences = select_relevant_mentor_experiences(conn, message, subject_hint, limit=5)
    return {
        "teacher_memories": teacher_memory_prompt(conn, subject_hint),
        "mentor_experiences": mentor_experiences,
        "mentor_experience_policy": "这些是外部经验参考，不是用户个人做题证据；只能辅助生成策略，不能替代本地错题统计。",
        "settings": {
            "daily_minutes": daily_minutes,
            "exam_date": exam.isoformat(),
            "days_left": days_left,
            "cadence": state.get("cadence", "immediate"),
            "focus_subject": subject_hint,
        },
        "profile": {
            "version": latest["version"] if latest else 0,
            "has_profile": bool(latest),
            "headline": profile.get("headline", ""),
            "pattern_summary": profile.get("pattern_summary", ""),
            "avg_mastery": profile.get("avg_mastery", 0),
            "evidence_count": profile.get("evidence_count", 0),
            "error_mode_profile": profile.get("error_mode_profile", {}),
            "recurring_misconceptions": profile.get("recurring_misconceptions", [])[:6],
            "prereq_gaps": profile.get("prereq_gaps", [])[:8],
        },
        "top_gaps": gaps,
        "review_backlog": backlog,
        "today_actions": today_actions,
        "recent_wrong_or_review_questions": recent_learning_evidence(conn, limit=8),
        "knowledge_stats_sample": gather_knowledge_stats(conn)[:10],
        "response_contract": {
            "must_use_evidence": True,
            "avoid_fabrication": True,
            "default_scaffolding": "概念提示 -> 关键一步 -> 完整说明",
            "must_end_with_actions": True,
        },
    }


def compute_review_backlog(conn, today: date) -> dict:
    today_iso = today.isoformat()
    week_iso = (today + timedelta(days=7)).isoformat()
    overdue = conn.execute(
        "SELECT COUNT(*) c FROM questions WHERE ever_wrong = 1 AND mastered_at IS NULL AND next_review_at IS NOT NULL AND date(next_review_at) < date(?)",
        (today_iso,),
    ).fetchone()["c"]
    due_today = conn.execute(
        "SELECT COUNT(*) c FROM questions WHERE ever_wrong = 1 AND mastered_at IS NULL AND next_review_at IS NOT NULL AND date(next_review_at) = date(?)",
        (today_iso,),
    ).fetchone()["c"]
    due_week = conn.execute(
        "SELECT COUNT(*) c FROM questions WHERE ever_wrong = 1 AND mastered_at IS NULL AND next_review_at IS NOT NULL AND date(next_review_at) <= date(?)",
        (week_iso,),
    ).fetchone()["c"]
    active_wrong = conn.execute(
        "SELECT COUNT(*) c FROM questions WHERE status IN ('做错', '半会', '需复习')",
    ).fetchone()["c"]
    return {"overdue": overdue, "due_today": due_today, "due_week": due_week, "active_wrong": active_wrong}


def rank_gaps_from_profile(
    profile: dict,
    top_n: int = 6,
    *,
    root_cause_prescriptions: dict[str, str],
) -> list[dict]:
    """Rank weak knowledge points by mastery, evidence volume and prerequisite impact."""
    state = profile.get("knowledge_state", {})
    prereq_gaps = set(profile.get("prereq_gaps", []))
    error_mode = profile.get("error_mode_profile", {})
    main_cause = max(error_mode, key=error_mode.get) if error_mode and max(error_mode.values(), default=0) > 0 else ""

    ranked = []
    for name, info in state.items():
        evidence = info.get("evidence", 0)
        if evidence == 0:
            continue
        mastery = info.get("mastery", 0.5)
        weakness = 1 - mastery
        volume = math.log(1 + info.get("total", 0))
        prereq_boost = 1.35 if name in prereq_gaps else 1.0
        urgency = 1 + (info.get("wrong", 0) + info.get("review", 0)) * 0.12
        score = round(weakness * (0.5 + volume) * prereq_boost * urgency, 4)

        # Show the actual accuracy (correct/evidence) to match the 做对 X/Y fraction printed next
        # to it; the Laplace-smoothed `mastery` is only used for ranking, not display. (evidence>0
        # is guaranteed by the `continue` above.)
        display_accuracy = int(round(info.get("correct", 0) / evidence * 100))
        reason = f"正确率 {display_accuracy}%（做对 {info.get('correct', 0)}/{evidence}）"
        if name in prereq_gaps:
            reason += "，且是其它薄弱点的前置 -> 先补地基"
        if info.get("trend") == "down":
            reason += "，近期还在退步"
        elif info.get("trend") == "up":
            reason += "，已在回升，值得乘胜追击"
        prescription = root_cause_prescriptions.get(main_cause, "先精读同类范题，再闭卷重做巩固。")
        ranked.append({
            "name": name,
            "subject": info.get("subject", ""),
            "mastery": mastery,
            "band": info.get("band", ""),
            "evidence": evidence,
            "trend": info.get("trend", "flat"),
            "score": score,
            "reason": reason,
            "prescription": prescription,
            "note": info.get("note", ""),
        })
    ranked.sort(key=lambda x: x["score"], reverse=True)
    return ranked[:top_n]


def build_today_actions(
    conn,
    gaps: list[dict],
    backlog: dict,
    daily_minutes: int,
    in_sprint: bool,
    focus_subject: str,
    *,
    minutes_per_question: int,
    knowledge_dependencies: dict[str, list[str]],
    find_foundation_questions: Callable,
    mock_paper_kind: str,
) -> list[dict]:
    capacity = max(2, round(daily_minutes / minutes_per_question))
    actions = []
    used = 0

    review_n = min(backlog["due_today"] + backlog["overdue"], max(1, capacity // 2))
    if review_n > 0:
        actions.append({
            "kind": "review",
            "label": f"复习 {review_n} 道到期错题",
            "detail": f"含 {backlog['overdue']} 道逾期 + {backlog['due_today']} 道今日到期，先还复习账。",
            "count": review_n,
            "filter": {"status": "需复习"},
        })
        used += review_n

    for gap in gaps[:2]:
        if used >= capacity:
            break
        n = min(3, capacity - used)
        actions.append({
            "kind": "attack",
            "label": f"攻坚《{gap['name']}》{n} 道",
            "detail": gap["reason"],
            "count": n,
            "filter": {"category": gap["name"], "subject": gap.get("subject", "")},
        })
        used += n

    if used < capacity and gaps:
        subject = focus_subject or gaps[0].get("subject", "")
        dep_categories = []
        for gap in gaps:
            dep_categories.extend(knowledge_dependencies.get(gap["name"], []))
        foundations = find_foundation_questions(conn, subject, list(dict.fromkeys(dep_categories)), set())
        if foundations:
            n = min(len(foundations), capacity - used)
            actions.append({
                "kind": "foundation",
                "label": f"补 {n} 道前置基础题",
                "detail": "针对薄弱点的前置知识，先把地基补上再啃难题。",
                "count": n,
                "filter": {"subject": subject},
            })
            used += n

    if in_sprint:
        actions.append({
            "kind": "mock",
            "label": "限时做 1 套模拟卷",
            "detail": "整卷计时，做完按错因归档，模拟真实考场节奏。",
            "count": 1,
            "filter": {"kind": mock_paper_kind},
        })

    return actions


def coach_narrative_ai(
    profile: dict,
    gaps: list[dict],
    backlog: dict,
    phases: list[dict],
    predictions: dict,
    *,
    llm_enabled: bool,
    call_llm: Callable,
    local_narrative: Callable[[dict, list[dict], dict, list[dict], dict], str],
) -> str:
    local = local_narrative(profile, gaps, backlog, phases, predictions)
    if not llm_enabled:
        return local
    try:
        compact = {
            "headline": profile.get("headline", ""),
            "velocity": profile.get("velocity", ""),
            "pattern_summary": profile.get("pattern_summary", ""),
            "top_gaps": [{"name": g["name"], "reason": g["reason"], "prescription": g["prescription"]} for g in gaps[:5]],
            "backlog": backlog,
            "phases": [{"name": p["name"], "span": p["span"], "focus": p["focus"]} for p in phases],
            "predictions": predictions,
        }
        prompt = f"""
你是一位学习规划助手。下面是一名学生的学情档案与备考数据（数字均来自真实做题记录，请勿改动数字）：
{json.dumps(compact, ensure_ascii=False)}

请用中文写一段 250-400 字的个性化学习档案解读，要求：
1. 先点明这名学生当前的核心问题（结合 pattern_summary 与 top_gaps）。
2. 给出本阶段最该做的 2-3 件事，落到具体知识点和动作。
3. 结合剩余天数给一句务实的节奏建议与鼓励。
语气务实、可执行、不空泛、不堆砌套话；不要承诺提分或预测成绩。
"""
        return call_llm(prompt, temperature=0.5) or local
    except Exception:
        print("LLM coach narrative failed; falling back", file=sys.stderr)
        traceback.print_exc()
        return local


def build_coach_plan(
    conn,
    settings: dict,
    *,
    want_ai: bool = False,
    load_latest_profile: Callable,
    parse_exam_date: Callable[[str | None], date],
    default_daily_minutes: int,
    minutes_per_question: int,
    root_cause_prescriptions: dict[str, str],
    knowledge_dependencies: dict[str, list[str]],
    find_foundation_questions: Callable,
    mock_paper_kind: str,
    llm_enabled: bool,
    call_llm: Callable,
) -> dict:
    """Assemble the full AI-coach plan from profile, backlog and exam settings."""
    profile_row = load_latest_profile(conn)
    profile = profile_row["profile"] if profile_row else {}
    today = date.today()
    exam = parse_exam_date(settings.get("exam_date"))
    days_left = (exam - today).days
    daily_minutes = int(settings.get("daily_minutes") or default_daily_minutes)

    gaps = rank_gaps_from_profile(profile, top_n=6, root_cause_prescriptions=root_cause_prescriptions)
    backlog = compute_review_backlog(conn, today)
    phases = sakura_profile.build_study_phases(days_left, daily_minutes, minutes_per_question)
    in_sprint = days_left < 14
    today_actions = build_today_actions(
        conn,
        gaps,
        backlog,
        daily_minutes,
        in_sprint,
        settings.get("focus_subject", ""),
        minutes_per_question=minutes_per_question,
        knowledge_dependencies=knowledge_dependencies,
        find_foundation_questions=find_foundation_questions,
        mock_paper_kind=mock_paper_kind,
    )
    predictions = sakura_profile.compute_predictions(profile, gaps, days_left, daily_minutes, minutes_per_question)
    narrative = coach_narrative_ai(
        profile,
        gaps,
        backlog,
        phases,
        predictions,
        llm_enabled=llm_enabled,
        call_llm=call_llm,
        local_narrative=sakura_profile.coach_narrative_local,
    ) if want_ai else sakura_profile.coach_narrative_local(profile, gaps, backlog, phases, predictions)

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "has_profile": bool(profile_row),
        "profile_version": profile_row["version"] if profile_row else 0,
        "evidence_count": profile.get("evidence_count", 0),
        "exam_date": exam.isoformat(),
        "days_left": days_left,
        "daily_minutes": daily_minutes,
        "diagnosis": {
            "headline": profile.get("headline", ""),
            "velocity": profile.get("velocity", ""),
            "pattern_summary": profile.get("pattern_summary", ""),
            "error_mode_profile": profile.get("error_mode_profile", {}),
            "recurring_misconceptions": profile.get("recurring_misconceptions", []),
            "knowledge_state": profile.get("knowledge_state", {}),
        },
        "gaps": gaps,
        "backlog": backlog,
        "phases": phases,
        "today": today_actions,
        "predictions": predictions,
        "narrative": narrative,
        "narrative_source": "ai" if (want_ai and llm_enabled) else "local",
    }
