"""Settings live in studio/.env (never leaves your computer)."""

import os
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "web"
DATA_DIR = ROOT / "data"
ENV_FILE = ROOT / ".env"
DATA_DIR.mkdir(exist_ok=True)

load_dotenv(ENV_FILE)

# YouTube Data API free quota per Google Cloud project, reset at midnight Pacific time.
DAILY_QUOTA = 10_000


def get(name, default=""):
    return (os.environ.get(name) or default).strip()


def region():
    return get("YT_REGION", "EG")


def lang():
    return get("YT_LANG", "ar")


def port():
    return int(get("PORT", "8765"))


def tz():
    return ZoneInfo(get("TIMEZONE", "Africa/Cairo"))


def niche_keywords():
    """Words that describe your niche (comma separated), used to filter trends and raise alerts."""
    return [w.strip() for w in get("NICHE_KEYWORDS").replace("،", ",").split(",") if w.strip()]


def rpm():
    """Your estimated revenue per 1,000 views in USD (check YouTube Studio for the real number)."""
    try:
        return float(get("RPM", "1.5"))
    except ValueError:
        return 1.5


def save(updates):
    """Write the given keys into .env, keeping every other line as it is."""
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []
    for key, value in updates.items():
        value = value.strip()
        line = f"{key}={value}"
        for i, existing in enumerate(lines):
            if existing.split("=", 1)[0].strip() == key:
                lines[i] = line
                break
        else:
            lines.append(line)
        os.environ[key] = value
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
