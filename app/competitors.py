"""Competitor channels: their latest uploads, daily view snapshots, and outliers.

An outlier is a video with many more views than its channel's usual video (median of the
channel's stored videos of the same format), which is what vidIQ calls an outlier score.
"""

import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from . import alerts, config, db, hourly, util, youtube

STALE_AFTER = 12 * 3600
WEEKDAYS = ["الاتنين", "التلات", "الأربع", "الخميس", "الجمعة", "السبت", "الحد"]


def add(text):
    channel = youtube.find_channel(text)
    c = youtube.channel_summary(channel)
    db.execute(
        """INSERT OR REPLACE INTO competitors
           (channel_id, title, handle, thumbnail, subs, video_count, view_count, uploads_playlist, added, refreshed)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
        (c["id"], c["title"], c["handle"], c["thumbnail"], c["subs"], c["video_count"], c["view_count"],
         channel["contentDetails"]["relatedPlaylists"]["uploads"], time.time()),
    )
    refresh(c["id"], channel)
    return c


def remove(channel_id):
    db.execute("DELETE FROM competitors WHERE channel_id = ?", (channel_id,))
    ids = [r["video_id"] for r in db.query("SELECT video_id FROM videos WHERE channel_id = ?", (channel_id,))]
    db.executemany("DELETE FROM snapshots WHERE video_id = ?", [(i,) for i in ids])
    db.execute("DELETE FROM videos WHERE channel_id = ?", (channel_id,))


def snapshot_channel(c):
    """Record today's subscribers/views for a channel summary, to measure growth over time."""
    day = datetime.now(config.tz()).date().isoformat()
    db.execute(
        "INSERT OR REPLACE INTO channel_snapshots (channel_id, day, subs, views, videos) VALUES (?, ?, ?, ?, ?)",
        (c["id"], day, c["subs"], c["view_count"], c["video_count"]),
    )


def refresh(channel_id, channel=None):
    """Re-read channel stats and latest 50 uploads (about 3 quota units)."""
    if channel is None:
        items = youtube.channels([channel_id], ttl=0)
        if not items:
            return
        channel = items[0]
    c = youtube.channel_summary(channel)
    previous = db.query("SELECT refreshed FROM competitors WHERE channel_id = ?", (channel_id,))
    known = {r["video_id"] for r in db.query("SELECT video_id FROM videos WHERE channel_id = ?", (channel_id,))}
    db.execute(
        "UPDATE competitors SET title=?, handle=?, thumbnail=?, subs=?, video_count=?, view_count=?, refreshed=? WHERE channel_id=?",
        (c["title"], c["handle"], c["thumbnail"], c["subs"], c["video_count"], c["view_count"], time.time(), channel_id),
    )
    snapshot_channel(c)
    videos = [youtube.summary(v) for v in youtube.uploads(channel, ttl=0)]
    hourly.record(videos)
    # Alert only after the first refresh, so adding a channel doesn't flood the list with its back catalogue.
    if previous and previous[0]["refreshed"]:
        for v in videos:
            if v["id"] not in known and v["age_days"] <= 3:
                alerts.add(f"upload:{v['id']}", "upload", f"{c['title']} نزّل فيديو جديد", v["title"],
                           f"https://www.youtube.com/watch?v={v['id']}", v["thumbnail"])
    now = time.time()
    day = datetime.now(config.tz()).date().isoformat()
    db.executemany(
        """INSERT OR REPLACE INTO videos
           (video_id, channel_id, title, published_at, duration, thumbnail, views, likes, comments, updated)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [(v["id"], channel_id, v["title"], v["published"], v["duration"], v["thumbnail"],
          v["views"], v["likes"], v["comments"], now) for v in videos],
    )
    db.executemany(
        "INSERT OR REPLACE INTO snapshots (video_id, day, views) VALUES (?, ?, ?)",
        [(v["id"], day, v["views"]) for v in videos],
    )


def refresh_all(only_stale=False):
    cutoff = time.time() - STALE_AFTER if only_stale else float("inf")
    rows = db.query("SELECT channel_id FROM competitors WHERE refreshed < ?", (cutoff,))
    for row in rows:
        refresh(row["channel_id"])
    return len(rows)


def _videos(channel_id=None):
    sql = "SELECT * FROM videos"
    params = ()
    if channel_id:
        sql += " WHERE channel_id = ?"
        params = (channel_id,)
    rows = db.query(sql, params)
    for r in rows:
        r["is_short"] = 0 < (r["duration"] or 0) <= 180
        r["age_days"] = round(util.age_days(r["published_at"]), 1)
        r["vpd"] = round(r["views"] / r["age_days"], 1)
    return rows


def _with_outlier_scores(rows):
    """Add each video's views divided by its channel's median views for the same format."""
    groups = defaultdict(list)
    for r in rows:
        groups[(r["channel_id"], r["is_short"])].append(r["views"])
    medians = {k: util.median(v) for k, v in groups.items()}
    for r in rows:
        med = medians[(r["channel_id"], r["is_short"])]
        r["channel_median"] = round(med)
        r["outlier"] = round(r["views"] / med, 2) if med else None
    return rows


def _growth(video_ids):
    """Views gained per day between the two latest snapshots of each video."""
    if not video_ids:
        return {}
    marks = ",".join("?" * len(video_ids))
    rows = db.query(f"SELECT video_id, day, views FROM snapshots WHERE video_id IN ({marks}) ORDER BY day DESC", tuple(video_ids))
    by_video = defaultdict(list)
    for r in rows:
        by_video[r["video_id"]].append(r)
    growth = {}
    for vid, snaps in by_video.items():
        if len(snaps) >= 2:
            new, old = snaps[0], snaps[1]
            days = (datetime.fromisoformat(new["day"]) - datetime.fromisoformat(old["day"])).days or 1
            growth[vid] = round((new["views"] - old["views"]) / days)
    return growth


def list_all():
    competitors = db.query("SELECT * FROM competitors ORDER BY subs DESC")
    rows = _videos()
    month_ago = datetime.now(timezone.utc) - timedelta(days=30)
    for c in competitors:
        mine = [r for r in rows if r["channel_id"] == c["channel_id"]]
        c["median_views"] = round(util.median([r["views"] for r in mine if not r["is_short"]]))
        c["median_views_shorts"] = round(util.median([r["views"] for r in mine if r["is_short"]]))
        c["uploads_30d"] = sum(util.parse_time(r["published_at"]) >= month_ago for r in mine)
    return competitors


def outliers(days=90, fmt="all", channel_id=None, limit=60):
    rows = _with_outlier_scores(_videos())
    rows = [r for r in rows if r["age_days"] <= days and r["outlier"] is not None]
    if fmt == "long":
        rows = [r for r in rows if not r["is_short"]]
    elif fmt == "short":
        rows = [r for r in rows if r["is_short"]]
    if channel_id:
        rows = [r for r in rows if r["channel_id"] == channel_id]
    rows.sort(key=lambda r: r["outlier"], reverse=True)
    rows = rows[:limit]

    names = {c["channel_id"]: c for c in db.query("SELECT channel_id, title, thumbnail, subs FROM competitors")}
    ids = [r["video_id"] for r in rows]
    growth = _growth(ids)
    per_hour = hourly.vph(ids)
    for r in rows:
        c = names.get(r["channel_id"], {})
        r["channel_title"] = c.get("title", "")
        r["subs"] = c.get("subs", 0)
        r["growth_per_day"] = growth.get(r["video_id"])
        r["vph"] = per_hour.get(r["video_id"])
    return rows


def check_takeoffs():
    """Alert when a competitor's video from the last 3 days is already at 2x its channel's usual views."""
    rows = _with_outlier_scores(_videos())
    names = {c["channel_id"]: c["title"] for c in db.query("SELECT channel_id, title FROM competitors")}
    for r in rows:
        if r["age_days"] <= 3 and (r["outlier"] or 0) >= 2:
            alerts.add(f"takeoff:{r['video_id']}", "takeoff", f"فيديو بيفرقع عند {names.get(r['channel_id'], '')}",
                       f"{r['title']} (×{r['outlier']:.1f} من المعتاد في {r['age_days']:.0f} يوم)",
                       f"https://www.youtube.com/watch?v={r['video_id']}", r["thumbnail"])


def growth(channel_id, days=30):
    """Subscriber and view growth from stored daily snapshots (None until there are two days of data)."""
    rows = db.query("SELECT day, subs, views FROM channel_snapshots WHERE channel_id = ? ORDER BY day", (channel_id,))
    if len(rows) < 2:
        return None
    latest = rows[-1]
    cutoff = (datetime.fromisoformat(latest["day"]) - timedelta(days=days)).date().isoformat()
    base = next((r for r in rows if r["day"] >= cutoff), rows[0])
    span = (datetime.fromisoformat(latest["day"]) - datetime.fromisoformat(base["day"])).days
    if span < 1:
        return None
    return {
        "days": span,
        "subs": latest["subs"] - base["subs"],
        "views": latest["views"] - base["views"],
        "subs_per_day": (latest["subs"] - base["subs"]) / span,
        "views_per_day": (latest["views"] - base["views"]) / span,
    }


def timing():
    """Median outlier score of competitors' long videos by weekday and 3-hour block (local time)."""
    rows = [r for r in _with_outlier_scores(_videos()) if not r["is_short"] and r["age_days"] >= 3 and r["outlier"]]
    tz = config.tz()
    by_day, by_hour = defaultdict(list), defaultdict(list)
    for r in rows:
        local = util.parse_time(r["published_at"]).astimezone(tz)
        by_day[local.weekday()].append(r["outlier"])
        by_hour[local.hour // 3].append(r["outlier"])

    def summarize(groups, labels):
        return [{"label": labels[k], "count": len(groups[k]), "score": round(util.median(groups[k]), 2) if groups[k] else None}
                for k in range(len(labels))]

    hours = [f"{h * 3}:00–{h * 3 + 3}:00" for h in range(8)]
    return {"sample": len(rows), "weekdays": summarize(by_day, WEEKDAYS), "hours": summarize(by_hour, hours)}
