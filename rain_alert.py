#!/usr/bin/env python3
"""
Rain "~15 minutes before" push alert (via ntfy.sh).
Runs every 15 min, looks ahead 30 min, warns once per rain event.
Reads preferences from config.json. Pass --dry-run to preview.
"""

import os
import sys
import json
import datetime
import urllib.parse
import urllib.request

from notifier import load_config, send_push

TIMEZONE = "Asia/Kolkata"
COOLDOWN_MIN = 90
STATE_FILE = os.getenv("RAIN_STATE_FILE", os.path.join(os.path.dirname(__file__), "rain_state.json"))


def fetch(cfg):
    params = {
        "latitude": cfg["latitude"],
        "longitude": cfg["longitude"],
        "minutely_15": "precipitation",
        "timezone": TIMEZONE,
        "forecast_minutely_15": 12,
    }
    url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read().decode())


def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)
    except Exception as e:
        print("Could not save state:", e, file=sys.stderr)


def main():
    cfg = load_config()
    if not cfg.get("rain_enabled", True):
        print("Rain alerts disabled in config; nothing to do.")
        return

    threshold = float(cfg.get("rain_threshold_mm", 0.2))
    lookahead = int(cfg.get("rain_lookahead_min", 30))

    data = fetch(cfg)
    m = data.get("minutely_15", {})
    times, precip = m.get("time", []), m.get("precipitation", [])
    if not times:
        print("No minutely data available.")
        return

    now = datetime.datetime.now()
    steps = []
    for t, p in zip(times, precip):
        try:
            steps.append((datetime.datetime.fromisoformat(t), p or 0.0))
        except ValueError:
            pass

    raining_now = False
    for dt, p in steps:
        if dt <= now < dt + datetime.timedelta(minutes=15):
            raining_now = p >= threshold
            break

    upcoming = None
    horizon = now + datetime.timedelta(minutes=lookahead)
    for dt, p in steps:
        if now < dt <= horizon and p >= threshold:
            upcoming = (dt, p)
            break

    print(f"now={now:%H:%M} raining_now={raining_now} upcoming={upcoming}")

    if raining_now or upcoming is None:
        state = load_state()
        if upcoming is None and not raining_now and state.get("last_event"):
            state.pop("last_event", None)
            save_state(state)
        print("No alert needed.")
        return

    start_dt, p = upcoming
    minutes_away = round((start_dt - now).total_seconds() / 60)
    event_key = start_dt.strftime("%Y-%m-%dT%H:%M")

    state = load_state()
    if state.get("last_event") == event_key:
        print("Already alerted for this event.")
        return
    if state.get("last_sent"):
        try:
            if (now - datetime.datetime.fromisoformat(state["last_sent"])).total_seconds() < COOLDOWN_MIN * 60:
                print("Within cooldown; skipping.")
                return
        except ValueError:
            pass

    title = "🌧️ Rain incoming!"
    body = (
        f"📍 {cfg['location_name']}\n"
        f"Rain expected ~{start_dt:%I:%M %p} ({minutes_away} min away).\n"
        f"☔ Grab an umbrella before heading out!"
    )
    print("----- ALERT -----"); print(title); print(body); print("-----------------")

    if "--dry-run" in sys.argv:
        print("(dry run: not sending)")
        return

    send_push(cfg, title, body, tags=["umbrella", "rain_cloud"], priority="high")
    state["last_event"] = event_key
    state["last_sent"] = now.isoformat()
    save_state(state)


if __name__ == "__main__":
    main()
