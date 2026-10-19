"""Changes on your own channel: titles, descriptions, tags, thumbnails, visibility and translations.

Needs editing turned on in Settings and the channel linked again to approve the write permission.
Every change re-reads the video right before writing (so a stale preview never overwrites newer edits),
keeps the old values in edit_log so it can be undone, and costs 50 quota units.
"""

import base64
import difflib
import json
import re
import time
import uuid

import httpx

from . import config, db, oauth, seo, util, youtube
from .youtube import YouTubeError

TITLE_MAX = 100
DESCRIPTION_MAX = 5000
TAGS_MAX = 500
THUMB_MAX = 2_000_000
# Only these fields are sent back on videos.update; anything left out of the snippet would be erased.
SNIPPET_FIELDS = ("title", "description", "tags", "categoryId", "defaultLanguage", "defaultAudioLanguage")
STATUS_FIELDS = ("privacyStatus", "embeddable", "license", "publicStatsViewable", "publishAt",
                 "selfDeclaredMadeForKids", "containsSyntheticMedia")
PRIVACY = {"public": "عام", "unlisted": "غير مدرج", "private": "خاص"}
THUMB_DIR = config.DATA_DIR / "thumbs"
DATA_URL = re.compile(r"^data:(image/(?:png|jpeg));base64,(.+)$", re.S)
ACTIONS = {"snippet": "العنوان/الوصف/التاجز", "privacy": "الظهور", "thumbnail": "الثمبنيل",
           "localizations": "الترجمات", "reply": "رد على كومنت", "playlist": "قايمة تشغيل"}


def status():
    return {
        "enabled": oauth.editing_enabled(),
        "connected": oauth.connected(),
        "granted": oauth.WRITE_SCOPE in oauth.granted_scopes(),
        "can_edit": oauth.can_edit(),
        "cost_per_write": youtube.WRITE_COST,
        "quota_left": max(config.DAILY_QUOTA - db.quota_used(), 0),
    }


def video_id(text):
    vid = util.video_id(text)
    if not vid:
        raise YouTubeError("ده مش لينك فيديو يوتيوب.")
    return vid


def check_quota(writes):
    """Refuse a batch up front when today's quota can't cover it, instead of failing halfway."""
    need = writes * youtube.WRITE_COST
    left = config.DAILY_QUOTA - db.quota_used()
    if need > left:
        raise YouTubeError(f"التعديل ده محتاج {need:,} وحدة والباقي النهارده {max(left, 0):,}. قلّل عدد الفيديوهات أو كمّل بكرة.")


# ---------- reading your videos (read-only sign-in is enough) ----------

def fetch(ids, parts="snippet,status,localizations"):
    """Fresh copies of your videos, private and unlisted included (1 quota unit per 50)."""
    token = oauth.access_token()
    out = []
    for chunk in youtube._chunks(ids, 50):
        res = youtube.call("videos", {"part": parts, "id": ",".join(chunk), "maxResults": 50}, token=token)
        out.extend(res.get("items", []))
    return out


def fetch_one(vid):
    items = fetch([vid])
    if not items:
        raise YouTubeError("الفيديو ده مش موجود.")
    item = items[0]
    mine = config.get("MY_CHANNEL_ID")
    if mine and item["snippet"].get("channelId") != mine:
        raise YouTubeError("الفيديو ده مش على قناتك، فمينفعش تعدّله.")
    return item


def my_videos(limit=500):
    """Every upload on the linked channel, including private and unlisted ones (about 2 units per 50 videos)."""
    token = oauth.access_token()
    res = youtube.call("channels", {"part": "contentDetails", "mine": "true"}, token=token)
    items = res.get("items") or []
    if not items:
        raise YouTubeError("الحساب ده مفيهوش قناة يوتيوب.")
    playlist = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
    ids, page = [], None
    while len(ids) < limit:
        params = {"part": "contentDetails", "playlistId": playlist, "maxResults": 50}
        if page:
            params["pageToken"] = page
        res = youtube.call("playlistItems", params, token=token)
        ids += [i["contentDetails"]["videoId"] for i in res.get("items", [])]
        page = res.get("nextPageToken")
        if not page:
            break
    return fetch(ids[:limit])


def brief(item):
    s = item["snippet"]
    return {
        "id": item["id"],
        "title": s.get("title", ""),
        "description": s.get("description", ""),
        "tags": s.get("tags", []),
        "category_id": s.get("categoryId"),
        "default_language": s.get("defaultLanguage"),
        "published": s.get("publishedAt"),
        "thumbnail": youtube.best_thumb(s),
        "privacy": item.get("status", {}).get("privacyStatus"),
        "localizations": item.get("localizations", {}),
    }


def video(url):
    return brief(fetch_one(video_id(url)))


# ---------- checks ----------

def problems(title=None, description=None, tags=None):
    out = []
    if title is not None:
        if not title.strip():
            out.append("العنوان فاضي.")
        if len(title) > TITLE_MAX:
            out.append(f"العنوان {len(title)} حرف (الحد {TITLE_MAX}).")
        if "<" in title or ">" in title:
            out.append("العنوان فيه < أو > ويوتيوب بيرفضهم.")
    if description is not None:
        if len(description) > DESCRIPTION_MAX:
            out.append(f"الوصف {len(description)} حرف (الحد {DESCRIPTION_MAX}).")
        if "<" in description or ">" in description:
            out.append("الوصف فيه < أو > ويوتيوب بيرفضهم.")
    if tags is not None and seo.tags_length(tags) > TAGS_MAX:
        out.append(f"التاجز {seo.tags_length(tags)} حرف (الحد {TAGS_MAX}).")
    return out


def excerpts(old, new, context=60, limit=3):
    """Short before/after snippets around each change, for previews."""
    out = []
    matcher = difflib.SequenceMatcher(None, old, new, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        a, b = max(i1 - context, 0), min(i2 + context, len(old))
        c, d = max(j1 - context, 0), min(j2 + context, len(new))
        out.append({"before": ("…" if a else "") + old[a:b] + ("…" if b < len(old) else ""),
                    "after": ("…" if c else "") + new[c:d] + ("…" if d < len(new) else "")})
        if len(out) >= limit:
            break
    return out


# ---------- the log (and undo) ----------

def log(vid, title, action, before, after, source="dashboard"):
    db.execute(
        "INSERT INTO edit_log (video_id, video_title, action, before, after, source, created) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (vid, title, action, json.dumps(before, ensure_ascii=False), json.dumps(after, ensure_ascii=False), source, time.time()),
    )


def history(limit=50):
    rows = db.query("SELECT * FROM edit_log ORDER BY created DESC LIMIT ?", (limit,))
    for r in rows:
        r["before"] = json.loads(r["before"])
        r["after"] = json.loads(r["after"])
        r["label"] = ACTIONS.get(r["action"], r["action"])
        r["can_undo"] = r["action"] in ("snippet", "privacy", "localizations") or (
            r["action"] == "thumbnail" and bool(r["before"]) and (THUMB_DIR / r["before"]).exists())
    return rows


def undo(log_id):
    rows = db.query("SELECT * FROM edit_log WHERE id = ?", (log_id,))
    if not rows:
        raise ValueError("التعديل ده مش موجود في السجل.")
    r = rows[0]
    before, source = json.loads(r["before"]), f"undo #{log_id}"
    if r["action"] == "snippet":
        return update(r["video_id"], title=before.get("title"), description=before.get("description"),
                      tags=before.get("tags") or [], source=source)
    if r["action"] == "privacy":
        return set_privacy(r["video_id"], before, source=source)
    if r["action"] == "localizations":
        return save_localizations(r["video_id"], before, replace=True, source=source)
    if r["action"] == "thumbnail" and before:
        path = THUMB_DIR / before
        if path.exists():
            return set_thumbnail(r["video_id"], path.read_bytes(), _mime(path), source=source)
    raise ValueError("التعديل ده مينفعش يترجع.")


# ---------- writes (need the write permission) ----------

def _snippet(item, **changes):
    s = {k: item["snippet"][k] for k in SNIPPET_FIELDS if k in item["snippet"]}
    s.update({k: v for k, v in changes.items() if v is not None})
    return s


def write_snippet(item, title=None, description=None, tags=None, category_id=None, source="dashboard"):
    """videos.update with the full writable snippet (the API erases fields that are left out)."""
    found = problems(title, description, tags)
    if found:
        raise ValueError(" ".join(found))
    snippet = _snippet(item, title=title, description=description, tags=tags, categoryId=category_id)
    if not snippet.get("tags"):
        snippet.pop("tags", None)
    keys = ("title", "description", "tags", "categoryId")
    before = {k: item["snippet"].get(k) for k in keys}
    after = {k: snippet.get(k) for k in keys}
    if before == after:
        return {"id": item["id"], "title": snippet["title"], "changed": False}
    youtube.write("PUT", "videos", {"part": "snippet"}, {"id": item["id"], "snippet": snippet}, token=oauth.write_token())
    log(item["id"], snippet["title"], "snippet", before, after, source)
    return {"id": item["id"], "title": snippet["title"], "changed": True}


def update(url, title=None, description=None, tags=None, category_id=None, source="dashboard"):
    oauth.write_token()  # fail before spending a unit on the read
    return write_snippet(fetch_one(video_id(url)), title, description, tags, category_id, source)


def set_privacy(url, privacy, source="dashboard"):
    if privacy not in PRIVACY:
        raise ValueError("الظهور لازم يكون public أو unlisted أو private.")
    oauth.write_token()
    item = fetch_one(video_id(url))
    st = {k: item["status"][k] for k in STATUS_FIELDS if k in item["status"]}
    before = st.get("privacyStatus")
    st["privacyStatus"] = privacy
    if privacy != "private":
        st.pop("publishAt", None)  # a scheduled publish time is only allowed on private videos
    youtube.write("PUT", "videos", {"part": "status"}, {"id": item["id"], "status": st}, token=oauth.write_token())
    log(item["id"], item["snippet"]["title"], "privacy", before, privacy, source)
    return {"id": item["id"], "title": item["snippet"]["title"], "privacy": privacy, "before": before}


def _mime(path):
    return "image/png" if path.suffix == ".png" else "image/jpeg"


def save_image(data_url):
    """Store an uploaded thumbnail (data URL from the browser) in data/thumbs; returns the file name."""
    m = DATA_URL.match(data_url or "")
    if not m:
        raise ValueError("الثمبنيل لازم يكون صورة PNG أو JPG.")
    data = base64.b64decode(m.group(2))
    if len(data) > THUMB_MAX:
        raise ValueError("يوتيوب مش بيقبل ثمبنيل أكبر من 2MB.")
    THUMB_DIR.mkdir(exist_ok=True)
    name = f"{uuid.uuid4().hex[:12]}.{'png' if m.group(1) == 'image/png' else 'jpg'}"
    (THUMB_DIR / name).write_bytes(data)
    return name


def image_bytes(name):
    path = THUMB_DIR / name
    if not re.fullmatch(r"[\w.-]+", name or "") or not path.exists():
        raise ValueError("صورة الثمبنيل مش موجودة.")
    return path.read_bytes(), _mime(path)


def _backup_thumbnail(item):
    """Download the current thumbnail so the change can be undone. Best effort."""
    thumbs = item["snippet"].get("thumbnails", {})
    for size in ("maxres", "standard", "high", "medium"):
        if size in thumbs:
            try:
                r = httpx.get(thumbs[size]["url"], timeout=15)
                if r.status_code == 200 and r.content:
                    THUMB_DIR.mkdir(exist_ok=True)
                    name = f"old_{item['id']}_{int(time.time())}.jpg"
                    (THUMB_DIR / name).write_bytes(r.content)
                    return name
            except httpx.HTTPError:
                pass
            break
    return ""


def set_thumbnail(url, data, mime="image/jpeg", source="dashboard"):
    if len(data) > THUMB_MAX:
        raise ValueError("يوتيوب مش بيقبل ثمبنيل أكبر من 2MB.")
    oauth.write_token()
    item = fetch_one(video_id(url))
    old = _backup_thumbnail(item)
    youtube.write("POST", "thumbnails/set", {"videoId": item["id"], "uploadType": "media"},
                  token=oauth.write_token(), content=data, content_type=mime)
    log(item["id"], item["snippet"]["title"], "thumbnail", old, "new", source)
    return {"id": item["id"], "title": item["snippet"]["title"], "changed": True}


def save_localizations(url, translations, replace=False, source="dashboard"):
    """Set translated titles/descriptions: {lang: {title, description}}. Keeps other languages unless replace=True."""
    oauth.write_token()
    item = fetch_one(video_id(url))
    snippet = _snippet(item)
    default = snippet.get("defaultLanguage") or config.lang()
    before = item.get("localizations") or {}
    loc = {} if replace else dict(before)
    for lang, t in translations.items():
        lang = lang.strip()
        if not lang or lang == default:
            continue
        title, desc = (t.get("title") or "").strip(), (t.get("description") or "").strip()
        found = problems(title, desc)
        if found:
            raise ValueError(f"[{lang}] " + " ".join(found))
        loc[lang] = {"title": title, "description": desc}
    parts, body = "localizations", {"id": item["id"], "localizations": loc}
    if not snippet.get("defaultLanguage"):
        # Translations need the video's own language set first.
        snippet["defaultLanguage"] = default
        parts, body["snippet"] = "snippet,localizations", snippet
    youtube.write("PUT", "videos", {"part": parts}, body, token=oauth.write_token())
    log(item["id"], snippet["title"], "localizations", before, loc, source)
    return {"id": item["id"], "title": snippet["title"], "default_language": default, "languages": sorted(loc)}
