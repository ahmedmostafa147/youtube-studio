"""YouTube's trending ("most popular") list for your region, filtered to your niche."""

from . import alerts, config, db, util, youtube
from .youtube import YouTubeError

HOUR = 3600
# Categories checked for niche alerts besides the overall chart: Science & Technology, Education.
ALERT_CATEGORIES = ["", "28", "27"]


def categories():
    res = youtube.call("videoCategories", {"part": "snippet", "regionCode": config.region(), "hl": config.lang()}, ttl=7 * 24 * HOUR)
    return [{"id": c["id"], "title": c["snippet"]["title"]} for c in res.get("items", []) if c["snippet"].get("assignable")]


def trending(category_id="", limit=50):
    """Up to 50 most popular videos in your region (1 quota unit)."""
    params = {"part": "snippet,statistics,contentDetails", "chart": "mostPopular",
              "regionCode": config.region(), "maxResults": min(limit, 50)}
    if category_id:
        params["videoCategoryId"] = category_id
    res = youtube.call("videos", params, ttl=HOUR)
    videos = []
    for rank, item in enumerate(res.get("items", []), 1):
        v = youtube.summary(item)
        v["rank"] = rank
        v["niche"] = matches_niche(v)
        del v["description"]
        videos.append(v)
    return videos


def matches_niche(v):
    # Titles only: tags are often stuffed with popular words (an AI-generated song tags itself "AI", "Gemini").
    return any(util.has_all_words(v["title"], w) for w in config.niche_keywords())


def check_alerts():
    """Alert on trending videos that match your niche keywords (about 3 quota units)."""
    if not config.niche_keywords():
        return 0
    # Drop earlier trend alerts that no longer match (older versions matched "AI" inside "Trailer").
    for a in db.query("SELECT id, body FROM alerts WHERE kind = 'trend'"):
        if not matches_niche({"title": a["body"]}):
            db.execute("DELETE FROM alerts WHERE id = ?", (a["id"],))
    found = 0
    for cat in ALERT_CATEGORIES:
        try:
            videos = trending(cat)
        except YouTubeError:
            # Some regions don't have a chart for every category.
            continue
        for v in videos:
            if v["niche"]:
                found += 1
                alerts.add(f"trend:{v['id']}", "trend", f"فيديو في مجالك دخل الترند (#{v['rank']})", v["title"],
                           f"https://www.youtube.com/watch?v={v['id']}", v["thumbnail"])
    return found
