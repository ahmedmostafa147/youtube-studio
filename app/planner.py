"""Video idea planner and saved tag lists."""

import json
import time

from . import db, util

STATUSES = ["idea", "writing", "filming", "editing", "published"]


def ideas():
    return db.query("SELECT * FROM ideas ORDER BY CASE status WHEN 'published' THEN 1 ELSE 0 END, updated DESC")


def add_idea(title, keyword="", notes="", source="manual", score=None):
    now = time.time()
    idea_id = db.execute(
        "INSERT INTO ideas (title, keyword, notes, status, score, source, created, updated) VALUES (?, ?, ?, 'idea', ?, ?, ?, ?)",
        (title.strip(), keyword.strip(), notes.strip(), score, source, now, now),
    )
    return db.query("SELECT * FROM ideas WHERE id = ?", (idea_id,))[0]


def update_idea(idea_id, **fields):
    allowed = {k: v for k, v in fields.items() if k in ("title", "keyword", "notes", "status", "score") and v is not None}
    if "status" in allowed and allowed["status"] not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    if allowed:
        sets = ", ".join(f"{k} = ?" for k in allowed)
        db.execute(f"UPDATE ideas SET {sets}, updated = ? WHERE id = ?", (*allowed.values(), time.time(), idea_id))
    rows = db.query("SELECT * FROM ideas WHERE id = ?", (idea_id,))
    return rows[0] if rows else None


def delete_idea(idea_id):
    db.execute("DELETE FROM ideas WHERE id = ?", (idea_id,))


def tag_lists():
    return [{"name": r["name"], "tags": json.loads(r["tags"]), "updated": r["updated"]}
            for r in db.query("SELECT * FROM tag_lists ORDER BY name")]


def save_tag_list(name, tags):
    tags = [t.strip() for t in tags if t.strip()]
    db.execute("INSERT OR REPLACE INTO tag_lists (name, tags, updated) VALUES (?, ?, ?)",
               (name.strip(), json.dumps(tags, ensure_ascii=False), time.time()))


def delete_tag_list(name):
    db.execute("DELETE FROM tag_lists WHERE name = ?", (name,))


def sort_tags(tags, keyword=""):
    """Exact keyword first, then tags sharing its words, then the rest; duplicates removed."""
    seen, unique = set(), []
    for t in (t.strip() for t in tags):
        n = util.normalize(t)
        if t and n not in seen:
            seen.add(n)
            unique.append(t)
    if not keyword:
        return unique
    target = util.normalize(keyword)
    words = set(target.split())

    def rank(tag):
        n = util.normalize(tag)
        if n == target:
            return (0, 0)
        shared = len(words & set(n.split()))
        return (1, -shared) if shared else (2, 0)

    return sorted(unique, key=rank)
