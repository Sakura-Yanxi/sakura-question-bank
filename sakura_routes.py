from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RouteTarget:
    handler: str
    with_query: bool = False


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


def route_for(path: str, routes: dict[str, RouteTarget]) -> RouteTarget | None:
    return routes.get(path)


def split_path(path: str) -> list[str]:
    return [part for part in path.strip("/").split("/") if part]
