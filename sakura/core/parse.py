from __future__ import annotations


TRUE_VALUES = {"1", "true", "on", "yes"}
FALSE_VALUES = {"0", "false", "off", "no"}


def positive_int(value, fallback: int | None = None) -> int | None:
    try:
        parsed = int(str(value).strip())
        return parsed if parsed > 0 else fallback
    except (TypeError, ValueError):
        return fallback


def bool_flag(value, default: bool = False) -> bool:
    text = str(value or "").strip().lower()
    if text in TRUE_VALUES:
        return True
    if text in FALSE_VALUES:
        return False
    return default


def clamped_int(value, *, minimum: int, maximum: int, fallback: int) -> int:
    parsed = positive_int(value, fallback)
    if parsed is None:
        parsed = fallback
    return max(minimum, min(maximum, parsed))
