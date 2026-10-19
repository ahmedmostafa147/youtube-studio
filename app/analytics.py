"""Your own channel through the YouTube Analytics API (separate quota from the Data API)."""

import json
from datetime import date, timedelta

import httpx

from . import db, oauth, youtube

REPORTS = "https://youtubeanalytics.googleapis.com/v2/reports"
HOUR = 3600
# Analytics data lags about two days behind.
LAG_DAYS = 2

TRAFFIC_LABELS = {
    "YT_SEARCH": "بحث يوتيوب",
    "RELATED_VIDEO": "الفيديوهات المقترحة",
    "SUBSCRIBER": "الصفحة الرئيسية والاشتراكات",
    "YT_OTHER_PAGE": "صفحات تانية في يوتيوب",
    "YT_CHANNEL": "صفحة القناة",
    "EXT_URL": "مواقع خارجية",
    "NO_LINK_OTHER": "مباشر أو غير معروف",
    "NO_LINK_EMBEDDED": "فيديو متضمّن في مواقع",
    "PLAYLIST": "قوائم التشغيل",
    "YT_PLAYLIST_PAGE": "صفحة قائمة التشغيل",
    "SHORTS": "فيد الشورتس",
    "NOTIFICATION": "الإشعارات",
    "END_SCREEN": "شاشة النهاية",
    "ANNOTATION": "الكروت",
    "HASHTAGS": "صفحات الهاشتاج",
    "ADVERTISING": "إعلانات",
    "CAMPAIGN_CARD": "كروت الحملات",
    "SOUND_PAGE": "صفحات الصوت",
    "VIDEO_REMIXES": "ريمكس الفيديوهات",
    "PRODUCT_PAGE": "صفحات المنتجات",
    "LIVE_REDIRECT": "تحويل من بث مباشر",
    "PROMOTED": "ترويج",
}

OVERVIEW_METRICS = ("views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,"
                    "subscribersGained,subscribersLost,likes,comments,shares")


def window(days):
    end = date.today() - timedelta(days=LAG_DAYS)
    return end - timedelta(days=days - 1), end


def report(metrics, start, end, **extra):
    params = {"ids": "channel==MINE", "startDate": start.isoformat(), "endDate": end.isoformat(), "metrics": metrics, **extra}
    cache_key = "an:" + json.dumps(params, sort_keys=True)
    cached = db.cache_get(cache_key, HOUR)
    if cached is not None:
        return cached
    token = oauth.access_token()
    response = httpx.get(REPORTS, params=params, headers={"Authorization": f"Bearer {token}"}, timeout=30)
    if response.status_code == 401:
        raise oauth.AuthError("انتهت صلاحية ربط القناة. اربطها تاني.")
    if response.status_code != 200:
        raise youtube.YouTubeError(youtube.error_message(response))
    data = response.json()
    names = [h["name"] for h in data.get("columnHeaders", [])]
    rows = [dict(zip(names, row)) for row in data.get("rows") or []]
    db.cache_set(cache_key, rows)
    return rows


def me():
    res = youtube.call("channels", {"part": "snippet,statistics,contentDetails", "mine": "true"}, token=oauth.access_token())
    items = res.get("items") or []
    if not items:
        raise youtube.YouTubeError("الحساب ده مفيهوش قناة يوتيوب.")
    return youtube.channel_summary(items[0])


def overview(days):
    start, end = window(days)
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=days - 1)
    current = report(OVERVIEW_METRICS, start, end)
    previous = report(OVERVIEW_METRICS, prev_start, prev_end)
    daily = report("views,estimatedMinutesWatched,subscribersGained,subscribersLost", start, end, dimensions="day", sort="day")
    return {
        "start": start.isoformat(), "end": end.isoformat(),
        "current": current[0] if current else {},
        "previous": previous[0] if previous else {},
        "daily": daily,
    }


def top_videos(days):
    start, end = window(days)
    rows = report(
        "views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,likes,subscribersGained",
        start, end, dimensions="video", sort="-views", maxResults=50,
    )
    info = {v["id"]: youtube.summary(v) for v in youtube.videos([r["video"] for r in rows], token=oauth.access_token())}
    for r in rows:
        v = info.get(r["video"], {})
        r["title"] = v.get("title", r["video"])
        r["thumbnail"] = v.get("thumbnail", "")
        r["published"] = v.get("published")
        r["duration"] = v.get("duration")
        r["is_short"] = v.get("is_short", False)
    return rows


def traffic(days):
    start, end = window(days)
    rows = report("views,estimatedMinutesWatched", start, end, dimensions="insightTrafficSourceType", sort="-views")
    for r in rows:
        r["label"] = TRAFFIC_LABELS.get(r["insightTrafficSourceType"], r["insightTrafficSourceType"])
    return rows


def search_terms(days):
    """The real searches that brought viewers to your videos."""
    start, end = window(days)
    return report(
        "views", start, end, dimensions="insightTrafficSourceDetail",
        filters="insightTrafficSourceType==YT_SEARCH", sort="-views", maxResults=25,
    )


def audience(days):
    start, end = window(days)
    countries = report("views,estimatedMinutesWatched", start, end, dimensions="country", sort="-views", maxResults=10)
    demographics = report("viewerPercentage", start, end, dimensions="ageGroup,gender", sort="gender,ageGroup")
    return {"countries": countries, "demographics": demographics}
