import re
from datetime import datetime, timezone

_DIACRITICS = re.compile(r"[ؗ-ًؚ-ْٰـ]")
_DURATION = re.compile(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?")
_VIDEO_IN_URL = re.compile(r"(?:v=|youtu\.be/|shorts/|embed/|live/)([A-Za-z0-9_-]{11})")
_VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}")


def normalize(text):
    """Lowercase and fold Arabic spelling variants so 'أداة' matches 'اداه'."""
    text = _DIACRITICS.sub("", (text or "").lower())
    text = re.sub("[أإآ]", "ا", text).replace("ة", "ه").replace("ى", "ي")
    return re.sub(r"\s+", " ", text).strip()


def has_phrase(text, phrase):
    return bool(phrase) and normalize(phrase) in normalize(text)


def has_all_words(text, phrase):
    words = normalize(phrase).split()
    target = normalize(text)
    return bool(words) and all(w in target for w in words)


def count_phrase(text, phrase):
    return normalize(text).count(normalize(phrase)) if phrase else 0


def parse_duration(iso):
    m = _DURATION.fullmatch(iso or "")
    if not m:
        return 0
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + s


def parse_time(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def age_days(iso):
    # Floor at half a day so views-per-day is not inflated for videos published minutes ago.
    return max((datetime.now(timezone.utc) - parse_time(iso)).total_seconds() / 86400, 0.5)


def video_id(text):
    text = (text or "").strip()
    if _VIDEO_ID.fullmatch(text):
        return text
    m = _VIDEO_IN_URL.search(text)
    return m.group(1) if m else None


def median(values):
    values = sorted(v for v in values if v is not None)
    if not values:
        return 0
    mid = len(values) // 2
    return values[mid] if len(values) % 2 else (values[mid - 1] + values[mid]) / 2


def clamp(x, lo=0, hi=100):
    return max(lo, min(hi, x))
