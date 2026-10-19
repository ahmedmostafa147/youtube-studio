"""SQLite storage: API response cache, quota counter, competitors and their videos."""

import json
import sqlite3
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, value TEXT NOT NULL, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS quota (day TEXT PRIMARY KEY, units INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS competitors (
    channel_id TEXT PRIMARY KEY, title TEXT, handle TEXT, thumbnail TEXT,
    subs INTEGER, video_count INTEGER, view_count INTEGER, uploads_playlist TEXT,
    added REAL, refreshed REAL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS videos (
    video_id TEXT PRIMARY KEY, channel_id TEXT, title TEXT, published_at TEXT,
    duration INTEGER, thumbnail TEXT, views INTEGER, likes INTEGER, comments INTEGER, updated REAL
);
CREATE INDEX IF NOT EXISTS videos_channel ON videos(channel_id);
CREATE TABLE IF NOT EXISTS snapshots (
    video_id TEXT, day TEXT, views INTEGER, PRIMARY KEY (video_id, day)
);
CREATE TABLE IF NOT EXISTS hourly (
    video_id TEXT, ts REAL, views INTEGER, PRIMARY KEY (video_id, ts)
);
CREATE TABLE IF NOT EXISTS channel_snapshots (
    channel_id TEXT, day TEXT, subs INTEGER, views INTEGER, videos INTEGER, PRIMARY KEY (channel_id, day)
);
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT UNIQUE, kind TEXT, title TEXT, body TEXT,
    url TEXT, thumbnail TEXT, created REAL, read INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS ideas (
    id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, keyword TEXT, notes TEXT,
    status TEXT DEFAULT 'idea', score INTEGER, source TEXT, created REAL, updated REAL
);
CREATE TABLE IF NOT EXISTS tag_lists (name TEXT PRIMARY KEY, tags TEXT NOT NULL, updated REAL);
"""

PACIFIC = ZoneInfo("America/Los_Angeles")

_lock = threading.Lock()
# The dashboard and the MCP server are separate processes sharing this file; wait instead of failing on a lock.
_conn = sqlite3.connect(config.DATA_DIR / "studio.db", check_same_thread=False, timeout=15)
_conn.row_factory = sqlite3.Row
_conn.executescript(SCHEMA)


def execute(sql, params=()):
    with _lock:
        cur = _conn.execute(sql, params)
        _conn.commit()
        return cur.lastrowid


def executemany(sql, rows):
    with _lock:
        _conn.executemany(sql, rows)
        _conn.commit()


def query(sql, params=()):
    with _lock:
        return [dict(r) for r in _conn.execute(sql, params).fetchall()]


# ---------- cache ----------

def cache_get(key, ttl):
    rows = query("SELECT value, created FROM cache WHERE key = ?", (key,))
    if rows and time.time() - rows[0]["created"] < ttl:
        return json.loads(rows[0]["value"])
    return None


def cache_set(key, value):
    execute(
        "INSERT OR REPLACE INTO cache (key, value, created) VALUES (?, ?, ?)",
        (key, json.dumps(value, ensure_ascii=False), time.time()),
    )


def cache_clear(prefix):
    execute("DELETE FROM cache WHERE key LIKE ?", (prefix + "%",))


# ---------- quota ----------

def quota_day():
    return datetime.now(PACIFIC).date().isoformat()


def add_quota(units):
    execute(
        "INSERT INTO quota (day, units) VALUES (?, ?) ON CONFLICT(day) DO UPDATE SET units = units + excluded.units",
        (quota_day(), units),
    )


def quota_used():
    rows = query("SELECT units FROM quota WHERE day = ?", (quota_day(),))
    return rows[0]["units"] if rows else 0
