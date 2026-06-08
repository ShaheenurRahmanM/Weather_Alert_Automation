#!/usr/bin/env python3
"""
Shared helpers: load config + send a push notification via ntfy.sh.

ntfy.sh is a free, open-source push-notification service. You install the
ntfy app (Android / iOS / web), subscribe to a *topic* (any secret name you
choose), and anything POSTed to https://ntfy.sh/<topic> pops up as a push
notification. No account, no API key, no rate-limit hassle.

The topic name acts like a password, so keep it secret & hard to guess.
"""

import os
import json
import base64
import urllib.request


def _encode_header(value):
    """HTTP headers must be ISO-8859-1. Emoji/Unicode aren't, so if the value
    contains non-Latin-1 chars we encode it as RFC 2047 base64 (=?UTF-8?B?..?=),
    which ntfy decodes back to the original text."""
    try:
        value.encode("latin-1")
        return value  # plain ASCII/Latin-1, safe as-is
    except UnicodeEncodeError:
        b64 = base64.b64encode(value.encode("utf-8")).decode("ascii")
        return "=?UTF-8?B?" + b64 + "?="

CONFIG_PATH = os.getenv("CONFIG_PATH", os.path.join(os.path.dirname(__file__), "config.json"))


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    # Environment variables override the file (handy for GitHub Actions secrets)
    env_map = {
        "NTFY_TOPIC": "ntfy_topic",
        "NTFY_SERVER": "ntfy_server",
        "LOCATION_NAME": "location_name",
        "LATITUDE": "latitude",
        "LONGITUDE": "longitude",
        "SKIN_TYPE": "skin_type",
        "UNITS": "units",
    }
    for env_key, cfg_key in env_map.items():
        val = os.getenv(env_key)
        if val:
            if cfg_key in ("latitude", "longitude"):
                cfg[cfg_key] = float(val)
            else:
                cfg[cfg_key] = val
    return cfg


def send_push(cfg, title, message, tags=None, priority="default", click=None):
    """Send a push notification through ntfy. Returns the server response text."""
    server = cfg.get("ntfy_server", "https://ntfy.sh").rstrip("/")
    topic = cfg["ntfy_topic"]
    if not topic or "REPLACE" in topic:
        raise SystemExit(
            "ERROR: ntfy_topic is not set. Edit config.json (or set NTFY_TOPIC) "
            "to a secret topic name, e.g. 'kovai-weather-7h3k9'."
        )
    url = f"{server}/{topic}"

    headers = {
        "Title": _encode_header(title),
        "Priority": str(priority),
        "Content-Type": "text/plain; charset=utf-8",
    }
    if tags:
        headers["Tags"] = ",".join(tags)
    if click:
        headers["Click"] = _encode_header(click)

    req = urllib.request.Request(
        url, data=message.encode("utf-8"), headers=headers, method="POST"
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        body = r.read().decode(errors="replace")
    print(f"ntfy -> {url} : {body[:200]}")
    return body
