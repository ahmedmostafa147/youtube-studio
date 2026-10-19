"""Title/thumbnail A/B rotation: switch between 2-3 versions every N days and compare their analytics.

YouTube Studio has its own "Test & Compare" (thumbnails and titles) that splits viewers at the same time and is
more accurate; use it when your channel has it. This rotation is the fallback: versions run one after another, so a
video's natural decay favours the first one. Running each version at least twice in turn evens that out.
Switches happen just after midnight Pacific time (about 10:00 in Cairo), because YouTube Analytics days are
Pacific days: that way each version owns whole days of data. Each switch costs 50 quota units per changed field.
"""

import json
import time
from collections import defaultdict
from datetime import date, datetime, timedelta

from . import alerts, analytics, db, editor, oauth
from .youtube import YouTubeError

DAY = 86400
SLACK = 1800  # the hourly job may run a bit early; still switch if within half an hour of the deadline


def next_switch(last_switch, days):
    """Pacific midnight `days` days after the Pacific date of the last switch."""
    d = datetime.fromtimestamp(last_switch, db.PACIFIC).date() + timedelta(days=days)
    return datetime(d.year, d.month, d.day, tzinfo=db.PACIFIC).timestamp()


def _load(r):
    r["variants"] = json.loads(r["variants"])
    r["periods"] = db.query("SELECT variant, start, end FROM ab_periods WHERE test_id = ? ORDER BY start", (r["id"],))
    r["next_switch"] = next_switch(r["last_switch"], r["days"]) if r["status"] == "running" else None
    return r


def tests():
    return [_load(r) for r in db.query("SELECT * FROM ab_tests ORDER BY CASE status WHEN 'running' THEN 0 ELSE 1 END, started DESC")]


def get(test_id):
    rows = db.query("SELECT * FROM ab_tests WHERE id = ?", (test_id,))
    if not rows:
        raise ValueError("الاختبار ده مش موجود.")
    return _load(rows[0])


def start(url, variants, days=1, rounds=2, source="dashboard"):
    """variants: 1-2 new versions, each {"title": str|None, "thumbnail": data URL|file name|None}.
    The video's current title and thumbnail become version A automatically."""
    if not 1 <= days <= 7:
        raise ValueError("مدة كل نسخة من يوم لـ 7 أيام.")
    if not 1 <= rounds <= 4:
        raise ValueError("عدد الجولات من 1 لـ 4.")
    variants = [v for v in variants if (v.get("title") or "").strip() or v.get("thumbnail")]
    if not 1 <= len(variants) <= 2:
        raise ValueError("ضيف نسخة أو اتنين غير النسخة الحالية (عنوان و/أو ثمبنيل).")
    oauth.write_token()
    item = editor.fetch_one(editor.video_id(url))
    if db.query("SELECT 1 FROM ab_tests WHERE video_id = ? AND status = 'running'", (item["id"],)):
        raise ValueError("فيه اختبار شغال على الفيديو ده بالفعل.")
    uses_thumb = any(v.get("thumbnail") for v in variants)
    original = {"title": item["snippet"]["title"],
                "thumbnail": editor._backup_thumbnail(item) if uses_thumb else None}
    if uses_thumb and not original["thumbnail"]:
        raise YouTubeError("مقدرتش أحفظ نسخة من الثمبنيل الحالي، فمش هقدر أرجّعه. جرّب تاني.")
    clean = [original]
    for v in variants:
        title = (v.get("title") or "").strip() or None
        if title and editor.problems(title=title):
            raise ValueError(" ".join(editor.problems(title=title)))
        thumb = v.get("thumbnail")
        if thumb:
            thumb = editor.save_image(thumb) if thumb.startswith("data:") else thumb
            editor.image_bytes(thumb)
        clean.append({"title": title or original["title"], "thumbnail": thumb or original["thumbnail"]})
    now = time.time()
    test_id = db.execute(
        "INSERT INTO ab_tests (video_id, video_title, variants, days, current, status, started, last_switch, rounds) "
        "VALUES (?, ?, ?, ?, 0, 'running', ?, ?, ?)",
        (item["id"], original["title"], json.dumps(clean, ensure_ascii=False), days, now, now, rounds),
    )
    db.execute("INSERT INTO ab_periods (test_id, variant, start, end) VALUES (?, 0, ?, NULL)", (test_id, now))
    # Version A is live already; the first switch happens after `days`.
    return get(test_id)


def _apply(test, index, source):
    v, cur = test["variants"][index], test["variants"][test["current"]]
    if v["title"] != cur["title"]:
        editor.update(test["video_id"], title=v["title"], source=source)
    if v["thumbnail"] and v["thumbnail"] != cur["thumbnail"]:
        data, mime = editor.image_bytes(v["thumbnail"])
        editor.set_thumbnail(test["video_id"], data, mime, source=source)


def _switch(test, index, source):
    _apply(test, index, source)
    now = time.time()
    db.execute("UPDATE ab_periods SET end = ? WHERE test_id = ? AND end IS NULL", (now, test["id"]))
    db.execute("INSERT INTO ab_periods (test_id, variant, start, end) VALUES (?, ?, ?, NULL)", (test["id"], index, now))
    db.execute("UPDATE ab_tests SET current = ?, last_switch = ? WHERE id = ?", (index, now, test["id"]))


def tick():
    """Rotate running tests whose period is over. Called by the hourly job."""
    if not oauth.can_edit():
        return "skipped: editing is off or not approved"
    switched = 0
    for test in tests():
        if test["status"] != "running" or time.time() < test["next_switch"] - SLACK:
            continue
        total = len(test["variants"]) * (test["rounds"] or 2)
        try:
            if len(test["periods"]) >= total:
                finish(test["id"], keep=0, source=f"ab #{test['id']}")
                alerts.add(f"ab:{test['id']}:done", "ab", "اختبار A/B خلص ورجعت النسخة الأصلية", test["video_title"] + " — شوف النتيجة واختار الأحسن.",
                           f"https://www.youtube.com/watch?v={test['video_id']}")
            else:
                _switch(test, (test["current"] + 1) % len(test["variants"]), f"ab #{test['id']}")
            switched += 1
        except Exception as e:  # one failing test (quota, revoked access) must not block the others
            alerts.add(f"ab:{test['id']}:err:{int(time.time() // DAY)}", "ab", "اختبار A/B مقدرش يبدّل النسخة",
                       f"{test['video_title']} — {e}", f"https://www.youtube.com/watch?v={test['video_id']}")
    return switched


def finish(test_id, keep=None, source="dashboard"):
    """Stop the test. keep = index of the version to leave on the video (None leaves the current one)."""
    test = get(test_id)
    if test["status"] == "running":
        if keep is not None and keep != test["current"]:
            if not 0 <= keep < len(test["variants"]):
                raise ValueError("النسخة دي مش موجودة.")
            _apply(test, keep, source)
        db.execute("UPDATE ab_periods SET end = ? WHERE test_id = ? AND end IS NULL", (time.time(), test_id))
        db.execute("UPDATE ab_tests SET status = 'done', winner = ? WHERE id = ?",
                   (test["current"] if keep is None else keep, test_id))
    elif keep is not None and keep != test["winner"]:
        # After the test ended: put the chosen version on the video.
        test["current"] = test["winner"] or 0
        _apply(test, keep, source)
        db.execute("UPDATE ab_tests SET winner = ? WHERE id = ?", (keep, test_id))
    return get(test_id)


def results(test_id):
    """Daily analytics per version. A day counts for a version only when it was live for 20+ hours of it."""
    test = get(test_id)
    start = datetime.fromtimestamp(test["started"], db.PACIFIC).date()
    end = date.today() - timedelta(days=analytics.LAG_DAYS)
    out = {"test": test, "versions": [], "days_counted": 0, "lag_days": analytics.LAG_DAYS}
    if start > end:
        out["note"] = f"أرقام YouTube Analytics بتتأخر حوالي {analytics.LAG_DAYS} يوم. ارجع بعد كده."
    rows = [] if start > end else analytics.report(
        "views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,likes,subscribersGained",
        start, end, dimensions="day", filters=f"video=={test['video_id']}", sort="day")
    by_version = defaultdict(list)
    for r in rows:
        d = date.fromisoformat(r["day"])
        day_start = datetime(d.year, d.month, d.day, tzinfo=db.PACIFIC).timestamp()
        day_end = day_start + DAY
        for p in test["periods"]:
            overlap = min(p["end"] or time.time(), day_end) - max(p["start"], day_start)
            if overlap >= 20 * 3600:
                by_version[p["variant"]].append(r)
                break
    for i, v in enumerate(test["variants"]):
        days = by_version.get(i, [])
        n = len(days)
        views = sum(r["views"] for r in days)
        out["versions"].append({
            "index": i, "title": v["title"], "thumbnail": v["thumbnail"], "days": n,
            "views_per_day": round(views / n) if n else None,
            "minutes_per_day": round(sum(r["estimatedMinutesWatched"] for r in days) / n) if n else None,
            "avg_view_duration": round(sum(r["averageViewDuration"] * r["views"] for r in days) / views) if views else None,
            "avg_view_pct": round(sum(r["averageViewPercentage"] * r["views"] for r in days) / views, 1) if views else None,
            "subs_per_day": round(sum(r["subscribersGained"] for r in days) / n, 1) if n else None,
        })
        out["days_counted"] += n
    scored = [v for v in out["versions"] if v["minutes_per_day"] is not None]
    if len(scored) == len(out["versions"]) and len(scored) > 1:
        out["leader"] = max(scored, key=lambda v: v["minutes_per_day"])["index"]
    return out
