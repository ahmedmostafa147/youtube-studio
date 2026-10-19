"""Answering comments: comments you haven't replied to, canned replies, AI reply drafts, and posting a reply.

Nothing is posted automatically: a reply goes out only when you press send (50 quota units each).
"""

import time

from . import config, db, editor, oauth, util, youtube
from .youtube import YouTubeError


def threads(video="", unanswered=True, limit=50):
    """Latest comment threads on one video (link) or across your whole channel, 1 quota unit."""
    mine = config.get("MY_CHANNEL_ID")
    if not mine:
        raise YouTubeError("حط لينك قناتك في الإعدادات الأول.")
    params = {"part": "snippet,replies", "maxResults": min(limit, 100), "order": "time", "textFormat": "plainText"}
    if video.strip():
        vid = util.video_id(video)
        if not vid:
            raise YouTubeError("ده مش لينك فيديو يوتيوب.")
        params["videoId"] = vid
    else:
        params["allThreadsRelatedToChannelId"] = mine
    res = youtube.call("commentThreads", params, token=oauth.access_token())
    rows = []
    for it in res.get("items", []):
        top = it["snippet"]["topLevelComment"]
        s = top["snippet"]
        author = (s.get("authorChannelId") or {}).get("value")
        if author == mine:
            continue  # your own comments
        replies = (it.get("replies") or {}).get("comments", [])
        answered = any((r["snippet"].get("authorChannelId") or {}).get("value") == mine for r in replies)
        if unanswered and answered:
            continue
        rows.append({"comment_id": top["id"], "video_id": it["snippet"].get("videoId") or s.get("videoId"),
                     "text": s.get("textDisplay", ""), "author": s.get("authorDisplayName", ""),
                     "likes": s.get("likeCount", 0), "published": s.get("publishedAt"),
                     "replies": it["snippet"].get("totalReplyCount", 0), "answered": answered})
    return rows


# ---------- canned replies ----------

def canned():
    return db.query("SELECT * FROM canned_replies ORDER BY name")


def save_canned(name, text, reply_id=None):
    name, text = (name or "").strip(), (text or "").strip()
    if not name or not text:
        raise ValueError("اكتب اسم للرد ونصه.")
    if reply_id:
        db.execute("UPDATE canned_replies SET name = ?, text = ?, updated = ? WHERE id = ?", (name, text, time.time(), reply_id))
    else:
        db.execute("INSERT INTO canned_replies (name, text, updated) VALUES (?, ?, ?)", (name, text, time.time()))
    return canned()


def delete_canned(reply_id):
    db.execute("DELETE FROM canned_replies WHERE id = ?", (reply_id,))
    return canned()


def fill(text, author=""):
    """Canned replies may use {name} for the commenter's name."""
    return text.replace("{name}", author.lstrip("@")).strip()


# ---------- posting ----------

def post(comment_id, text, source="dashboard"):
    text = (text or "").strip()
    if not text:
        raise ValueError("الرد فاضي.")
    if len(text) > 10000:
        raise ValueError("الرد أطول من المسموح.")
    res = youtube.write("POST", "comments", {"part": "snippet"},
                        {"snippet": {"parentId": comment_id, "textOriginal": text}}, token=oauth.write_token())
    editor.log(res.get("snippet", {}).get("videoId", ""), "", "reply", {"comment_id": comment_id}, text, source)
    return {"id": res.get("id"), "posted": True}
