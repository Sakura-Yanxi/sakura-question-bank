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
    "/api/coach": RouteTarget("handle_coach_get"),
    "/api/coach/settings": RouteTarget("handle_coach_settings_get"),
    "/api/profile/history": RouteTarget("handle_profile_history"),
    "/api/weather/settings": RouteTarget("handle_weather_settings_get"),
    "/api/weather/preview": RouteTarget("handle_weather_preview", with_query=True),
    "/api/ai-chat/memory": RouteTarget("handle_ai_memory_get"),
    "/api/mentor-experience": RouteTarget("handle_mentor_experience_get"),
    "/api/llm/settings": RouteTarget("handle_llm_settings_get"),
    "/api/notification/settings": RouteTarget("handle_notification_settings_get"),
    "/api/notify/settings": RouteTarget("handle_notification_settings_get"),
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
    "/api/ai-chat/memory": RouteTarget("handle_ai_memory_post"),
    "/api/mentor-experience": RouteTarget("handle_mentor_experience_post"),
    "/api/llm/settings": RouteTarget("handle_llm_settings_post"),
    "/api/notification/settings": RouteTarget("handle_notification_settings_post"),
    "/api/notify/settings": RouteTarget("handle_notification_settings_post"),
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
    "handle_rescan_chapters",
    "handle_analyze",
    "handle_hint",
    "handle_variations",
    "handle_crop_question",
    "handle_practice_feedback",
    "handle_delete_textbook",
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


def get_dynamic_route(path: str) -> RouteTarget | None:
    if path.startswith("/api/textbooks/") and "/pages/" in path:
        parts = path.split("/")
        return RouteTarget("handle_textbook_page", args=(parts[3], int(parts[5])))
    if path.startswith("/api/documents/") and path.endswith("/chapter-stats"):
        return RouteTarget("handle_chapter_stats", args=(path.split("/")[-2],))
    if path.startswith("/api/practice/"):
        return RouteTarget("handle_practice_batch_get", args=(path.split("/")[-1],))
    if path.startswith("/api/reflections/") and path.endswith("/download"):
        return RouteTarget("handle_reflection_download", args=(path.split("/")[-2],))
    if path.startswith("/api/questions/"):
        return RouteTarget("handle_question_detail", args=(path.split("/")[-1],))
    return None


def post_dynamic_route(path: str) -> RouteTarget | None:
    if path.startswith("/api/documents/") and path.endswith("/rescan-chapters"):
        return RouteTarget("handle_rescan_chapters", args=(path.split("/")[-2],))
    if path.startswith("/api/questions/") and path.endswith("/analyze"):
        return RouteTarget("handle_analyze", args=(path.split("/")[-2],))
    if path.startswith("/api/questions/") and path.endswith("/hint"):
        return RouteTarget("handle_hint", args=(path.split("/")[-2],))
    if path.startswith("/api/questions/") and path.endswith("/variations"):
        return RouteTarget("handle_variations", args=(path.split("/")[-2],))
    if path.startswith("/api/questions/") and path.endswith("/crop"):
        return RouteTarget("handle_crop_question", args=(path.split("/")[-2],))
    if path.startswith("/api/practice/") and "/questions/" in path:
        parts = split_path(path)
        return RouteTarget("handle_practice_feedback", args=(parts[2], parts[4]))
    return None


def delete_dynamic_route(path: str) -> RouteTarget | None:
    if path.startswith("/api/textbooks/"):
        return RouteTarget("handle_delete_textbook", args=(path.split("/")[-1],))
    if path.startswith("/api/documents/"):
        return RouteTarget("handle_delete_document", args=(path.split("/")[-1],))
    if path.startswith("/api/questions/"):
        return RouteTarget("handle_delete_question", args=(path.split("/")[-1],))
    if path.startswith("/api/reflections/"):
        return RouteTarget("handle_delete_reflection", args=(path.split("/")[-1],))
    if path.startswith("/api/daily/rules/"):
        return RouteTarget("handle_daily_rule_delete", args=(path.split("/")[-1],))
    if path.startswith("/api/ai-chat/memory/"):
        return RouteTarget("handle_ai_memory_delete", args=(path.split("/")[-1],))
    if path.startswith("/api/mentor-experience/"):
        return RouteTarget("handle_mentor_experience_delete", args=(path.split("/")[-1],))
    return None


def patch_dynamic_route(path: str) -> RouteTarget | None:
    if path.startswith("/api/documents/"):
        return RouteTarget("handle_update_document", args=(path.split("/")[-1],))
    if path.startswith("/api/questions/"):
        return RouteTarget("handle_update_question", args=(path.split("/")[-1],))
    return None
