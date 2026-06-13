from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RouteTarget:
    handler: str
    with_query: bool = False
    args: tuple = ()


GET_ROUTES: dict[str, RouteTarget] = {
    "/api/documents": RouteTarget("handle_documents"),
    "/api/textbooks": RouteTarget("handle_textbooks"),
    "/api/questions": RouteTarget("handle_questions", with_query=True),
    "/api/daily": RouteTarget("handle_daily"),
    "/api/daily/rules": RouteTarget("handle_daily_rules_get"),
    "/api/daily/rule-options": RouteTarget("handle_daily_rule_options", with_query=True),
    "/api/backup/export": RouteTarget("handle_backup_export", with_query=True),
    "/api/backup/import-status": RouteTarget("handle_backup_import_status", with_query=True),
    "/api/reflection": RouteTarget("handle_reflection_preview", with_query=True),
    "/api/countdown": RouteTarget("handle_countdown"),
    "/api/quote": RouteTarget("handle_quote"),
    "/api/version": RouteTarget("handle_version", with_query=True),
    "/api/coach": RouteTarget("handle_coach_get"),
    "/api/coach/settings": RouteTarget("handle_coach_settings_get"),
    "/api/profile/history": RouteTarget("handle_profile_history"),
    "/api/weather/settings": RouteTarget("handle_weather_settings_get"),
    "/api/weather/preview": RouteTarget("handle_weather_preview", with_query=True),
    "/api/ai-chat/memory": RouteTarget("handle_ai_memory_get", with_query=True),
    "/api/ai-chat/memory-settings": RouteTarget("handle_ai_memory_settings_get"),
    "/api/ai-chat/memory-subjects": RouteTarget("handle_ai_memory_subjects_get"),
    "/api/mentor-experience": RouteTarget("handle_mentor_experience_get"),
    "/api/llm/settings": RouteTarget("handle_llm_settings_get"),
    "/api/notification/settings": RouteTarget("handle_notification_settings_get"),
    "/api/notify/settings": RouteTarget("handle_notification_settings_get"),
    "/api/security/settings": RouteTarget("handle_security_settings_get"),
    "/api/reminder/settings": RouteTarget("handle_reminder_settings_get"),
    "/api/today/done": RouteTarget("handle_today_done"),
    "/api/today/status": RouteTarget("handle_today_status"),
    "/api/export/mistakes": RouteTarget("handle_export_mistakes", with_query=True),
    "/api/reflections": RouteTarget("handle_reflection_history"),
}


POST_ROUTES: dict[str, RouteTarget] = {
    "/api/upload": RouteTarget("handle_upload"),
    "/api/textbooks/upload": RouteTarget("handle_textbook_upload"),
    "/api/textbooks/chat": RouteTarget("handle_textbook_chat"),
    "/api/textbooks/vision": RouteTarget("handle_textbook_vision"),
    "/api/textbooks/memory": RouteTarget("handle_textbook_memory"),
    "/api/reflection": RouteTarget("handle_reflection"),
    "/api/profile/refresh": RouteTarget("handle_profile_refresh"),
    "/api/coach": RouteTarget("handle_coach_post"),
    "/api/coach/settings": RouteTarget("handle_coach_settings_post"),
    "/api/daily/rules": RouteTarget("handle_daily_rule_save"),
    "/api/backup/import": RouteTarget("handle_backup_import"),
    "/api/weather/settings": RouteTarget("handle_weather_settings_post"),
    "/api/weather/reminder": RouteTarget("handle_weather_reminder_preview"),
    "/api/push/daily": RouteTarget("handle_push_daily"),
    "/api/push/morning": RouteTarget("handle_push_morning"),
    "/api/push/night": RouteTarget("handle_push_night"),
    "/api/push/weather": RouteTarget("handle_push_weather"),
    "/api/ai-chat": RouteTarget("handle_ai_chat"),
    "/api/ai-chat/memory/compress": RouteTarget("handle_ai_memory_compress"),
    "/api/ai-chat/memory": RouteTarget("handle_ai_memory_post"),
    "/api/ai-chat/memory-settings": RouteTarget("handle_ai_memory_settings_post"),
    "/api/ai-chat/memory-subjects": RouteTarget("handle_ai_memory_subjects_post"),
    "/api/mentor-experience": RouteTarget("handle_mentor_experience_post"),
    "/api/llm/settings": RouteTarget("handle_llm_settings_post"),
    "/api/notification/settings": RouteTarget("handle_notification_settings_post"),
    "/api/notify/settings": RouteTarget("handle_notification_settings_post"),
    "/api/security/settings": RouteTarget("handle_security_settings_post"),
    "/api/notification/test-email": RouteTarget("handle_email_test"),
    "/api/reminder/settings": RouteTarget("handle_reminder_settings_post"),
}


DELETE_ROUTES: dict[str, RouteTarget] = {
    "/api/coach/plan": RouteTarget("handle_clear_coach_plan"),
}


DYNAMIC_HANDLER_NAMES = {
    "handle_textbook_page",
    "handle_chapter_stats",
    "handle_practice_batch_get",
    "handle_reflection_download",
    "handle_question_detail",
    "handle_question_review_notes_get",
    "handle_question_review_notes_post",
    "handle_rescan_chapters",
    "handle_analyze",
    "handle_hint",
    "handle_variations",
    "handle_crop_question",
    "handle_practice_feedback",
    "handle_delete_textbook",
    "handle_delete_textbook_page",
    "handle_delete_document",
    "handle_delete_question",
    "handle_delete_reflection",
    "handle_daily_rule_delete",
    "handle_ai_memory_delete",
    "handle_mentor_experience_delete",
    "handle_update_document",
    "handle_update_question",
}


def configured_handler_names() -> set[str]:
    names = {target.handler for target in GET_ROUTES.values()}
    names.update(target.handler for target in POST_ROUTES.values())
    names.update(target.handler for target in DELETE_ROUTES.values())
    names.update(DYNAMIC_HANDLER_NAMES)
    return names


def route_for(path: str, routes: dict[str, RouteTarget]) -> RouteTarget | None:
    return routes.get(path)


def split_path(path: str) -> list[str]:
    return [part for part in path.strip("/").split("/") if part]


def _positive_int_arg(value: str) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def get_dynamic_route(path: str) -> RouteTarget | None:
    parts = split_path(path)
    if len(parts) == 5 and parts[:2] == ["api", "textbooks"] and parts[3] == "pages":
        page_number = _positive_int_arg(parts[4])
        if page_number is None:
            return None
        return RouteTarget("handle_textbook_page", args=(parts[2], page_number))
    if len(parts) == 4 and parts[:2] == ["api", "documents"] and parts[3] == "chapter-stats":
        return RouteTarget("handle_chapter_stats", args=(parts[2],))
    if len(parts) == 3 and parts[:2] == ["api", "practice"]:
        return RouteTarget("handle_practice_batch_get", args=(parts[2],))
    if len(parts) == 4 and parts[:2] == ["api", "reflections"] and parts[3] == "download":
        return RouteTarget("handle_reflection_download", args=(parts[2],))
    if len(parts) == 4 and parts[:2] == ["api", "questions"] and parts[3] == "review-notes":
        return RouteTarget("handle_question_review_notes_get", args=(parts[2],))
    if len(parts) == 3 and parts[:2] == ["api", "questions"]:
        return RouteTarget("handle_question_detail", args=(parts[2],))
    return None


def post_dynamic_route(path: str) -> RouteTarget | None:
    parts = split_path(path)
    if len(parts) == 4 and parts[:2] == ["api", "documents"] and parts[3] == "rescan-chapters":
        return RouteTarget("handle_rescan_chapters", args=(parts[2],))
    if len(parts) == 4 and parts[:2] == ["api", "questions"] and parts[3] == "analyze":
        return RouteTarget("handle_analyze", args=(parts[2],))
    if len(parts) == 4 and parts[:2] == ["api", "questions"] and parts[3] == "hint":
        return RouteTarget("handle_hint", args=(parts[2],))
    if len(parts) == 4 and parts[:2] == ["api", "questions"] and parts[3] == "variations":
        return RouteTarget("handle_variations", args=(parts[2],))
    if len(parts) == 4 and parts[:2] == ["api", "questions"] and parts[3] == "crop":
        return RouteTarget("handle_crop_question", args=(parts[2],))
    if len(parts) == 4 and parts[:2] == ["api", "questions"] and parts[3] == "review-notes":
        return RouteTarget("handle_question_review_notes_post", args=(parts[2],))
    if len(parts) == 5 and parts[:2] == ["api", "practice"] and parts[3] == "questions":
        return RouteTarget("handle_practice_feedback", args=(parts[2], parts[4]))
    return None


def delete_dynamic_route(path: str) -> RouteTarget | None:
    parts = split_path(path)
    if len(parts) == 5 and parts[:2] == ["api", "textbooks"] and parts[3] == "pages":
        page_number = _positive_int_arg(parts[4])
        if page_number is None:
            return None
        return RouteTarget("handle_delete_textbook_page", args=(parts[2], page_number))
    if len(parts) == 3 and parts[:2] == ["api", "textbooks"]:
        return RouteTarget("handle_delete_textbook", args=(parts[2],))
    if len(parts) == 3 and parts[:2] == ["api", "documents"]:
        return RouteTarget("handle_delete_document", args=(parts[2],))
    if len(parts) == 3 and parts[:2] == ["api", "questions"]:
        return RouteTarget("handle_delete_question", args=(parts[2],))
    if len(parts) == 3 and parts[:2] == ["api", "reflections"]:
        return RouteTarget("handle_delete_reflection", args=(parts[2],))
    if len(parts) == 4 and parts[:3] == ["api", "daily", "rules"]:
        return RouteTarget("handle_daily_rule_delete", args=(parts[3],))
    if len(parts) == 4 and parts[:3] == ["api", "ai-chat", "memory"]:
        return RouteTarget("handle_ai_memory_delete", args=(parts[3],))
    if len(parts) == 3 and parts[:2] == ["api", "mentor-experience"]:
        return RouteTarget("handle_mentor_experience_delete", args=(parts[2],))
    return None


def patch_dynamic_route(path: str) -> RouteTarget | None:
    parts = split_path(path)
    if len(parts) == 3 and parts[:2] == ["api", "documents"]:
        return RouteTarget("handle_update_document", args=(parts[2],))
    if len(parts) == 3 and parts[:2] == ["api", "questions"]:
        return RouteTarget("handle_update_question", args=(parts[2],))
    return None
