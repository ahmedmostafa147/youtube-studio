"""Bulk find/replace/append in titles or descriptions, and upload profiles (saved title/description/tags templates).

Both work in two steps: a free preview (dry run), then applying to the videos the user ticked, 50 quota units each.
"""

import json
import re
import time
from datetime import datetime

from . import config, db, editor, util

FIELDS = {"description": "الوصف", "title": "العنوان"}
MODES = ("replace", "append", "prepend")


def _change(text, mode, find, replace, case):
    """Returns (new text, number of changes)."""
    if mode == "replace":
        if not find:
            raise ValueError("اكتب الكلام اللي عاوز تدوّر عليه.")
        pattern = re.compile(re.escape(find), 0 if case else re.I)
        return pattern.subn(lambda m: replace, text)
    addition = replace.strip()
    if not addition:
        raise ValueError("اكتب الكلام اللي عاوز تضيفه.")
    if addition in text:  # already added (e.g. the bulk edit ran before)
        return text, 0
    sep = "\n\n" if "\n" in addition or len(text) > 100 else " "
    if mode == "append":
        return (text.rstrip() + sep + addition) if text.strip() else addition, 1
    return (addition + sep + text.lstrip()) if text.strip() else addition, 1


def _check(field, mode):
    if field not in FIELDS:
        raise ValueError("اختار العنوان أو الوصف.")
    if mode not in MODES:
        raise ValueError("النوع لازم يكون replace أو append أو prepend.")


def preview(field="description", mode="replace", find="", replace="", case=False, videos=None):
    """Dry run over your uploads (or the given video links). Changes nothing; about 2 units per 50 videos."""
    _check(field, mode)
    ids = [editor.video_id(v) for v in videos] if videos else None
    items = editor.fetch(ids) if ids else editor.my_videos()
    rows = []
    for item in items:
        old = item["snippet"].get(field, "")
        new, n = _change(old, mode, find, replace, case)
        if not n:
            continue
        b = editor.brief(item)
        rows.append({
            "id": b["id"], "title": b["title"], "thumbnail": b["thumbnail"], "privacy": b["privacy"],
            "published": b["published"], "count": n, "excerpts": editor.excerpts(old, new),
            "problems": editor.problems(**{field: new}),
        })
    status = editor.status()
    return {"field": field, "mode": mode, "checked": len(items), "matches": rows,
            "cost": len(rows) * status["cost_per_write"], "quota_left": status["quota_left"], "can_edit": status["can_edit"]}


def apply(video_ids, field="description", mode="replace", find="", replace="", case=False, source="dashboard"):
    """Apply the same change to the chosen videos. Each one is re-read first, so the change is recomputed on its
    latest text; videos that no longer match are skipped."""
    _check(field, mode)
    ids = list(dict.fromkeys(editor.video_id(v) for v in video_ids))
    if not ids:
        raise ValueError("اختار فيديو واحد على الأقل.")
    editor.check_quota(len(ids))
    results = []
    for item in editor.fetch(ids):
        new, n = _change(item["snippet"].get(field, ""), mode, find, replace, case)
        row = {"id": item["id"], "title": item["snippet"]["title"]}
        if not n:
            results.append({**row, "status": "skipped", "message": "مفيش تغيير (يمكن اتعدّل قبل كده)."})
            continue
        try:
            editor.write_snippet(item, **{field: new}, source=source)
            results.append({**row, "status": "done"})
        except (ValueError, editor.YouTubeError) as e:
            results.append({**row, "status": "failed", "message": str(e)})
    return {"results": results, "done": sum(r["status"] == "done" for r in results)}


# ---------- upload profiles ----------

PLACEHOLDERS = {"{title}": "العنوان الحالي", "{description}": "الوصف الحالي", "{date}": "تاريخ النهارده"}


def profiles():
    rows = db.query("SELECT * FROM profiles ORDER BY name")
    for r in rows:
        r["tags"] = json.loads(r["tags"] or "[]")
    return rows


def save_profile(name, title="", description="", tags=(), tags_mode="append", category_id=""):
    name = (name or "").strip()
    if not name:
        raise ValueError("اكتب اسم للقالب.")
    if tags_mode not in ("append", "replace"):
        raise ValueError("التاجز إما append أو replace.")
    tags = [t.strip() for t in tags if t.strip()]
    db.execute(
        "INSERT OR REPLACE INTO profiles (name, title, description, tags, tags_mode, category_id, updated) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (name, title or "", description or "", json.dumps(tags, ensure_ascii=False), tags_mode, category_id or "", time.time()),
    )
    return profiles()


def delete_profile(name):
    db.execute("DELETE FROM profiles WHERE name = ?", (name,))
    return profiles()


def _profile(name):
    found = [p for p in profiles() if p["name"] == name]
    if not found:
        raise ValueError("القالب ده مش موجود.")
    return found[0]


def _render(template, snippet):
    today = datetime.now(config.tz()).strftime("%Y-%m-%d")
    return (template.replace("{title}", snippet.get("title", ""))
            .replace("{description}", snippet.get("description", "")).replace("{date}", today)).strip()


def _profile_changes(profile, item):
    s = item["snippet"]
    changes = {}
    if profile["title"].strip():
        changes["title"] = _render(profile["title"], s)
    if profile["description"].strip():
        changes["description"] = _render(profile["description"], s)
    if profile["tags"]:
        base = s.get("tags", []) if profile["tags_mode"] == "append" else []
        seen, tags = set(), []
        for t in base + profile["tags"]:
            if util.normalize(t) not in seen:
                seen.add(util.normalize(t))
                tags.append(t)
        changes["tags"] = tags
    if profile["category_id"]:
        changes["category_id"] = profile["category_id"]
    return changes


def profile_preview(name, url):
    """What the video would look like with the profile applied. Changes nothing; 1 quota unit."""
    profile = _profile(name)
    item = editor.fetch_one(editor.video_id(url))
    changes = _profile_changes(profile, item)
    b = editor.brief(item)
    after = {"title": changes.get("title", b["title"]), "description": changes.get("description", b["description"]),
             "tags": changes.get("tags", b["tags"]), "category_id": changes.get("category_id", b["category_id"])}
    return {"video": b, "after": after, "problems": editor.problems(after["title"], after["description"], after["tags"]),
            "changed": any(after[k] != b[k] for k in after), "can_edit": editor.status()["can_edit"]}


def profile_apply(name, url, source="dashboard"):
    profile = _profile(name)
    editor.oauth.write_token()
    item = editor.fetch_one(editor.video_id(url))
    return editor.write_snippet(item, source=source, **_profile_changes(profile, item))
