"""Hourly view counts for fresh videos, to show views per hour (VPH) like vidIQ's real-time stats."""

import time
from collections import defaultdict

from . import db, youtube

# Only videos younger than this get hourly snapshots; older ones barely move hour to hour.
FRESH_DAYS = 7
KEEP_DAYS = 14


def record(videos):
    """Store current views for the given summaries (from youtube.summary) that are still fresh."""
    now = time.time()
    rows = [(v["id"], now, v["views"]) for v in videos if v["age_days"] <= FRESH_DAYS]
    db.executemany("INSERT OR REPLACE INTO hourly (video_id, ts, views) VALUES (?, ?, ?)", rows)
    db.execute("DELETE FROM hourly WHERE ts < ?", (now - KEEP_DAYS * 86400,))
    return len(rows)


def vph(video_ids):
    """Views per hour between the two latest snapshots that are at least 30 minutes apart."""
    if not video_ids:
        return {}
    marks = ",".join("?" * len(video_ids))
    rows = db.query(f"SELECT video_id, ts, views FROM hourly WHERE video_id IN ({marks}) ORDER BY ts DESC", tuple(video_ids))
    by_video = defaultdict(list)
    for r in rows:
        by_video[r["video_id"]].append(r)
    out = {}
    for vid, snaps in by_video.items():
        latest = snaps[0]
        older = next((s for s in snaps[1:] if latest["ts"] - s["ts"] >= 1800), None)
        if older:
            hours = (latest["ts"] - older["ts"]) / 3600
            out[vid] = round((latest["views"] - older["views"]) / hours)
    return out


def last_48h(video_id):
    """Views gained in the last 48 hours, when there is a snapshot that old."""
    rows = db.query("SELECT ts, views FROM hourly WHERE video_id = ? ORDER BY ts", (video_id,))
    if len(rows) < 2:
        return None
    latest = rows[-1]
    base = next((r for r in reversed(rows) if latest["ts"] - r["ts"] >= 48 * 3600), None)
    return latest["views"] - base["views"] if base else None


def refresh_videos(ids):
    """Fetch current stats for the given video ids (1 quota unit per 50) and record them."""
    videos = [youtube.summary(v) for v in youtube.videos(ids, ttl=0)]
    record(videos)
    return videos
