"""YouTube Data API v3 client with caching and quota accounting.

Costs: search = 100 units, everything else we use = 1 unit per call (up to 50 ids per call).
"""

import json
import re
from urllib.parse import unquote

import httpx

from . import config, db, util

API = "https://www.googleapis.com/youtube/v3"
COST = {"search": 100}
HOUR = 3600
DAY = 24 * HOUR

_client = httpx.Client(timeout=20)


class YouTubeError(Exception):
    pass


def error_message(response):
    try:
        err = response.json()["error"]
        reason = (err.get("errors") or [{}])[0].get("reason", "")
        message = err.get("message", "")
    except (ValueError, KeyError, TypeError):
        return f"YouTube رد بخطأ {response.status_code}"
    if reason in ("quotaExceeded", "dailyLimitExceeded"):
        return "خلصت الـ quota بتاعة النهارده (10,000 وحدة). بتتجدد حوالي الساعة 10 الصبح بتوقيت مصر."
    if reason in ("keyInvalid",) or "API key not valid" in message:
        return "الـ YouTube API key مش صح. راجعه من صفحة الإعدادات."
    if reason == "commentsDisabled":
        return "الكومنتات مقفولة على الفيديو ده."
    if reason in ("videoNotFound", "notFound"):
        return "مش لاقي ده على يوتيوب. اتأكد من اللينك."
    if reason == "accessNotConfigured" or "has not been used in project" in message:
        return "الـ API مش متفعّل في مشروع Google Cloud بتاعك. فعّل YouTube Data API v3 و YouTube Analytics API."
    if reason == "forbidden" or response.status_code == 403:
        return f"جوجل رفضت الطلب: {message}"
    return message or f"YouTube رد بخطأ {response.status_code}"


def require_key():
    if not config.get("YOUTUBE_API_KEY"):
        raise YouTubeError("مفيش YouTube API key لسه. حطه من صفحة الإعدادات.")


def call(endpoint, params, ttl=0, token=None):
    """GET one Data API endpoint. Calls made with an OAuth token are never cached."""
    cache_key = f"yt:{endpoint}:{json.dumps(params, sort_keys=True, ensure_ascii=False)}"
    if ttl and not token:
        cached = db.cache_get(cache_key, ttl)
        if cached is not None:
            return cached

    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    else:
        require_key()
        params = {**params, "key": config.get("YOUTUBE_API_KEY")}

    response = _client.get(f"{API}/{endpoint}", params=params, headers=headers)
    # Google charges quota even for failed requests.
    db.add_quota(COST.get(endpoint, 1))
    if response.status_code != 200:
        raise YouTubeError(error_message(response))
    data = response.json()
    if ttl and not token:
        db.cache_set(cache_key, data)
    return data


def _chunks(items, size):
    items = list(items)
    for i in range(0, len(items), size):
        yield items[i:i + size]


def videos(ids, ttl=6 * HOUR, token=None):
    out = []
    for chunk in _chunks(ids, 50):
        res = call("videos", {"part": "snippet,statistics,contentDetails", "id": ",".join(chunk), "maxResults": 50}, ttl, token)
        out.extend(res.get("items", []))
    return out


def channels(ids, ttl=DAY):
    out = []
    for chunk in _chunks(ids, 50):
        res = call("channels", {"part": "snippet,statistics,contentDetails", "id": ",".join(chunk), "maxResults": 50}, ttl)
        out.extend(res.get("items", []))
    return out


def search(q, max_results=25):
    res = call(
        "search",
        {
            "part": "id", "type": "video", "q": q, "maxResults": max_results,
            "regionCode": config.region(), "relevanceLanguage": config.lang(),
        },
        ttl=DAY,
    )
    return [item["id"]["videoId"] for item in res.get("items", []) if item["id"].get("videoId")]


def find_channel(text):
    """Accepts a channel URL, @handle, UC… id, or a plain name (a name costs a 100-unit search)."""
    text = unquote((text or "").strip())
    if m := re.search(r"(UC[\w-]{22})", text):
        params = {"id": m.group(1)}
    elif m := re.search(r"@([^/?#\s]+)", text):
        params = {"forHandle": "@" + m.group(1)}
    elif m := re.search(r"youtube\.com/user/([^/?#\s]+)", text):
        params = {"forUsername": m.group(1)}
    else:
        res = call("search", {"part": "snippet", "type": "channel", "q": text, "maxResults": 1}, ttl=DAY)
        items = res.get("items") or []
        if not items:
            raise YouTubeError("ملقيتش قناة بالاسم ده. جرّب تحط لينك القناة أو الـ @handle.")
        params = {"id": items[0]["snippet"]["channelId"]}
    res = call("channels", {"part": "snippet,statistics,contentDetails", **params}, ttl=HOUR)
    items = res.get("items") or []
    if not items:
        raise YouTubeError("ملقيتش القناة دي. اتأكد من اللينك أو الـ @handle.")
    return items[0]


def uploads(channel, ttl=6 * HOUR, token=None, limit=50):
    """Latest uploads of a channel item (from channels.list) as raw video items."""
    playlist = channel["contentDetails"]["relatedPlaylists"]["uploads"]
    res = call("playlistItems", {"part": "contentDetails", "playlistId": playlist, "maxResults": min(limit, 50)}, ttl, token)
    ids = [item["contentDetails"]["videoId"] for item in res.get("items", [])]
    return videos(ids, ttl, token)


def best_thumb(snippet):
    thumbs = snippet.get("thumbnails", {})
    for size in ("medium", "high", "default"):
        if size in thumbs:
            return thumbs[size]["url"]
    return ""


def summary(item):
    """Flatten a videos.list item into the fields the app uses."""
    s, st, cd = item["snippet"], item.get("statistics", {}), item.get("contentDetails", {})
    views = int(st.get("viewCount", 0))
    age = util.age_days(s["publishedAt"])
    duration = util.parse_duration(cd.get("duration"))
    return {
        "id": item["id"],
        "title": s.get("title", ""),
        "description": s.get("description", ""),
        "tags": s.get("tags", []),
        "channel_id": s.get("channelId"),
        "channel_title": s.get("channelTitle", ""),
        "published": s["publishedAt"],
        "age_days": round(age, 1),
        "views": views,
        "likes": int(st["likeCount"]) if "likeCount" in st else None,
        "comments": int(st["commentCount"]) if "commentCount" in st else None,
        "vpd": round(views / age, 1),
        "duration": duration,
        # Shorts can be up to 3 minutes; the API has no explicit Shorts flag.
        "is_short": 0 < duration <= 180,
        "thumbnail": best_thumb(s),
    }


def channel_summary(item):
    s, st = item["snippet"], item.get("statistics", {})
    return {
        "id": item["id"],
        "title": s.get("title", ""),
        "handle": s.get("customUrl", ""),
        "thumbnail": best_thumb(s),
        "subs": int(st.get("subscriberCount", 0)),
        "subs_hidden": st.get("hiddenSubscriberCount", False),
        "video_count": int(st.get("videoCount", 0)),
        "view_count": int(st.get("viewCount", 0)),
    }
