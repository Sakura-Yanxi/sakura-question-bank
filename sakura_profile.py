from __future__ import annotations

from datetime import date, timedelta


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
