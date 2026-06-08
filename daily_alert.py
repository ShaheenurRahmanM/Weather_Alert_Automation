#!/usr/bin/env python3
"""
Daily weather push notification (via ntfy.sh).
Sends today's weather, rain chance, and outfit + skincare tips.
Reads all preferences from config.json (editable via the settings page).

Run once a day at your chosen time (GitHub Actions cron, in UTC).
Pass --dry-run to preview without sending.
"""

import sys
import datetime
import urllib.parse
import urllib.request
import json

from notifier import load_config, send_push

TIMEZONE = "Asia/Kolkata"

WMO = {
    0: ("Clear sky", "☀️"), 1: ("Mainly clear", "🌤️"), 2: ("Partly cloudy", "⛅"),
    3: ("Overcast", "☁️"), 45: ("Fog", "🌫️"), 48: ("Rime fog", "🌫️"),
    51: ("Light drizzle", "🌦️"), 53: ("Drizzle", "🌦️"), 55: ("Heavy drizzle", "🌧️"),
    56: ("Freezing drizzle", "🌧️"), 57: ("Freezing drizzle", "🌧️"),
    61: ("Light rain", "🌦️"), 63: ("Rain", "🌧️"), 65: ("Heavy rain", "🌧️"),
    66: ("Freezing rain", "🌧️"), 67: ("Freezing rain", "🌧️"),
    71: ("Light snow", "🌨️"), 73: ("Snow", "🌨️"), 75: ("Heavy snow", "❄️"),
    77: ("Snow grains", "🌨️"), 80: ("Rain showers", "🌦️"), 81: ("Rain showers", "🌧️"),
    82: ("Violent showers", "⛈️"), 85: ("Snow showers", "🌨️"), 86: ("Snow showers", "🌨️"),
    95: ("Thunderstorm", "⛈️"), 96: ("Thunderstorm w/ hail", "⛈️"), 99: ("Severe thunderstorm", "⛈️"),
}


def c_to_f(c):
    return c * 9 / 5 + 32


def get_weather(cfg):
    params = {
        "latitude": cfg["latitude"],
        "longitude": cfg["longitude"],
        "daily": ",".join([
            "weather_code", "temperature_2m_max", "temperature_2m_min",
            "apparent_temperature_max", "precipitation_probability_max",
            "precipitation_sum", "uv_index_max", "wind_speed_10m_max",
        ]),
        "hourly": "relative_humidity_2m",
        "timezone": TIMEZONE,
        "forecast_days": 1,
    }
    url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read().decode())


def avg_humidity(data):
    try:
        hums = [h for h in data["hourly"]["relative_humidity_2m"] if h is not None]
        return round(sum(hums) / len(hums)) if hums else None
    except Exception:
        return None


def outfit_tip(tmax, rain_prob, uv, wind):
    tips = []
    if tmax >= 34:
        tips.append("Hot 🥵 — light, breathable cotton/linen in light colours.")
    elif tmax >= 28:
        tips.append("Warm 👕 — light, comfy clothing.")
    elif tmax >= 22:
        tips.append("Pleasant 🙂 — regular outfit; carry a light layer for evening.")
    else:
        tips.append("Cooler 🧥 — keep a light jacket/sweater handy.")
    if rain_prob >= 60:
        tips.append("High rain chance ☔ — umbrella + quick-dry footwear.")
    elif rain_prob >= 30:
        tips.append("Some rain possible 🌂 — pack a foldable umbrella.")
    if uv is not None and uv >= 8:
        tips.append("Very high UV 😎 — sunglasses + cap if out midday.")
    elif uv is not None and uv >= 6:
        tips.append("Moderate-high UV — sunglasses recommended.")
    if wind is not None and wind >= 30:
        tips.append("Breezy 💨 — secure loose items.")
    return tips


def skincare_tip(skin, humidity, uv, rain_prob):
    skin = (skin or "oily").lower()
    tips = []
    if skin == "oily":
        tips.append("Gentle foaming/salicylic-acid wash (AM & PM).")
        tips.append("Lightweight oil-free *gel* moisturiser — don't skip it.")
        if humidity is not None and humidity >= 70:
            tips.append("High humidity → keep blotting papers; avoid heavy creams.")
        else:
            tips.append("A hydrating toner helps balance oil.")
    elif skin == "dry":
        tips.append("Creamy non-foaming cleanser + rich moisturiser.")
        tips.append("Hyaluronic-acid serum on damp skin.")
    elif skin == "sensitive":
        tips.append("Fragrance-free cleanser + barrier-repair moisturiser.")
        tips.append("Avoid new actives today; patch-test anything new.")
    else:
        tips.append("Gentle cleanser; gel on T-zone, cream on dry areas.")
    if uv is not None and uv >= 6:
        tips.append("☀️ Sunscreen is a must — SPF 50, reapply if outdoors.")
    else:
        tips.append("Apply SPF 30–50 in the morning even if cloudy.")
    if rain_prob >= 50:
        tips.append("Rain & sweat clog pores — cleanse once home.")
    return tips


def build_message(cfg, data):
    d = data["daily"]
    code = d["weather_code"][0]
    desc, emoji = WMO.get(code, ("Unknown", "🌡️"))
    tmax = d["temperature_2m_max"][0]
    tmin = d["temperature_2m_min"][0]
    feels = d["apparent_temperature_max"][0]
    rain_prob = d["precipitation_probability_max"][0] or 0
    rain_sum = d["precipitation_sum"][0] or 0
    uv = d["uv_index_max"][0]
    wind = d["wind_speed_10m_max"][0]
    humidity = avg_humidity(data)
    today = datetime.datetime.now().strftime("%A, %d %b %Y")

    metric = cfg.get("units", "metric") != "imperial"
    if metric:
        temp_line = f"🌡️ {tmin:.0f}°C – {tmax:.0f}°C (feels {feels:.0f}°C)"
    else:
        temp_line = f"🌡️ {c_to_f(tmin):.0f}°F – {c_to_f(tmax):.0f}°F (feels {c_to_f(feels):.0f}°F)"

    rain_line = (
        f"☔ Rain chance: {rain_prob}%"
        + (f" (~{rain_sum} mm)" if rain_prob >= 30 else " — unlikely")
    )

    outfit = outfit_tip(tmax, rain_prob, uv, wind)
    skin = skincare_tip(cfg.get("skin_type"), humidity, uv, rain_prob)

    lines = [
        f"📍 {cfg['location_name']} · {today}",
        f"{emoji} {desc}",
        temp_line,
        (f"💧 Humidity: {humidity}%" if humidity is not None else ""),
        (f"☀️ UV index: {uv:.0f}" if uv is not None else ""),
        rain_line,
        "",
        "👗 Outfit:",
    ] + [f"• {t}" for t in outfit] + [
        "",
        f"🧴 Skincare ({cfg.get('skin_type','oily')} skin):",
    ] + [f"• {t}" for t in skin] + [
        "",
        "Have a great day! 🌟",
    ]
    body = "\n".join(l for l in lines if l != "" or True)
    title = f"{emoji} Weather Today — {tmax:.0f}°{'C' if metric else 'F'}"
    # tag emoji + rain warning tag for high chance
    tags = ["sun_with_face"] if code in (0, 1) else ["partly_sunny"]
    if rain_prob >= 50:
        tags = ["umbrella"]
    click = f"https://www.google.com/search?q=weather+{urllib.parse.quote(cfg['location_name'])}"
    return title, body, tags, click


def main():
    cfg = load_config()
    if not cfg.get("daily_enabled", True):
        print("Daily alerts disabled in config; nothing to do.")
        return
    data = get_weather(cfg)
    title, body, tags, click = build_message(cfg, data)
    print("----- NOTIFICATION -----")
    print("TITLE:", title)
    print(body)
    print("------------------------")
    if "--dry-run" in sys.argv:
        print("(dry run: not sending)")
        return
    send_push(cfg, title, body, tags=tags, priority="default", click=click)


if __name__ == "__main__":
    main()
