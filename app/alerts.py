"""Notifications shown in the dashboard: new competitor uploads, videos taking off, niche trends."""

import time

from . import db


def add(key, kind, title, body="", url="", thumbnail=""):
    """Store an alert once; the same key never alerts twice."""
    db.execute(
        "INSERT OR IGNORE INTO alerts (key, kind, title, body, url, thumbnail, created) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (key, kind, title, body, url, thumbnail, time.time()),
    )


def recent(limit=50, unread_only=False):
    sql = "SELECT * FROM alerts"
    if unread_only:
        sql += " WHERE read = 0"
    return db.query(sql + " ORDER BY created DESC LIMIT ?", (limit,))


def unread_count():
    return db.query("SELECT COUNT(*) AS n FROM alerts WHERE read = 0")[0]["n"]


def mark_read(alert_id=None):
    if alert_id is None:
        db.execute("UPDATE alerts SET read = 1")
    else:
        db.execute("UPDATE alerts SET read = 1 WHERE id = ?", (alert_id,))
