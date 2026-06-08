from __future__ import annotations

import json
import sys
import traceback
import uuid
from datetime import date, datetime, timedelta
from typing import Callable


def gather_knowledge_stats(conn, scope: str = "__all__") -> list[dict]:
    """Aggregate solved-question stats by subject and category."""
    where = ""
    params: list[str] = []
    if scope and scope != "__all__":
        where = "WHERE d.subject = ?"
        params.append(scope)
    rows = conn.execute(
        f"""
        SELECT d.subject, q.category,
               COUNT(*) total,
               SUM(CASE WHEN q.status <> '未做' THEN 1 ELSE 0 END) done,
               SUM(CASE WHEN q.status = '做对' THEN 1 ELSE 0 END) correct,
               SUM(CASE WHEN q.status = '做错' THEN 1 ELSE 0 END) wrong,
               SUM(CASE WHEN q.status IN ('半会', '需复习') THEN 1 ELSE 0 END) review
        FROM questions q
        JOIN documents d ON d.id = q.document_id
        {where}
        GROUP BY d.subject, q.category
        HAVING q.category <> ''
        ORDER BY done DESC, total DESC
        """,
        params,
    ).fetchall()
    return [dict(row) for row in rows]


def load_insight_rows(conn, scope: str = "__all__") -> list[dict]:
    where = ""
    params: list[str] = []
    if scope and scope != "__all__":
        where = "WHERE i.subject = ?"
        params.append(scope)
    rows = conn.execute(
        f"""
        SELECT i.*, q.status, q.category
        FROM insights i
        JOIN questions q ON q.id = i.question_id
        {where}
        ORDER BY i.updated_at DESC
        """,
        params,
    ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        try:
            item["knowledge_points"] = json.loads(item.get("knowledge_points") or "[]")
        except (TypeError, json.JSONDecodeError):
            item["knowledge_points"] = []
        try:
            item["missing_prereq"] = json.loads(item.get("missing_prereq") or "[]")
        except (TypeError, json.JSONDecodeError):
            item["missing_prereq"] = []
        result.append(item)
    return result


def load_latest_profile(conn, scope: str = "__all__") -> dict | None:
    row = conn.execute(
        "SELECT * FROM learner_profile WHERE scope = ? ORDER BY version DESC LIMIT 1",
        (scope,),
    ).fetchone()
    if not row:
        return None
    item = dict(row)
    try:
        item["profile"] = json.loads(item.get("profile_json") or "{}")
    except (TypeError, json.JSONDecodeError):
        item["profile"] = {}
    return item


def mastery_band(score: float, evidence: int) -> str:
    if evidence == 0:
        return "未触及"
    if score >= 0.8:
        return "已掌握"
    if score >= 0.6:
        return "巩固中"
    if score >= 0.4:
        return "不稳"
    return "薄弱"


def merge_profile_locally(
    stats: list[dict],
    insights: list[dict],
    prev_profile: dict | None,
    *,
    root_causes: list[str],
) -> dict:
    """Deterministically synthesize a learner profile from stats and insights."""
    prev_state = (prev_profile or {}).get("knowledge_state", {}) if prev_profile else {}
    knowledge_state: dict[str, dict] = {}
    for stat in stats:
        category = stat["category"]
        done = stat["done"] or 0
        correct = stat["correct"] or 0
        mastery = round((correct + 1) / (done + 2), 3)
        prev = prev_state.get(category, {})
        prev_mastery = prev.get("mastery")
        if prev_mastery is None or done == 0:
            trend = "new" if done else "untouched"
        elif mastery > prev_mastery + 0.03:
            trend = "up"
        elif mastery < prev_mastery - 0.03:
            trend = "down"
        else:
            trend = "flat"
        knowledge_state[category] = {
            "subject": stat["subject"],
            "mastery": mastery,
            "band": mastery_band(mastery, done),
            "evidence": done,
            "correct": correct,
            "wrong": stat["wrong"] or 0,
            "review": stat["review"] or 0,
            "total": stat["total"] or 0,
            "trend": trend,
        }

    error_mode: dict[str, int] = {cause: 0 for cause in root_causes}
    misconception_counter: dict[str, dict] = {}
    prereq_counter: dict[str, int] = {}
    for ins in insights:
        cause = ins.get("root_cause")
        if cause in error_mode:
            error_mode[cause] += 1
        text = (ins.get("misconception") or "").strip()
        if text and text not in {"暂无具体误区记录"}:
            entry = misconception_counter.setdefault(text, {"text": text, "count": 0, "examples": []})
            entry["count"] += 1
            if len(entry["examples"]) < 3:
                entry["examples"].append(ins.get("question_id"))
        for prereq in ins.get("missing_prereq", []):
            prereq_counter[prereq] = prereq_counter.get(prereq, 0) + 1

    recurring = sorted(misconception_counter.values(), key=lambda x: x["count"], reverse=True)[:8]
    prereq_gaps = [p for p, _ in sorted(prereq_counter.items(), key=lambda kv: kv[1], reverse=True)][:8]

    masteries = [v["mastery"] for v in knowledge_state.values() if v["evidence"] > 0]
    avg_mastery = round(sum(masteries) / len(masteries), 3) if masteries else 0.0
    prev_avg = (prev_profile or {}).get("avg_mastery")
    if prev_avg is None:
        velocity = f"首次建档，平均掌握度 {int(avg_mastery * 100)}%"
    else:
        delta = int((avg_mastery - prev_avg) * 100)
        arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "→")
        velocity = f"平均掌握度 {int(prev_avg * 100)}% {arrow} {int(avg_mastery * 100)}%"

    return {
        "knowledge_state": knowledge_state,
        "error_mode_profile": error_mode,
        "recurring_misconceptions": recurring,
        "prereq_gaps": prereq_gaps,
        "avg_mastery": avg_mastery,
        "velocity": velocity,
        "evidence_count": len(insights),
        "knowledge_count": len(knowledge_state),
        "source": "local",
    }


def polish_profile_with_ai(
    base_profile: dict,
    insights: list[dict],
    *,
    llm_enabled: bool,
    call_llm: Callable,
    extract_json_block: Callable[[str], dict],
) -> dict:
    """Ask the LLM for narrative profile notes without changing objective stats."""
    if not llm_enabled:
        return base_profile
    try:
        weak = sorted(
            base_profile["knowledge_state"].items(),
            key=lambda kv: kv[1]["mastery"],
        )[:10]
        compact = {
            "weak_points": [
                {"name": k, "mastery": v["mastery"], "band": v["band"], "evidence": v["evidence"], "trend": v["trend"]}
                for k, v in weak
            ],
            "error_mode_profile": base_profile["error_mode_profile"],
            "recurring_misconceptions": [m["text"] for m in base_profile["recurring_misconceptions"][:6]],
            "prereq_gaps": base_profile["prereq_gaps"],
            "velocity": base_profile["velocity"],
        }
        prompt = f"""
你是一位学习数据分析助手，正在更新一名学生的学情档案。下面是基于真实做题数据算出的客观统计（数字已准确，请勿改动数字）：
{json.dumps(compact, ensure_ascii=False)}

请只输出一个 JSON 代码块，字段固定：
{{
  "headline": "一句话概括这名学生当前的学情画像",
  "knowledge_notes": {{"知识点名": "针对该薄弱点的一句具体诊断（结合掌握度与趋势）"}},
  "pattern_summary": "结合错因分布与反复误区，指出这名学生最值得警惕的1-2个习惯问题"
}}
knowledge_notes 只需覆盖上面 weak_points 里的知识点。
"""
        extra = extract_json_block(call_llm(prompt, temperature=0.3))
        base_profile = {**base_profile, "source": "ai"}
        base_profile["headline"] = str(extra.get("headline", "")).strip()
        base_profile["pattern_summary"] = str(extra.get("pattern_summary", "")).strip()
        notes = extra.get("knowledge_notes") or {}
        if isinstance(notes, dict):
            for name, note in notes.items():
                if name in base_profile["knowledge_state"]:
                    base_profile["knowledge_state"][name]["note"] = str(note).strip()[:120]
        return base_profile
    except Exception:
        print("LLM profile polish failed; keeping local profile", file=sys.stderr)
        traceback.print_exc()
        return base_profile


def synthesize_profile(
    conn,
    *,
    want_ai: bool = True,
    scope: str = "__all__",
    root_causes: list[str],
    llm_enabled: bool,
    call_llm: Callable,
    extract_json_block: Callable[[str], dict],
) -> dict:
    """Read stats and insights, then persist a new learner-profile version."""
    prev = load_latest_profile(conn, scope)
    prev_profile = prev["profile"] if prev else None
    stats = gather_knowledge_stats(conn, scope)
    insights = load_insight_rows(conn, scope)
    profile = merge_profile_locally(stats, insights, prev_profile, root_causes=root_causes)
    if want_ai:
        profile = polish_profile_with_ai(
            profile,
            insights,
            llm_enabled=llm_enabled,
            call_llm=call_llm,
            extract_json_block=extract_json_block,
        )

    version = (prev["version"] + 1) if prev else 1
    now = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        """
        INSERT INTO learner_profile (id, version, scope, profile_json, evidence_count, source, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (uuid.uuid4().hex, version, scope, json.dumps(profile, ensure_ascii=False), profile["evidence_count"], profile["source"], now),
    )
    return {"version": version, "scope": scope, "profile": profile, "created_at": now}


def build_study_phases(
    days_left: int,
    daily_minutes: int,
    minutes_per_question: int = 6,
    today: date | None = None,
) -> list[dict]:
    """Split the remaining preparation time into practical study phases."""
    per_day_questions = max(1, round(daily_minutes / minutes_per_question))
    today = today or date.today()

    def span(start_offset: int, length: int) -> str:
        start = today + timedelta(days=start_offset)
        end = today + timedelta(days=max(start_offset, start_offset + length - 1))
        return f"{start.month}/{start.day} – {end.month}/{end.day}"

    if days_left <= 0:
        return [{
            "name": "考试在即", "span": "今天", "days": 0,
            "focus": "回顾错题集与公式卡，保持手感，别碰新题。",
            "daily_questions": per_day_questions,
        }]
    if days_left < 14:
        return [{
            "name": "冲刺模考", "span": span(0, days_left), "days": days_left,
            "focus": "整套模拟卷限时训练 + 错题三轮回炉，主攻最薄弱的 2-3 个知识点。",
            "daily_questions": per_day_questions,
        }]
    base_days = round(days_left * 0.5)
    boost_days = round(days_left * 0.3)
    sprint_days = days_left - base_days - boost_days
    return [
        {"name": "基础攻坚", "span": span(0, base_days), "days": base_days,
         "focus": "补前置缺口 + 主攻薄弱知识点，先把地基打牢。",
         "daily_questions": per_day_questions},
        {"name": "强化提升", "span": span(base_days, boost_days), "days": boost_days,
         "focus": "不稳知识点做专项突破，错题回炉，提升综合题正确率。",
         "daily_questions": per_day_questions},
        {"name": "冲刺模考", "span": span(base_days + boost_days, sprint_days), "days": sprint_days,
         "focus": "整套模拟卷限时模考，按错因复盘，稳住已掌握内容。",
         "daily_questions": per_day_questions},
    ]


def compute_predictions(
    profile: dict,
    gaps: list[dict],
    days_left: int,
    daily_minutes: int,
    minutes_per_question: int = 6,
) -> dict:
    """Estimate study capacity and weak-point coverage without predicting scores."""
    avg = profile.get("avg_mastery", 0.0)
    capacity_total = max(1, round(days_left * daily_minutes / minutes_per_question))
    weak_total = sum(g.get("total", g.get("evidence", 0)) for g in gaps) or 1
    coverage = min(1.0, capacity_total / (weak_total * 2.5))
    projected = round(min(0.92, avg + coverage * (1 - avg) * 0.6), 3)
    readiness = round(projected * (0.7 + 0.3 * coverage), 3)
    if days_left <= 0:
        outlook = "考试当天：以稳为主，回顾错题与公式卡即可。"
    elif coverage >= 0.8:
        outlook = "时间相对充裕，按计划推进可把薄弱点系统补齐。"
    elif coverage >= 0.5:
        outlook = "时间偏紧，建议聚焦最高优先级的 3-4 个薄弱点，别铺太开。"
    else:
        outlook = "时间紧张，只攻最高频考点与前置地基，放弃边角难题保性价比。"
    return {
        "days_left": days_left,
        "current_avg_mastery": round(avg, 3),
        "projected_avg_mastery": projected,
        "exam_readiness": readiness,
        "coverage": round(coverage, 3),
        "capacity_total": capacity_total,
        "outlook": outlook,
        "note": "这是基于剩余时间和薄弱点题量的容量估算，不代表成绩预测。",
    }


def coach_narrative_local(
    profile: dict,
    gaps: list[dict],
    backlog: dict,
    phases: list[dict],
    predictions: dict,
) -> str:
    """Build a deterministic local study-plan summary."""
    lines = ["【本地复习计划摘要】", ""]
    headline = profile.get("headline")
    if headline:
        lines.append(headline)
    lines.append(profile.get("velocity", ""))
    lines.append("")
    if gaps:
        lines.append("当前最该补的薄弱点（按性价比排序）：")
        for i, gap in enumerate(gaps[:4], 1):
            lines.append(f"  {i}. {gap['name']}：{gap['reason']}")
            lines.append(f"     → {gap['prescription']}")
    if backlog["overdue"] or backlog["due_today"]:
        lines.append("")
        lines.append(f"复习账：{backlog['overdue']} 道逾期 + {backlog['due_today']} 道今日到期，先还清再上新题。")
    lines.append("")
    lines.append(f"时间预算：距考试 {predictions['days_left']} 天，按 {phases[0]['daily_questions']} 题/天推进。")
    lines.append(f"容量估算：当前平均掌握度 {int(predictions['current_avg_mastery']*100)}%，剩余时间约可安排 {predictions['capacity_total']} 道练习。")
    lines.append(f"薄弱点覆盖率估算：{int(predictions['coverage']*100)}%。")
    lines.append(predictions["outlook"])
    return "\n".join(line for line in lines if line is not None)
