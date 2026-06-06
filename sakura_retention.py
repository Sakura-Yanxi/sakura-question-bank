from __future__ import annotations

import json
from datetime import datetime, timedelta


REVIEW_INTERVAL_DAYS = [1, 3, 7, 14, 30]
META_TAGS = ["计算失误", "公式遗忘", "逻辑死角", "题意理解偏差"]
WRONGISH_STATUSES = {"做错", "半会", "需复习"}


def schedule_for_status(current: dict | None, status: str, now: datetime | None = None) -> dict:
    now = now or datetime.now()
    if status in WRONGISH_STATUSES:
        return {
            "ever_wrong": 1,
            "review_stage": 0,
            "retention_stage": 1,
            "next_review_at": (now + timedelta(days=1)).date().isoformat(),
            "mastered_at": None,
        }
    if status != "做对" or not current:
        return {}

    current_dict = dict(current)
    was_in_review = bool(current_dict.get("ever_wrong")) or current_dict.get("status") in WRONGISH_STATUSES
    if not was_in_review:
        return {}

    next_stage = int(current_dict.get("review_stage") or 0) + 1
    if next_stage > len(REVIEW_INTERVAL_DAYS):
        return {
            "ever_wrong": 1,
            "review_stage": next_stage,
            "retention_stage": REVIEW_INTERVAL_DAYS[-1],
            "next_review_at": None,
            "mastered_at": now.isoformat(timespec="seconds"),
        }
    interval = REVIEW_INTERVAL_DAYS[next_stage - 1]
    return {
        "ever_wrong": 1,
        "review_stage": next_stage,
        "retention_stage": interval,
        "next_review_at": (now + timedelta(days=interval)).date().isoformat(),
        "mastered_at": None,
    }


def normalize_meta_tags(value) -> list[str]:
    if isinstance(value, list):
        raw = value
    else:
        try:
            raw = json.loads(value or "[]")
        except (TypeError, json.JSONDecodeError):
            raw = []
    return [tag for tag in raw if tag in META_TAGS]
