"""Your own channel through public data (API key only). Works without linking the channel with OAuth."""

import time

from . import competitors, config, hourly, oauth, util, youtube
from .youtube import YouTubeError

HOUR = 3600


def channel_id():
    cid = config.get("MY_CHANNEL_ID")
    if cid:
        return cid
    if oauth.connected():
        from . import analytics
        cid = analytics.me()["id"]
        config.save({"MY_CHANNEL_ID": cid})
        return cid
    raise YouTubeError("حط لينك قناتك في الإعدادات الأول (أو اربطها من صفحة «قناتي»).")


def set_channel(text):
    item = youtube.find_channel(text)
    config.save({"MY_CHANNEL_ID": item["id"]})
    return youtube.channel_summary(item)


def channel(ttl=HOUR):
    items = youtube.channels([channel_id()], ttl=ttl)
    if not items:
        raise YouTubeError("قناتك مش ظاهرة. اتأكد من اللينك في الإعدادات.")
    return items[0]


def recent(limit=10):
    """Latest uploads with current views, views per hour and last-48h views. Also records history."""
    item = channel(ttl=0)
    summary = youtube.channel_summary(item)
    competitors.snapshot_channel(summary)
    videos = [youtube.summary(v) for v in youtube.uploads(item, ttl=0)]
    hourly.record(videos)
    videos = videos[:limit]
    per_hour = hourly.vph([v["id"] for v in videos])
    for v in videos:
        v["vph"] = per_hour.get(v["id"])
        v["last_48h"] = hourly.last_48h(v["id"])
        del v["description"]
    return {"channel": summary, "videos": videos}


def _verdict(v, usual):
    """Plain-language verdict for one video against the channel's usual views for its format."""
    if v["age_days"] < 2:
        return "new", "لسه جديد، استنى يومين"
    if not usual:
        return "unknown", "مفيش فيديوهات كفاية للمقارنة"
    ratio = v["views"] / usual
    if v["age_days"] < 7 and ratio < 1:
        # The usual comes from older videos' lifetime views, so a young video below it isn't behind yet.
        return "growing", f"لسه بيكبر: وصل {ratio:.0%} من المعتاد في {v['age_days']:.0f} أيام"
    if ratio >= 2:
        return "great", f"أحسن من المعتاد بكتير (×{ratio:.1f})"
    if ratio >= 1.2:
        return "good", f"أحسن من المعتاد (×{ratio:.1f})"
    if ratio >= 0.8:
        return "normal", "زي المعتاد"
    return "low", f"أقل من المعتاد (×{ratio:.1f})"


def home():
    """Everything the home page shows about your channel, from public YouTube data (about 3 quota units)."""
    from . import insights  # imported here: insights imports this module

    item = channel(ttl=600)
    c = youtube.channel_summary(item)
    competitors.snapshot_channel(c)
    videos = [youtube.summary(v) for v in youtube.uploads(item, ttl=600)]
    hourly.record(videos)
    settled = [v for v in videos if v["age_days"] >= 7]
    usual = {fmt: util.median([v["views"] for v in settled if v["is_short"] == fmt]) for fmt in (False, True)}

    recent = videos[:8]
    per_hour = hourly.vph([v["id"] for v in recent])
    for v in recent:
        v["vph"] = per_hour.get(v["id"])
        v["usual"] = round(usual[v["is_short"]])
        v["verdict"], v["verdict_text"] = _verdict(v, usual[v["is_short"]])
        v.pop("description", None)
        v.pop("tags", None)

    last30 = [v for v in videos if v["age_days"] <= 30]
    prev30 = [v for v in videos if 30 < v["age_days"] <= 60]
    growth = competitors.growth(c["id"], 30)

    audit = insights.audit()
    fixes = [ch for ch in audit["checks"] if ch["status"] == "fail"] + [ch for ch in audit["checks"] if ch["status"] == "warn"]
    return {
        "channel": c,
        "updated": time.time(),
        "usual": {"long": round(usual[False]), "short": round(usual[True])},
        "last30": {"videos": len(last30), "views": sum(v["views"] for v in last30)},
        "prev30": {"videos": len(prev30), "views": sum(v["views"] for v in prev30)},
        "subs_growth": growth,
        "recent": recent,
        "health": {"score": audit["score"], "fixes": fixes[:3]},
    }


def uploads_all(item, max_pages=40):
    """Every upload of a channel item, 50 per page (1 quota unit per page, plus 1 per 50 videos for stats)."""
    playlist = item["contentDetails"]["relatedPlaylists"]["uploads"]
    ids, token = [], None
    for _ in range(max_pages):
        params = {"part": "contentDetails", "playlistId": playlist, "maxResults": 50}
        if token:
            params["pageToken"] = token
        res = youtube.call("playlistItems", params)
        ids += [i["contentDetails"]["videoId"] for i in res.get("items", [])]
        token = res.get("nextPageToken")
        if not token:
            break
    return [youtube.summary(v) for v in youtube.videos(ids, ttl=0)]
