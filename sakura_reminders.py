from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


CRON_BEGIN = "# SAKURA_NOTIFY_BEGIN"
CRON_END = "# SAKURA_NOTIFY_END"


@dataclass(frozen=True)
class ReminderSettings:
    morning_on: str = "1"
    morning_time: str = "10:00"
    night_on: str = "1"
    night_time: str = "20:00"
    weather_on: str = "1"
    weather_time: str = "22:30"
    checkin_mode: str = "cloud"

    def as_env(self) -> dict[str, str]:
        return {
            "REMIND_MORNING_ON": self.morning_on,
            "REMIND_MORNING_TIME": self.morning_time,
            "REMIND_NIGHT_ON": self.night_on,
            "REMIND_NIGHT_TIME": self.night_time,
            "REMIND_WEATHER_ON": self.weather_on,
            "REMIND_WEATHER_TIME": self.weather_time,
            "REMIND_CHECKIN_MODE": self.checkin_mode,
        }

    def as_payload(self, cron_status: dict | None = None) -> dict:
        return {
            "morning_on": self.morning_on,
            "morning_time": self.morning_time,
            "night_on": self.night_on,
            "night_time": self.night_time,
            "weather_on": self.weather_on,
            "weather_time": self.weather_time,
            "checkin_mode": self.checkin_mode,
            "cron": cron_status or {},
        }


def normalize_onoff(value: str | int | bool, default: str = "1") -> str:
    text = str(value).strip().lower()
    if text in {"1", "true", "on", "yes", "开启"}:
        return "1"
    if text in {"0", "false", "off", "no", "关闭"}:
        return "0"
    return default


def normalize_time(value: str, default: str) -> str:
    text = str(value or "").strip()
    if not re.match(r"^\d{1,2}:\d{2}$", text):
        return default
    hour, minute = [int(part) for part in text.split(":", 1)]
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        return default
    return f"{hour:02d}:{minute:02d}"


def normalize_checkin_mode(value: str, default: str = "cloud") -> str:
    text = str(value or "").strip()
    return text if text in {"cloud", "local"} else default


def settings_from_env(env: dict[str, str] | None = None) -> ReminderSettings:
    env = env or os.environ
    return ReminderSettings(
        morning_on=normalize_onoff(env.get("REMIND_MORNING_ON", "1")),
        morning_time=normalize_time(env.get("REMIND_MORNING_TIME", "10:00"), "10:00"),
        night_on=normalize_onoff(env.get("REMIND_NIGHT_ON", "1")),
        night_time=normalize_time(env.get("REMIND_NIGHT_TIME", "20:00"), "20:00"),
        weather_on=normalize_onoff(env.get("REMIND_WEATHER_ON", "1")),
        weather_time=normalize_time(env.get("REMIND_WEATHER_TIME", "22:30"), "22:30"),
        checkin_mode=normalize_checkin_mode(env.get("REMIND_CHECKIN_MODE", "cloud")),
    )


def merge_settings(current: ReminderSettings, payload: dict) -> ReminderSettings:
    return ReminderSettings(
        morning_on=normalize_onoff(payload.get("morning_on", current.morning_on), current.morning_on),
        morning_time=normalize_time(str(payload.get("morning_time", current.morning_time)), current.morning_time),
        night_on=normalize_onoff(payload.get("night_on", current.night_on), current.night_on),
        night_time=normalize_time(str(payload.get("night_time", current.night_time)), current.night_time),
        weather_on=normalize_onoff(payload.get("weather_on", current.weather_on), current.weather_on),
        weather_time=normalize_time(str(payload.get("weather_time", current.weather_time)), current.weather_time),
        checkin_mode=normalize_checkin_mode(str(payload.get("checkin_mode", current.checkin_mode)), current.checkin_mode),
    )


def cron_line(root: Path, data_dir: Path, time_value: str, mode: str, log_name: str) -> str:
    hour, minute = time_value.split(":", 1)
    return (
        f"{int(minute)} {int(hour)} * * * cd {root} && {root}/.venv/bin/python notify_daily.py --{mode} "
        f">> {data_dir}/{log_name} 2>&1"
    )


def build_cron_block(settings: ReminderSettings, root: Path, data_dir: Path) -> list[str]:
    lines = [CRON_BEGIN]
    if settings.morning_on == "1":
        lines.append(cron_line(root, data_dir, settings.morning_time, "morning", "notify_morning.log"))
    if settings.night_on == "1":
        lines.append(cron_line(root, data_dir, settings.night_time, "night", "notify_night.log"))
    if settings.weather_on == "1":
        lines.append(cron_line(root, data_dir, settings.weather_time, "weather", "notify_weather.log"))
    lines.append(CRON_END)
    return lines


def install_crontab(settings: ReminderSettings, root: Path, data_dir: Path) -> dict:
    if os.name == "nt":
        return {"installed": False, "message": "当前是 Windows，本地模式不会自动写入 Linux crontab。"}
    try:
        current = subprocess.run(["crontab", "-l"], capture_output=True, text=True, check=False)
        old_lines = current.stdout.splitlines() if current.returncode == 0 else []
        kept = []
        skipping = False
        for line in old_lines:
            stripped = line.strip()
            if stripped == CRON_BEGIN:
                skipping = True
                continue
            if stripped == CRON_END:
                skipping = False
                continue
            if not skipping and "notify_daily.py --" not in line:
                kept.append(line)
        block = build_cron_block(settings, root, data_dir)
        new_text = "\n".join([*kept, *block]).strip() + "\n"
        subprocess.run(["crontab", "-"], input=new_text, text=True, check=True)
        return {"installed": True, "message": "服务器定时任务已更新。", "lines": block}
    except Exception as exc:
        return {"installed": False, "message": f"定时任务写入失败：{exc}"}
