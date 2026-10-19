"""Keyword score from the first page of YouTube results.

vidIQ and TubeBuddy estimate search volume from data we don't have. We approximate:
- demand: how fast the top results gain views, plus how early autocomplete suggests the phrase.
- competition: how big the ranking channels are and how many target the phrase in their title.
"""

import math
from collections import Counter

from . import db, suggest, util, youtube

CACHE_PREFIX = "kw:"


def log_score(value, top):
    """Map value onto 0-100 on a log scale where `top` scores 100."""
    return util.clamp(math.log10(value + 1) / math.log10(top + 1) * 100)


def label(score):
    if score >= 70:
        return "ممتاز"
    if score >= 50:
        return "كويس"
    if score >= 35:
        return "متوسط"
    return "ضعيف"


def analyze(keyword):
    keyword = keyword.strip()
    youtube.require_key()
    suggestions = suggest.autocomplete(keyword)
    popularity = suggest.popularity(keyword)

    ids = youtube.search(keyword, 25)
    order = {vid: i for i, vid in enumerate(ids)}
    videos = sorted((youtube.summary(v) for v in youtube.videos(ids)), key=lambda v: order[v["id"]])
    if not videos:
        return {"keyword": keyword, "empty": True, "suggestions": suggestions}

    subs = {c["id"]: int(c.get("statistics", {}).get("subscriberCount", 0))
            for c in youtube.channels({v["channel_id"] for v in videos})}
    for v in videos:
        v["subs"] = subs.get(v["channel_id"], 0)
        v["title_match"] = util.has_all_words(v["title"], keyword)
        v["outlier"] = round(v["views"] / max(v["subs"], 100), 2)
        del v["description"]

    top = videos[:10]
    median_vpd = util.median([v["vpd"] for v in top])
    median_subs = util.median([v["subs"] for v in top])
    match_pct = round(sum(v["title_match"] for v in top) / len(top) * 100)
    fresh_pct = round(sum(v["age_days"] <= 180 for v in top) / len(top) * 100)
    small_channels = sum(v["subs"] < 10_000 for v in top)

    demand = round(0.75 * log_score(median_vpd, 20_000) + 0.25 * popularity)
    competition = round(0.6 * log_score(median_subs, 5_000_000) + 0.4 * match_pct)
    overall = round(util.clamp(0.55 * demand + 0.45 * (100 - competition)))

    notes = []
    if small_channels >= 3:
        notes.append(f"فيه {small_channels} قنوات صغيرة (أقل من 10K مشترك) في أول 10 نتايج. الموضوع ده ممكن تكسب فيه.")
    if match_pct < 40:
        notes.append("أغلب النتايج مش حاطة الكلمة دي في العنوان. لو حطيتها بالظبط هتبقى ميزة ليك.")
    if fresh_pct < 30:
        notes.append("أغلب النتايج قديمة (أكتر من 6 شهور). فيه فرصة لفيديو جديد ومحدّث.")
    if median_vpd < 20:
        notes.append("الطلب ضعيف: أول النتايج بتجيب أقل من 20 مشاهدة في اليوم. جرّب صياغة أشهر.")
    if popularity == 0:
        notes.append("يوتيوب مش بيقترح الجملة دي في البحث، يعني الناس نادرًا بتكتبها كده.")
    outliers = [v for v in videos if v["outlier"] >= 3 and v["views"] >= 1000]
    if outliers:
        notes.append(f"فيه {len(outliers)} فيديو جابوا مشاهدات أكتر من 3 أضعاف مشتركين قناتهم. شوف عملوا إيه.")

    tag_counts = Counter()
    for v in videos:
        tag_counts.update({t.strip().lower() for t in v["tags"] if t.strip()})

    result = {
        "keyword": keyword,
        "scores": {
            "overall": overall, "overall_label": label(overall),
            "demand": demand, "competition": competition, "popularity": popularity,
        },
        "stats": {
            "median_vpd": round(median_vpd), "median_subs": round(median_subs),
            "match_pct": match_pct, "fresh_pct": fresh_pct, "small_channels": small_channels,
        },
        "notes": notes,
        "suggestions": [s for s in suggestions if util.normalize(s) != util.normalize(keyword)],
        "tags": [{"tag": t, "count": c} for t, c in tag_counts.most_common(30)],
        "videos": videos,
    }
    db.cache_set(CACHE_PREFIX + util.normalize(keyword), result)
    return result


def cached(keyword, max_age=7 * 24 * 3600):
    """The last analysis of a keyword, without spending quota (None if never analyzed recently)."""
    return db.cache_get(CACHE_PREFIX + util.normalize(keyword), max_age)
