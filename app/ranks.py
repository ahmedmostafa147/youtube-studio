"""Where your videos rank in YouTube search: tag rankings, daily rank tracking for chosen keywords, brand alerts.

All of this uses search.list, the most expensive call: 100 quota units per keyword per check (the free daily
quota is 10,000). Tracking N keywords costs N × 100 units every day, so the number of keywords is capped in Settings.
"""

import time
from datetime import datetime, timedelta, timezone

from . import alerts, config, db, util, youtube
from .youtube import YouTubeError

HOUR = 3600
SEARCH_COST = youtube.COST["search"]
DEPTH = 50  # one search call returns at most 50 results


def max_keywords():
    try:
        return max(0, min(int(config.get("RANK_MAX_KEYWORDS", "5")), 50))
    except ValueError:
        return 5


def today():
    return datetime.now(config.tz()).date().isoformat()


def _search(q, ttl=20 * HOUR, **extra):
    res = youtube.call("search", {
        "part": "snippet", "type": "video", "q": q, "maxResults": DEPTH,
        "regionCode": config.region(), "relevanceLanguage": config.lang(), **extra,
    }, ttl=ttl)
    return [{"id": i["id"]["videoId"], "title": i["snippet"].get("title", ""), "channel_id": i["snippet"].get("channelId"),
             "channel_title": i["snippet"].get("channelTitle", ""), "thumbnail": youtube.best_thumb(i["snippet"])}
            for i in res.get("items", []) if i["id"].get("videoId")]


def _afford(searches):
    need, left = searches * SEARCH_COST, config.DAILY_QUOTA - db.quota_used()
    if need > left:
        raise YouTubeError(f"ده محتاج {need:,} وحدة والباقي النهارده {max(left, 0):,}.")


# ---------- tag rankings ----------

def tag_rankings(url, tags=None, limit=5):
    """Rank of one video for each of its tags (or the tags given) in the top 50 results. 100 units per tag."""
    vid = util.video_id(url)
    if not vid:
        raise YouTubeError("ده مش لينك فيديو يوتيوب.")
    items = youtube.videos([vid], ttl=HOUR)
    if not items:
        raise YouTubeError("الفيديو ده مش موجود أو خاص.")
    v = youtube.summary(items[0])
    tags = [t.strip() for t in (tags or v["tags"]) if t.strip()][:max(1, min(limit, 10))]
    if not tags:
        raise YouTubeError("الفيديو ده مفيهوش تاجز. اكتب الكلمات اللي عاوز تشوف ترتيبك فيها.")
    _afford(len(tags))
    rows = []
    for tag in tags:
        results = _search(tag)
        rank = next((i for i, r in enumerate(results, 1) if r["id"] == vid), None)
        rows.append({"tag": tag, "rank": rank, "leader": results[0]["title"] if results else ""})
    rows.sort(key=lambda r: r["rank"] or 999)
    return {"video": {"id": vid, "title": v["title"], "thumbnail": v["thumbnail"]}, "rows": rows,
            "cost": len(tags) * SEARCH_COST, "depth": DEPTH}


# ---------- daily rank tracking ----------

def keywords():
    rows = db.query("SELECT * FROM rank_keywords ORDER BY added")
    for r in rows:
        hist = db.query("SELECT day, rank, video_id, video_title FROM rank_history WHERE keyword = ? ORDER BY day DESC LIMIT 30",
                        (r["keyword"],))
        r["history"] = hist[::-1]
        r["latest"] = hist[0] if hist else None
        prev = next((h for h in hist[1:] if h["rank"]), None) if hist else None
        r["change"] = (prev["rank"] - hist[0]["rank"]) if prev and hist[0]["rank"] else None
    return {"keywords": rows, "max": max_keywords(), "daily_cost": len(rows) * SEARCH_COST, "depth": DEPTH}


def add_keyword(keyword, url=""):
    keyword = " ".join((keyword or "").split())
    if not keyword:
        raise ValueError("اكتب الكلمة.")
    count = len(db.query("SELECT keyword FROM rank_keywords"))
    if not db.query("SELECT 1 FROM rank_keywords WHERE keyword = ?", (keyword,)) and count >= max_keywords():
        raise ValueError(f"وصلت للحد ({max_keywords()} كلمات = {max_keywords() * SEARCH_COST} وحدة كل يوم). شيل كلمة أو زوّد الحد من الإعدادات.")
    vid = util.video_id(url) if url.strip() else None
    if url.strip() and not vid:
        raise YouTubeError("ده مش لينك فيديو يوتيوب.")
    db.execute("INSERT OR REPLACE INTO rank_keywords (keyword, video_id, added) VALUES (?, ?, ?)", (keyword, vid, time.time()))
    return keywords()


def remove_keyword(keyword):
    db.execute("DELETE FROM rank_keywords WHERE keyword = ?", (keyword,))
    db.execute("DELETE FROM rank_history WHERE keyword = ?", (keyword,))
    return keywords()


def check_ranks(force=False):
    """Search each tracked keyword once a day and record the best rank of your video (or the chosen one)."""
    day, mine = today(), config.get("MY_CHANNEL_ID")
    rows = db.query("SELECT * FROM rank_keywords")
    due = [r for r in rows if force or not db.query("SELECT 1 FROM rank_history WHERE keyword = ? AND day = ?", (r["keyword"], day))]
    if due and not mine and any(not r["video_id"] for r in due):
        raise YouTubeError("حط لينك قناتك في الإعدادات عشان أعرف أنهي فيديوهات بتاعتك.")
    checked = 0
    for r in due:
        if db.quota_used() + SEARCH_COST > config.DAILY_QUOTA:
            break
        results = _search(r["keyword"], ttl=0 if force else 20 * HOUR)
        hit = next(((i, x) for i, x in enumerate(results, 1)
                    if (x["id"] == r["video_id"] if r["video_id"] else x["channel_id"] == mine)), (None, None))
        db.execute("INSERT OR REPLACE INTO rank_history (keyword, day, rank, video_id, video_title) VALUES (?, ?, ?, ?, ?)",
                   (r["keyword"], day, hit[0], hit[1]["id"] if hit[1] else None, hit[1]["title"] if hit[1] else None))
        checked += 1
    return checked


# ---------- brand alerts ----------

def brand_query():
    return config.get("BRAND_QUERY") or config.get("MY_CHANNEL_TITLE")


def brand_check(force=False):
    """Once a day: search the channel name for new videos by other channels (100 units). Raises alerts."""
    if config.get("BRAND_ALERTS") != "1" and not force:
        return "off"
    q = brand_query()
    if not q:
        raise YouTubeError("حط اسم قناتك أو الكلمة اللي عاوز تتابعها في الإعدادات.")
    day = today()
    if not force and db.cache_get("brand:last", 2 * 86400) == day:
        return "already checked today"
    since = (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    results = _search(f'"{q}"', ttl=0, order="date", publishedAfter=since)
    mine, found = config.get("MY_CHANNEL_ID"), 0
    for r in results:
        if r["channel_id"] == mine:
            continue
        alerts.add(f"brand:{r['id']}", "brand", f"ذكر «{q}»: {r['title']}", r["channel_title"],
                   f"https://www.youtube.com/watch?v={r['id']}", r["thumbnail"])
        found += 1
    db.cache_set("brand:last", day)
    return found
