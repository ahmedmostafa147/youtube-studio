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


# Matching is by whole words: "AI" must not match "Trailer", and "دم" must not match "مقدمة".
_WORD = re.compile(r"[\w؀-ۿ]+")
_WORD_CHAR = r"[\w؀-ۿ]"
_AR_PREFIXES = ("وال", "بال", "فال", "كال", "لل", "ال", "و", "ف", "ب", "ل", "ك")


def _forms(word):
    """A word plus its forms without an Arabic article/conjunction or a Latin plural 's'."""
    forms = {word}
    for p in _AR_PREFIXES:
        if word.startswith(p) and len(word) - len(p) >= 2:
            forms.add(word[len(p):])
    if word.isascii() and word.endswith("s") and len(word) > 3:
        forms.add(word[:-1])
    return forms


def _tokens(text):
    tokens = set()
    for word in _WORD.findall(normalize(text)):
        tokens |= _forms(word)
    return tokens


def _phrase_re(phrase):
    # An Arabic one-letter prefix (و ف ب ل ك) may stick to the phrase: "بالذكاء الاصطناعي" contains "الذكاء الاصطناعي".
    return re.compile(rf"(?<!{_WORD_CHAR})[وفبلك]?{re.escape(normalize(phrase))}(?!{_WORD_CHAR})")


def has_phrase(text, phrase):
    return bool(phrase.strip()) and bool(_phrase_re(phrase).search(normalize(text)))


def has_all_words(text, phrase):
    words = _WORD.findall(normalize(phrase))
    tokens = _tokens(text)
    return bool(words) and all(_forms(w) & tokens for w in words)


def count_phrase(text, phrase):
    return len(_phrase_re(phrase).findall(normalize(text))) if phrase.strip() else 0


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
