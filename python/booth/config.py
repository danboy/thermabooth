"""Runtime configuration, read from data/config.json on every call so edits apply without a restart."""

import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
SESSIONS_DIR = DATA_DIR / "sessions"
CONFIG_PATH = DATA_DIR / "config.json"

DEFAULTS = {
    "photos_per_session": 4,
    "countdown_seconds": 3,
    "keep_sessions_hours": 24,
    # Base URL phones use to reach this board, e.g. "http://192.168.1.50:7000".
    # Leave empty to derive it from the request the touch screen made.
    "public_base_url": "",
    "smtp": {
        "host": "",
        "port": 587,
        "username": "",
        "password": "",
        "from": "",
        "starttls": True,
    },
    "twilio": {"account_sid": "", "auth_token": "", "from": ""},
    "printer": {"enabled": True, "device_name": "INSTAX-", "device_address": ""},
}


def load() -> dict:
    cfg = json.loads(json.dumps(DEFAULTS))
    try:
        user = json.loads(CONFIG_PATH.read_text())
    except (OSError, ValueError):
        user = {}
    for key, value in user.items():
        if isinstance(value, dict) and isinstance(cfg.get(key), dict):
            cfg[key].update(value)
        else:
            cfg[key] = value
    return cfg


def email_enabled(cfg: dict) -> bool:
    return bool(cfg["smtp"]["host"] and cfg["smtp"]["from"])


def sms_enabled(cfg: dict) -> bool:
    t = cfg["twilio"]
    return bool(t["account_sid"] and t["auth_token"] and t["from"])
