"""Your playlists: list them, add videos, and reorder. Reading is 1 unit per 50; every add or move is 50 units."""

import time

from . import editor, oauth, youtube
from .youtube import YouTubeError

SORTS = {"newest": "الأحدث الأول", "oldest": "الأقدم الأول", "views": "الأكتر مشاهدة", "title": "حسب الاسم"}


def mine():
    token = oauth.access_token()
    rows, page = [], None
    for _ in range(10):
        params = {"part": "snippet,contentDetails,status", "mine": "true", "maxResults": 50}
        if page:
            params["pageToken"] = page
        res = youtube.call("playlists", params, token=token)
        for p in res.get("items", []):
            rows.append({"id": p["id"], "title": p["snippet"].get("title", ""), "count": p["contentDetails"].get("itemCount", 0),
                         "thumbnail": youtube.best_thumb(p["snippet"]), "privacy": p.get("status", {}).get("privacyStatus")})
        page = res.get("nextPageToken")
        if not page:
            break
    return rows


def items(playlist_id):
    """Videos in a playlist in their current order, with views (for sorting)."""
    token = oauth.access_token()
    rows, page = [], None
    for _ in range(20):
        params = {"part": "snippet,contentDetails", "playlistId": playlist_id, "maxResults": 50}
        if page:
            params["pageToken"] = page
        res = youtube.call("playlistItems", params, token=token)
        for it in res.get("items", []):
            rows.append({"item_id": it["id"], "video_id": it["contentDetails"]["videoId"], "title": it["snippet"].get("title", ""),
                         "position": it["snippet"].get("position", len(rows)), "thumbnail": youtube.best_thumb(it["snippet"]),
                         "published": it["contentDetails"].get("videoPublishedAt") or ""})
        page = res.get("nextPageToken")
        if not page:
            break
    stats = {v["id"]: v.get("statistics", {}) for v in youtube.videos([r["video_id"] for r in rows], ttl=0, token=token)}
    for r in rows:
        r["views"] = int(stats.get(r["video_id"], {}).get("viewCount", 0))
    rows.sort(key=lambda r: r["position"])
    return rows


def add(playlist_id, videos, source="dashboard"):
    """Add videos (links or ids) to the end of a playlist, skipping ones already in it."""
    ids = list(dict.fromkeys(editor.video_id(v) for v in videos if v.strip()))
    if not ids:
        raise ValueError("حط لينك فيديو واحد على الأقل.")
    oauth.write_token()
    existing = {r["video_id"] for r in items(playlist_id)}
    new = [v for v in ids if v not in existing]
    editor.check_quota(len(new))
    results = [{"id": v, "status": "skipped", "message": "موجود في القايمة بالفعل."} for v in ids if v in existing]
    for vid in new:
        try:
            youtube.write("POST", "playlistItems", {"part": "snippet"},
                          {"snippet": {"playlistId": playlist_id, "resourceId": {"kind": "youtube#video", "videoId": vid}}},
                          token=oauth.write_token())
            editor.log(vid, "", "playlist", None, {"playlist": playlist_id, "added": True}, source)
            results.append({"id": vid, "status": "done"})
        except YouTubeError as e:
            results.append({"id": vid, "status": "failed", "message": str(e)})
    return {"results": results, "done": sum(r["status"] == "done" for r in results)}


def _target(rows, sort, order):
    if order:
        known = {r["item_id"] for r in rows}
        if set(order) != known or len(order) != len(rows):
            raise ValueError("الترتيب الجديد لازم يكون فيه كل فيديوهات القايمة مرة واحدة.")
        return list(order)
    if sort not in SORTS:
        raise ValueError("اختار طريقة الترتيب.")
    key = {"newest": lambda r: r["published"], "oldest": lambda r: r["published"], "views": lambda r: r["views"],
           "title": lambda r: r["title"]}[sort]
    return [r["item_id"] for r in sorted(rows, key=key, reverse=sort in ("newest", "views"))]


def _moves(current, target):
    """Moves (item_id, new position) that turn `current` into `target`, one item at a time."""
    current, moves = list(current), []
    for i, item in enumerate(target):
        if current[i] != item:
            current.remove(item)
            current.insert(i, item)
            moves.append((item, i))
    return moves


def reorder_preview(playlist_id, sort="", order=None):
    rows = items(playlist_id)
    target = _target(rows, sort, order)
    moves = _moves([r["item_id"] for r in rows], target)
    by_id = {r["item_id"]: r for r in rows}
    return {"before": rows, "after": [by_id[i] for i in target], "moves": len(moves),
            "cost": len(moves) * youtube.WRITE_COST, "can_edit": oauth.can_edit()}


def reorder(playlist_id, sort="", order=None, source="dashboard"):
    """Apply a new order (needs the playlist sorted "manually" in YouTube Studio)."""
    oauth.write_token()
    rows = items(playlist_id)
    target = _target(rows, sort, order)
    moves = _moves([r["item_id"] for r in rows], target)
    editor.check_quota(len(moves))
    by_id = {r["item_id"]: r for r in rows}
    for item_id, position in moves:
        youtube.write("PUT", "playlistItems", {"part": "snippet"}, {"id": item_id, "snippet": {
            "playlistId": playlist_id, "position": position,
            "resourceId": {"kind": "youtube#video", "videoId": by_id[item_id]["video_id"]}}}, token=oauth.write_token())
    if moves:
        editor.log("", "", "playlist", None, {"playlist": playlist_id, "moves": len(moves), "at": time.time()}, source)
    return {"moves": len(moves)}
