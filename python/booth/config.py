"""Runtime configuration, read from environment variables (and the app's .env file)."""

import os
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = APP_DIR / "data"
SESSIONS_DIR = DATA_DIR / "sessions"
ENV_PATH = APP_DIR / ".env"


def _read_dotenv(path: Path) -> dict[str, str]:
    values = {}
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return values
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    return values


def _bool(value: str) -> bool:
    return value.strip().lower() not in ("0", "false", "no", "off", "")


def load() -> dict:
    """Read .env on every call so edits apply without a restart. Real environment variables win."""
    env = {**_read_dotenv(ENV_PATH), **os.environ}
    get = lambda k, d="": env.get(k, d).strip()  # noqa: E731
    return {
        "photos_per_session": int(get("PHOTOS_PER_SESSION", "4") or 4),
        "countdown_seconds": int(get("COUNTDOWN_SECONDS", "3") or 3),
        "keep_sessions_hours": float(get("KEEP_SESSIONS_HOURS", "24") or 24),
        # Base URL phones use to reach this board, e.g. http://192.168.1.50:7000.
        # Empty = derive it from the request the touch screen made.
        "public_base_url": get("PUBLIC_BASE_URL"),
        "mailgun": {
            "api_key": get("MAILGUN_API_KEY"),
            "domain": get("MAILGUN_DOMAIN"),
            "from": get("MAILGUN_FROM"),
            "region": get("MAILGUN_REGION", "us").lower(),
        },
        "twilio": {
            "account_sid": get("TWILIO_ACCOUNT_SID"),
            "auth_token": get("TWILIO_AUTH_TOKEN"),
            "from": get("TWILIO_FROM"),
        },
        "printer": {
            "enabled": _bool(get("PRINTER_ENABLED", "true")),
            # Blank device_name = autodiscover by BLE service UUID (works for most cat-printer clones).
            "device_name": get("PRINTER_DEVICE_NAME"),
            "device_address": get("PRINTER_DEVICE_ADDRESS"),
            # Darkness: 0x0000 (light) to 0xffff (darkest, default).
            "energy": int(get("PRINTER_ENERGY", "0xffff") or "0xffff", 16),
            # Print helper on the host (see host/). Blank helper_url = the docker host on port 8765.
            "helper_url": get("PRINT_HELPER_URL"),
            "helper_token": get("PRINT_HELPER_TOKEN"),
        },
    }


def email_enabled(cfg: dict) -> bool:
    return bool(cfg["mailgun"]["api_key"] and cfg["mailgun"]["domain"])


def sms_enabled(cfg: dict) -> bool:
    t = cfg["twilio"]
    return bool(t["account_sid"] and t["auth_token"] and t["from"])
