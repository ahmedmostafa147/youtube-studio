"""Run the studio on fake YouTube / Analytics / Claude data. Import this before anything else from `app`.

Nothing here touches the network or your real data/ folder: settings and the database live in a temp directory.
"""

import os
import random
import re
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

STUDIO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(STUDIO))
MY_CHANNEL = "UC" + "m" * 22
os.environ.update({"YOUTUBE_API_KEY": "fake", "MY_CHANNEL_ID": MY_CHANNEL, "MY_CHANNEL_TITLE": "قناتي التجريبية",
                   "NICHE_KEYWORDS": "claude, ذكاء اصطناعي", "ANTHROPIC_API_KEY": "fake", "ALLOW_EDITING": "0",
                   "BRAND_ALERTS": "0", "RANK_MAX_KEYWORDS": "2", "TIMEZONE": "Africa/Cairo", "YT_LANG": "ar"})
from app import config  # noqa: E402

config.DATA_DIR = Path(tempfile.mkdtemp())
config.ENV_FILE = config.DATA_DIR / ".env"
import httpx  # noqa: E402

from app import ai, analytics, db, oauth, suggest, youtube  # noqa: E402

random.seed(1)
now = datetime.now(timezone.utc)
CHANNELS = [f"UC{'x' * 20}{n:02d}" for n in range(5)] + [MY_CHANNEL]


def vid(i, ch):
    pub = (now - timedelta(days=random.uniform(0.3, 300), hours=random.randint(0, 23))).isoformat().replace("+00:00", "Z")
    views = int(random.lognormvariate(9, 1.5))
    return {"id": f"vid{i:08d}",
            "snippet": {"title": f"شرح Claude الجزء {i}" if i % 2 else f"فيديو ذكاء اصطناعي {i}",
                        "description": "وصف قصير " * (i % 30) + ("\nكورس قديم: https://old.example/course" if (i // 6) % 2 == 0 else ""),
                        "tags": ["claude", "ai", "شرح claude"][: i % 4], "categoryId": "28", "channelId": ch,
                        "channelTitle": "قناتي التجريبية" if ch == MY_CHANNEL else "قناة " + ch[-2:], "publishedAt": pub,
                        "thumbnails": {"medium": {"url": f"https://picsum.photos/seed/{i}/320/180"},
                                       "high": {"url": f"https://picsum.photos/seed/{i}/480/360"}}},
            "statistics": {"viewCount": str(views), "likeCount": str(views // 30), "commentCount": str(views // 300)},
            "contentDetails": {"duration": random.choice(["PT45S", "PT12M3S", "PT25M"])},
            "status": {"privacyStatus": "public", "uploadStatus": "processed", "embeddable": True, "license": "youtube",
                       "publicStatsViewable": True, "madeForKids": False, "selfDeclaredMadeForKids": False}}


VIDS = {f"vid{i:08d}": vid(i, CHANNELS[i % 6]) for i in range(360)}
MINE = [k for k, v in VIDS.items() if v["snippet"]["channelId"] == MY_CHANNEL]
PLAYLIST = {"PLtest": [{"item_id": f"PLI{n}", "video_id": MINE[n]} for n in range(5)]}
WRITES = []


def chan(cid):
    return {"id": cid, "snippet": {"title": "قناتي التجريبية" if cid == MY_CHANNEL else "قناة " + cid[-2:], "customUrl": "@c" + cid[-2:],
                                   "publishedAt": "2022-01-01T00:00:00Z", "thumbnails": {"default": {"url": f"https://picsum.photos/seed/{cid}/88/88"}}},
            "statistics": {"subscriberCount": str(random.choice([800, 5000, 120000, 2000000])), "videoCount": "60", "viewCount": "1000000"},
            "contentDetails": {"relatedPlaylists": {"uploads": "UU" + cid[2:]}}}


def _comment(n, text, author_channel, video_id):
    return {"id": f"cm{n}", "snippet": {"textDisplay": text, "likeCount": 10 - n % 10, "authorDisplayName": f"@user{n}",
                                        "authorChannelId": {"value": author_channel}, "publishedAt": "2026-10-01T00:00:00Z", "videoId": video_id}}


def fake_call(endpoint, params, ttl=0, token=None):
    db.add_quota(youtube.COST.get(endpoint, 1))
    if endpoint == "search":
        if params.get("type") == "channel":
            return {"items": [{"snippet": {"channelId": CHANNELS[0]}}]}
        n = int(params.get("maxResults", 25))
        return {"items": [{"id": {"videoId": k}, "snippet": {kk: VIDS[k]["snippet"][kk] for kk in ("title", "channelId", "channelTitle", "thumbnails")}}
                          for k in list(VIDS)[:n]]}
    if endpoint == "videos":
        if params.get("chart"):
            return {"items": list(VIDS.values())[100:150]}
        return {"items": [VIDS[i] for i in params["id"].split(",") if i in VIDS]}
    if endpoint == "channels":
        if params.get("mine"):
            return {"items": [chan(MY_CHANNEL)]}
        handle = params.get("forHandle", "")
        ids = params.get("id") or (CHANNELS[int(handle[-1]) % 6] if handle else CHANNELS[1])
        return {"items": [chan(c) for c in ids.split(",")]}
    if endpoint == "playlists":
        return {"items": [{"id": "PLtest", "snippet": {"title": "شروحات Claude", "thumbnails": {}},
                           "contentDetails": {"itemCount": len(PLAYLIST["PLtest"])}, "status": {"privacyStatus": "public"}}]}
    if endpoint == "playlistItems":
        pid = params["playlistId"]
        if pid in PLAYLIST:
            return {"items": [{"id": it["item_id"], "snippet": {"title": VIDS[it["video_id"]]["snippet"]["title"], "position": pos,
                                                                "thumbnails": VIDS[it["video_id"]]["snippet"]["thumbnails"]},
                               "contentDetails": {"videoId": it["video_id"], "videoPublishedAt": VIDS[it["video_id"]]["snippet"]["publishedAt"]}}
                              for pos, it in enumerate(PLAYLIST[pid])]}
        cid = "UC" + pid[2:]
        return {"items": [{"contentDetails": {"videoId": k}} for k, v in VIDS.items() if v["snippet"]["channelId"] == cid][:50]}
    if endpoint == "videoCategories":
        return {"items": [{"id": "28", "snippet": {"title": "Science & Technology", "assignable": True}}, {"id": "27", "snippet": {"title": "Education", "assignable": True}}]}
    if endpoint == "commentThreads":
        texts = ["ياريت تعمل فيديو عن Claude Code", "شرح ممتاز جدا شكرا", "إزاي أستخدمه مجانًا؟", "please make a video about agents", "الصوت واطي شوية"]
        video = params.get("videoId") or MINE[0]
        items = []
        for n, t in enumerate(texts * 4):
            # Every 4th thread already has a reply from the channel, and one comment is the creator's own.
            replies = [_comment(1000 + n, "شكرا!", MY_CHANNEL, video)] if n % 4 == 0 else []
            author = MY_CHANNEL if n == 7 else f"UCviewer{n}"
            items.append({"id": f"th{n}", "snippet": {"videoId": video, "totalReplyCount": len(replies), "topLevelComment": _comment(n, t, author, video)},
                          "replies": {"comments": replies}})
        return {"items": items}
    raise AssertionError(endpoint)


READ_ONLY_SNIPPET = ("channelId", "channelTitle", "publishedAt", "thumbnails")


def fake_write(method, endpoint, params, body=None, token=None, content=None, content_type=None):
    assert token == "fake-token", "writes must use the write token"
    if db.quota_used() + youtube.WRITE_COST > config.DAILY_QUOTA:
        raise youtube.YouTubeError(youtube.error_message_quota(db.quota_used()))
    db.add_quota(youtube.WRITE_COST)
    WRITES.append({"method": method, "endpoint": endpoint, "params": params, "body": body, "bytes": len(content or b"")})
    if endpoint == "videos":
        v = VIDS[body["id"]]
        if "snippet" in body:
            # Like the real API: the snippet is replaced, so fields that are left out are erased.
            assert body["snippet"].get("title") and body["snippet"].get("categoryId"), "title and categoryId are required"
            v["snippet"] = {**{k: v["snippet"][k] for k in READ_ONLY_SNIPPET}, **body["snippet"]}
        if "status" in body:
            assert "uploadStatus" not in body["status"], "read-only status field sent"
            v["status"] = {**v["status"], **body["status"]}
        if "localizations" in body:
            assert v["snippet"].get("defaultLanguage"), "localizations need snippet.defaultLanguage"
            v["localizations"] = body["localizations"]
        return v
    if endpoint == "thumbnails/set":
        return {"items": [{"default": {"url": "new"}}]}
    if endpoint == "playlistItems":
        items = PLAYLIST[body["snippet"]["playlistId"]]
        if method == "POST":
            items.append({"item_id": f"PLI{len(items) + 100}", "video_id": body["snippet"]["resourceId"]["videoId"]})
        else:
            item = next(i for i in items if i["item_id"] == body["id"])
            items.remove(item)
            items.insert(body["snippet"]["position"], item)
        return {}
    if endpoint == "comments":
        return {"id": "reply-" + body["snippet"]["parentId"], "snippet": {"videoId": MINE[0], **body["snippet"]}}
    raise AssertionError(endpoint)


youtube.call = fake_call
youtube.write = fake_write
suggest.autocomplete = lambda q: [q, q + " code", q + " ai"]
oauth.has_client = lambda: True
oauth.access_token = lambda: "fake-token"
httpx.get = lambda url, **kw: SimpleNamespace(status_code=200, content=b"\xff\xd8 old thumbnail " + url.encode())


def link_channel(write_scope):
    """Pretend the channel was linked, with or without the write permission."""
    scopes = oauth.READ_SCOPES + ([oauth.WRITE_SCOPE] if write_scope else [])
    oauth.TOKEN_FILE.write_text('{"access_token": "fake-token", "refresh_token": "r", "expires_at": %d, "scope": "%s"}'
                                % (time.time() + 3600, " ".join(scopes)))


link_channel(write_scope=False)


def fake_report(metrics, start, end, **extra):
    dims = extra.get("dimensions")
    if dims == "day":
        return [{"day": (start + timedelta(days=i)).isoformat(), "views": 800 + random.randint(-300, 900), "estimatedMinutesWatched": 2000 + i * 10,
                 "averageViewDuration": 200 + i, "averageViewPercentage": 40.0, "likes": 30, "subscribersGained": 20, "subscribersLost": 3}
                for i in range((end - start).days + 1)]
    if dims == "video":
        return [{"video": k, "views": random.randint(100, 9000), "estimatedMinutesWatched": random.randint(500, 40000), "averageViewDuration": random.randint(60, 600), "averageViewPercentage": random.uniform(20, 60), "likes": 10, "subscribersGained": random.randint(0, 90)} for k in list(VIDS)[:8]]
    if dims == "insightTrafficSourceType":
        return [{"insightTrafficSourceType": t, "views": v, "estimatedMinutesWatched": v * 3} for t, v in [("YT_SEARCH", 9000), ("RELATED_VIDEO", 7000), ("SUBSCRIBER", 3000), ("EXT_URL", 600)]]
    if dims == "insightTrafficSourceDetail":
        return [{"insightTrafficSourceDetail": t, "views": v} for t, v in [("شرح claude", 1200), ("claude code", 800), ("ai agents", 300)]]
    if dims == "country":
        return [{"country": c, "views": v, "estimatedMinutesWatched": v * 3} for c, v in [("EG", 9000), ("SA", 4000), ("US", 900)]]
    if dims == "ageGroup,gender":
        return [{"ageGroup": "age18-24", "gender": "male", "viewerPercentage": 40.0}, {"ageGroup": "age25-34", "gender": "female", "viewerPercentage": 60.0}]
    if dims == "elapsedVideoTimeRatio":
        return [{"elapsedVideoTimeRatio": i / 100, "audienceWatchRatio": max(0.15, 1 - i / 100 * 0.8 - (0.15 if i > 30 else 0)), "relativeRetentionPerformance": 0.55} for i in range(1, 101)]
    row = {m: 0 for m in metrics.split(",")}
    row.update({"views": 24000, "estimatedMinutesWatched": 61000, "averageViewDuration": 245, "averageViewPercentage": 38.2, "subscribersGained": 420, "subscribersLost": 35})
    return [row]


analytics.report = fake_report


def fake_ask(content, schema, effort="medium"):
    props = schema["properties"]
    usage = {"input_tokens": 1200, "output_tokens": 600, "cost_usd": 0.0168}
    if "translations" in props:
        langs = schema["properties"]["translations"]["items"]["properties"]["language"]["enum"]
        return {"translations": [{"language": l, "title": f"[{l}] Claude Code tutorial", "description": f"[{l}] description <b>\n0:00 Intro"} for l in langs]}, usage
    if "replies" in props:
        ids = re.findall(r"^\[(\S+)\]", content, re.M)
        return {"replies": [{"comment_id": i, "reply": "شكرًا جدًا! فكرة حلوة لفيديو جاي."} for i in ids]}, usage
    if "titles" in props:
        return {"titles": [{"title": t, "angle": "شرح عملي", "why": "بيوعد بنتيجة واضحة"} for t in ["شرح Claude Code للمبتدئين خطوة بخطوة", "Claude Code: أداة بتكتب الكود لوحدها"]]}, usage
    if "description" in props:
        return {"description": "في الفيديو ده شرح Claude Code من الصفر.\n0:00 مقدمة", "hashtags": ["#claude"], "tags": ["شرح claude code", "claude code"]}, usage
    if "hook" in props:
        return {"hook": "الأداة دي كتبت تطبيق كامل في 10 دقايق.", "intro": "النهارده هنشوف إزاي.", "sections": [{"heading": "التسطيب", "talking_points": ["نزّل Node"], "seconds": 120}], "outro": "جرّبها."}, usage
    if "chapters" in props:
        return {"chapters": [{"start": "0:05", "title": "مقدمة"}, {"start": "1:10", "title": "التسطيب"}]}, usage
    if "ideas" in props:
        return {"ideas": [{"title": "Claude Code ضد Cursor", "keyword": "claude code vs cursor", "why": "مقارنة فرقعت", "based_on": "competitor_outliers"}]}, usage
    if "score" in props:
        return {"score": 72, "verdict": "واضحة", "readable_small": False, "words_on_image": 5, "focal_point": "لوجو", "strengths": ["تباين"], "issues": ["كلام كتير"], "suggestions": ["3 كلمات"]}, usage
    if "summary" in props:
        return {"summary": "الناس عاجبها الشرح.", "sentiment": {"positive": 70, "neutral": 20, "negative": 10}, "requests": ["فيديو عن Claude Code"], "questions": ["مجاني؟"], "video_ideas": ["Claude Code للمبتدئين"]}, usage
    raise AssertionError(props)


ai._ask = fake_ask
