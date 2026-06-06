from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request


DEFAULT_WEATHER_CITY = "北京"
WEATHER_CITY = DEFAULT_WEATHER_CITY


def parse_positive_int(value, fallback: int | None = None) -> int | None:
    try:
        parsed = int(str(value).strip())
        return parsed if parsed > 0 else fallback
    except (TypeError, ValueError):
        return fallback

WEATHER_CODE_TEXT = {
    0: "晴",
    1: "大部晴朗",
    2: "局部多云",
    3: "阴",
    45: "雾",
    48: "雾凇",
    51: "小毛毛雨",
    53: "毛毛雨",
    55: "强毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    80: "小阵雨",
    81: "阵雨",
    82: "强阵雨",
    95: "雷雨",
    96: "雷雨伴冰雹",
    99: "强雷雨伴冰雹",
}

WEATHER_CITY_COORDS = {
    "北京": (39.9042, 116.4074, "北京"),
    "北京市": (39.9042, 116.4074, "北京"),
    "北京海淀": (39.9599, 116.2983, "北京海淀区"),
    "北京海淀区": (39.9599, 116.2983, "北京海淀区"),
    "北京市海淀区": (39.9599, 116.2983, "北京海淀区"),
    "海淀区": (39.9599, 116.2983, "北京海淀区"),
    "海淀": (39.9599, 116.2983, "北京海淀区"),
    "上海": (31.2304, 121.4737, "上海"),
    "上海市": (31.2304, 121.4737, "上海"),
    "广州": (23.1291, 113.2644, "广州"),
    "深圳": (22.5431, 114.0579, "深圳"),
    "杭州": (30.2741, 120.1551, "杭州"),
    "南京": (32.0603, 118.7969, "南京"),
    "武汉": (30.5928, 114.3055, "武汉"),
    "成都": (30.5728, 104.0668, "成都"),
    "重庆": (29.5630, 106.5516, "重庆"),
    "西安": (34.3416, 108.9398, "西安"),
    "天津": (39.3434, 117.3616, "天津"),
    "苏州": (31.2989, 120.5853, "苏州"),
    "长沙": (28.2282, 112.9388, "长沙"),
    "郑州": (34.7466, 113.6254, "郑州"),
    "青岛": (36.0671, 120.3826, "青岛"),
    "山东日照": (35.4164, 119.5269, "山东日照"),
    "山东省日照市": (35.4164, 119.5269, "山东日照"),
    "日照": (35.4164, 119.5269, "日照"),
    "日照市": (35.4164, 119.5269, "日照"),
    "山东日照东港": (35.4254, 119.4623, "日照东港区"),
    "山东省日照市东港区": (35.4254, 119.4623, "日照东港区"),
    "日照东港": (35.4254, 119.4623, "日照东港区"),
    "日照市东港区": (35.4254, 119.4623, "日照东港区"),
    "东港区": (35.4254, 119.4623, "日照东港区"),
}

WTTR_DESC_ZH = {
    "sunny": "晴",
    "clear": "晴",
    "partly cloudy": "局部多云",
    "cloudy": "多云",
    "overcast": "阴",
    "mist": "薄雾",
    "fog": "雾",
    "patchy rain possible": "局部有雨",
    "light drizzle": "小毛毛雨",
    "light rain": "小雨",
    "moderate rain": "中雨",
    "heavy rain": "大雨",
    "patchy snow possible": "局部有雪",
    "light snow": "小雪",
    "moderate snow": "中雪",
    "heavy snow": "大雪",
    "thundery outbreaks possible": "可能有雷雨",
}


def normalize_weather_location(value: str) -> str:
    return re.sub(r"[\s,，/、|]+", "", (value or "").strip())


def weather_location_attempts(city: str) -> list[str]:
    raw = (city or WEATHER_CITY or "北京").strip()
    compact = normalize_weather_location(raw)
    attempts = []
    for item in (raw, compact):
        if item and item not in attempts:
            attempts.append(item)
    stripped = compact
    for suffix in ("省", "市", "区", "县"):
        stripped = stripped.replace(suffix, "")
    if stripped and stripped not in attempts:
        attempts.append(stripped)
    parts = [p for p in re.split(r"[\s,，/、|]+", raw) if p.strip()]
    if parts:
        joined = "".join(parts)
        if joined and joined not in attempts:
            attempts.append(joined)
        last_two = "".join(parts[-2:])
        if last_two and last_two not in attempts:
            attempts.append(last_two)
        last = parts[-1]
        if last and last not in attempts:
            attempts.append(last)
    if "北京" in compact and "海淀" in compact:
        attempts.insert(0, "北京海淀区")
    if "日照" in compact and "东港" in compact:
        attempts.insert(0, "山东省日照市东港区")
    return list(dict.fromkeys(attempts))


def wttr_query_name(city: str) -> str:
    compact = normalize_weather_location(city)
    if "北京" in compact and "海淀" in compact:
        return "Haidian,Beijing"
    if "日照" in compact and "东港" in compact:
        return "Donggang,Rizhao,Shandong"
    if city == "北京":
        return "Beijing"
    if city == "上海":
        return "Shanghai"
    return city


def geocode_weather_city(city: str) -> dict:
    city = (city or WEATHER_CITY or "北京").strip()
    for candidate in weather_location_attempts(city):
        if candidate in WEATHER_CITY_COORDS:
            lat, lon, name = WEATHER_CITY_COORDS[candidate]
            return {"name": name, "country": "中国", "latitude": lat, "longitude": lon, "timezone": "Asia/Shanghai"}
    attempts = weather_location_attempts(city)
    if city == "北京":
        attempts.append("Beijing")
    if "海淀" in normalize_weather_location(city):
        attempts.append("Haidian")
    if "日照" in normalize_weather_location(city):
        attempts.append("Rizhao")
    if "东港" in normalize_weather_location(city):
        attempts.append("Donggang")
    for name in attempts:
        url = (
            "https://geocoding-api.open-meteo.com/v1/search?"
            + urllib.parse.urlencode({"name": name, "count": 1, "language": "zh", "format": "json"})
        )
        with urllib.request.urlopen(url, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        results = data.get("results") or []
        if results:
            item = results[0]
            return {
                "name": item.get("name") or city,
                "country": item.get("country") or "",
                "latitude": item["latitude"],
                "longitude": item["longitude"],
                "timezone": item.get("timezone") or "Asia/Shanghai",
            }
    raise ValueError(f"没有找到城市：{city}")


def fetch_tomorrow_weather(city: str) -> dict:
    try:
        geo = geocode_weather_city(city)
        params = {
            "latitude": geo["latitude"],
            "longitude": geo["longitude"],
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,wind_speed_10m_max",
            "forecast_days": 2,
            "timezone": "Asia/Shanghai",
        }
        url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(params)
        with urllib.request.urlopen(url, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        daily = data.get("daily") or {}
        idx = 1 if len(daily.get("time", [])) > 1 else 0
        code = int((daily.get("weather_code") or [0])[idx])
        return {
            "city": city,
            "resolved_city": geo["name"],
            "country": geo["country"],
            "date": (daily.get("time") or [""])[idx],
            "weather_code": code,
            "weather_text": WEATHER_CODE_TEXT.get(code, f"天气代码 {code}"),
            "temp_max": (daily.get("temperature_2m_max") or [None])[idx],
            "temp_min": (daily.get("temperature_2m_min") or [None])[idx],
            "rain_probability": (daily.get("precipitation_probability_max") or [None])[idx],
            "wind_max": (daily.get("wind_speed_10m_max") or [None])[idx],
            "source": "open-meteo",
        }
    except Exception:
        return fetch_tomorrow_weather_wttr(city)


def fetch_tomorrow_weather_wttr(city: str) -> dict:
    city = (city or WEATHER_CITY or "北京").strip()
    query_city = wttr_query_name(city)
    url = f"https://wttr.in/{urllib.parse.quote(query_city)}?format=j1&lang=zh"
    with urllib.request.urlopen(url, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    days = data.get("weather") or []
    item = days[1] if len(days) > 1 else days[0]
    hourly = item.get("hourly") or [{}]
    noon = hourly[min(4, len(hourly) - 1)] if hourly else {}
    desc = ""
    if noon.get("lang_zh"):
        desc = noon["lang_zh"][0].get("value", "")
    if not desc and noon.get("weatherDesc"):
        desc = noon["weatherDesc"][0].get("value", "")
    desc = WTTR_DESC_ZH.get(desc.strip().lower(), desc)
    rain_values = [parse_positive_int(h.get("chanceofrain"), 0) or 0 for h in hourly]
    wind_values = [parse_positive_int(h.get("windspeedKmph"), 0) or 0 for h in hourly]
    return {
        "city": city,
        "resolved_city": city,
        "country": "",
        "date": item.get("date", ""),
        "weather_code": parse_positive_int(noon.get("weatherCode"), 0) or 0,
        "weather_text": desc or "天气信息",
        "temp_max": parse_positive_int(item.get("maxtempC"), None),
        "temp_min": parse_positive_int(item.get("mintempC"), None),
        "rain_probability": max(rain_values) if rain_values else 0,
        "wind_max": max(wind_values) if wind_values else 0,
        "source": "wttr.in",
    }


