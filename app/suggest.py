"""YouTube search autocomplete: free, no API key, no quota."""

from concurrent.futures import ThreadPoolExecutor

import httpx

from . import config, db, util

URL = "https://suggestqueries.google.com/complete/search"
DAY = 24 * 3600

ARABIC_LETTERS = "ابتثجحخدذرزسشصضطظعغفقكلمنهوي"
LATIN_LETTERS = "abcdefghijklmnopqrstuvwxyz"
QUESTION_WORDS = ["ازاي", "ليه", "ايه هو", "افضل", "طريقة", "شرح", "مقارنة"]

_client = httpx.Client(timeout=10)


def autocomplete(q):
    q = q.strip()
    if not q:
        return []
    cache_key = f"ac:{config.lang()}:{config.region()}:{q}"
    cached = db.cache_get(cache_key, DAY)
    if cached is not None:
        return cached
    response = _client.get(URL, params={"client": "firefox", "ds": "yt", "q": q, "hl": config.lang(), "gl": config.region()})
    response.raise_for_status()
    suggestions = response.json()[1]
    db.cache_set(cache_key, suggestions)
    return suggestions


def popularity(keyword):
    """0-100: how early YouTube autocompletes the exact phrase while it is being typed.

    A phrase suggested after typing a third of it is searched a lot; one that only shows up
    once fully typed is searched a little; one never suggested is rarely searched.
    """
    target = util.normalize(keyword)
    steps = [(0.35, 100), (0.5, 85), (0.65, 70), (0.8, 50), (1.0, 30)]
    tried = set()
    for fraction, score in steps:
        prefix = keyword[: max(2, round(len(keyword) * fraction))]
        if prefix in tried:
            continue
        tried.add(prefix)
        if any(util.normalize(s) == target for s in autocomplete(prefix)):
            return score
    return 0


def explore(keyword):
    """Long-tail ideas: the keyword followed by every letter, plus common question words in front."""
    keyword = keyword.strip()
    queries = [f"{keyword} {c}" for c in ARABIC_LETTERS + LATIN_LETTERS]
    queries += [f"{w} {keyword}" for w in QUESTION_WORDS]
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(_safe_autocomplete, queries))

    seen = {util.normalize(keyword)}
    ideas = []
    for suggestions in results:
        for s in suggestions:
            n = util.normalize(s)
            if n not in seen:
                seen.add(n)
                ideas.append(s)
    return ideas


def _safe_autocomplete(q):
    try:
        return autocomplete(q)
    except httpx.HTTPError:
        return []
