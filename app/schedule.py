"""Scheduled changes: new title, description or thumbnail on a date, and "sunset" (unlist or make private on a date).

The hourly job runner executes what is due, so a change happens within an hour of its time, and only while the
dashboard is running (anything missed runs as soon as it starts again). Each change costs 50 quota units.
"""

import time
from datetime import datetime

from . import alerts, config, db, editor, oauth

KINDS = {"title": "عنوان جديد", "description": "وصف جديد", "thumbnail": "ثمبنيل جديد", "privacy": "تغيير الظهور"}


def parse_time(value):
    """A datetime-local value from the browser ("2026-11-01T18:00"), in your timezone, as epoch seconds."""
    try:
        dt = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError("الميعاد مش مفهوم.")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=config.tz())
    return dt.timestamp()


def add(url, kind, value, when, source="dashboard"):
    if kind not in KINDS:
        raise ValueError("نوع التغيير لازم يكون title أو description أو thumbnail أو privacy.")
    run_at = parse_time(when) if isinstance(when, str) else float(when)
    if run_at < time.time() - 60:
        raise ValueError("الميعاد ده فات. اختار وقت جاي.")
    oauth.write_token()  # scheduling a change that could never run would only fail silently later
    item = editor.fetch_one(editor.video_id(url))
    if kind == "title":
        found = editor.problems(title=value)
    elif kind == "description":
        found = editor.problems(description=value)
    elif kind == "privacy":
        found = [] if value in editor.PRIVACY else ["الظهور لازم يكون public أو unlisted أو private."]
    else:
        value = editor.save_image(value) if value.startswith("data:") else value
        editor.image_bytes(value)
        found = []
    if found:
        raise ValueError(" ".join(found))
    sid = db.execute(
        "INSERT INTO scheduled (video_id, video_title, kind, value, run_at, created) VALUES (?, ?, ?, ?, ?, ?)",
        (item["id"], item["snippet"]["title"], kind, value, run_at, time.time()),
    )
    return get(sid)


def get(sid):
    rows = db.query("SELECT * FROM scheduled WHERE id = ?", (sid,))
    if not rows:
        raise ValueError("التغيير ده مش موجود.")
    return _row(rows[0])


def _row(r):
    r["label"] = KINDS.get(r["kind"], r["kind"])
    r["run_at_local"] = datetime.fromtimestamp(r["run_at"], config.tz()).strftime("%Y-%m-%d %H:%M")
    return r


def items(include_done=True):
    sql = "SELECT * FROM scheduled" + ("" if include_done else " WHERE status = 'pending'")
    return [_row(r) for r in db.query(sql + " ORDER BY CASE status WHEN 'pending' THEN 0 ELSE 1 END, run_at", ())]


def cancel(sid):
    db.execute("UPDATE scheduled SET status = 'cancelled' WHERE id = ? AND status = 'pending'", (sid,))
    return get(sid)


def execute(r):
    vid, source = r["video_id"], f"schedule #{r['id']}"
    if r["kind"] == "title":
        return editor.update(vid, title=r["value"], source=source)
    if r["kind"] == "description":
        return editor.update(vid, description=r["value"], source=source)
    if r["kind"] == "privacy":
        return editor.set_privacy(vid, r["value"], source=source)
    data, mime = editor.image_bytes(r["value"])
    return editor.set_thumbnail(vid, data, mime, source=source)


def run_due():
    """Run every pending change whose time has come. Called by the hourly job."""
    due = db.query("SELECT * FROM scheduled WHERE status = 'pending' AND run_at <= ? ORDER BY run_at", (time.time(),))
    if not due:
        return 0
    if not oauth.can_edit():
        return "skipped: editing is off or not approved"
    for r in due:
        try:
            execute(r)
            status, result = "done", "اتنفذ"
        except Exception as e:  # keep going with the rest; the error is shown on the row and as an alert
            status, result = "failed", str(e)
        db.execute("UPDATE scheduled SET status = ?, result = ?, done = ? WHERE id = ?", (status, result, time.time(), r["id"]))
        title = f"{KINDS[r['kind']]}: {'اتنفذ' if status == 'done' else 'فشل'}"
        alerts.add(f"sched:{r['id']}", "scheduled", title, f"{r['video_title']} — {result}",
                   f"https://www.youtube.com/watch?v={r['video_id']}")
    return len(due)
