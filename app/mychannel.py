"""Your own channel through public data (API key only). Works without linking the channel with OAuth."""

from . import competitors, config, hourly, oauth, youtube
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
