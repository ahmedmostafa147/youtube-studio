"""Channel audit, retention, scorecard, earnings, milestones, ad-safety check, comments, backup and idea signals."""

import csv
import json
import re
from collections import Counter
from datetime import date, datetime, timedelta, timezone

from . import analytics, competitors, config, db, mychannel, oauth, planner, seo, trends, util, youtube
from .youtube import YouTubeError

HOUR = 3600


def _status(value, good, ok, higher_is_better=True):
    if not higher_is_better:
        value, good, ok = -value, -good, -ok
    return "pass" if value >= good else "warn" if value >= ok else "fail"


def _share(items, pred):
    return round(sum(1 for i in items if pred(i)) / len(items) * 100) if items else 0


def _engagement(v):
    return ((v.get("likes") or 0) + (v.get("comments") or 0)) / v["views"] * 100 if v["views"] else 0


# ---------- channel audit ----------

def audit(channel_text=""):
    """Health check of a channel's last 50 uploads (yours by default). About 3 quota units."""
    item = youtube.find_channel(channel_text) if channel_text else mychannel.channel()
    c = youtube.channel_summary(item)
    videos = [youtube.summary(v) for v in youtube.uploads(item)]
    if not videos:
        return {"channel": c, "score": 0, "checks": [], "empty": True}

    videos.sort(key=lambda v: v["published"], reverse=True)
    last90 = [v for v in videos if v["age_days"] <= 90]
    per_week = round(len(last90) / (90 / 7), 1)
    gaps = [round(videos[i + 1]["age_days"] - videos[i]["age_days"]) for i in range(len(videos) - 1) if videos[i + 1]["age_days"] <= 120]
    settled = [v for v in videos if v["age_days"] >= 7]  # newer videos are still collecting views
    recent10 = util.median([v["views"] for v in settled[:10]])
    prev10 = util.median([v["views"] for v in settled[10:20]])
    trend = round((recent10 - prev10) / prev10 * 100) if prev10 else None

    long_videos = [v for v in videos if not v["is_short"]]
    reports = {v["id"]: seo.score(v["title"], v["description"], v["tags"], "") for v in videos}

    def check_ok(v, label_start):
        return next((c["status"] == "pass" for c in reports[v["id"]]["checks"] if c["label"].startswith(label_start)), False)

    long4 = [v for v in long_videos if v["duration"] >= 240]
    chapters_pct = _share(long4, lambda v: check_ok(v, "الفصول"))
    desc_pct = _share(videos, lambda v: len(v["description"]) >= 250)
    tags_pct = _share(videos, lambda v: bool(v["tags"]))
    titles_pct = _share(videos, lambda v: len(v["title"]) <= 70)
    engagement = round(util.median([_engagement(v) for v in settled or videos]), 2)

    checks = [
        ("معدل النشر", f"{per_week} فيديو في الأسبوع (آخر 90 يوم)", _status(per_week, 1, 0.5),
         "النشر المنتظم (فيديو أسبوعيًا على الأقل) بيخلّي يوتيوب يرشّحك أكتر.", 15),
        ("آخر فيديو", f"من {videos[0]['age_days']:.0f} يوم", _status(videos[0]["age_days"], 14, 30, higher_is_better=False),
         "غياب أكتر من أسبوعين بيقلل الظهور للمشتركين.", 10),
        ("أطول فترة من غير نشر", f"{max(gaps) if gaps else 0} يوم (آخر 4 شهور)", _status(max(gaps) if gaps else 0, 21, 45, higher_is_better=False),
         "حاول متسيبش فجوات طويلة بين الفيديوهات.", 5),
        ("اتجاه المشاهدات", "مفيش داتا كفاية" if trend is None else f"{trend:+d}% (آخر 10 فيديوهات قصاد الـ 10 اللي قبلهم)",
         "warn" if trend is None else _status(trend, -10, -35), "لو المشاهدات بتقل، شوف المنافسين بيعملوا إيه في «الفيديوهات اللي فرقعت».", 20),
        ("Chapters في الفيديوهات الطويلة", f"{chapters_pct}% من الفيديوهات اللي أطول من 4 دقايق", _status(chapters_pct, 70, 30),
         "الـ Chapters بتظهر في البحث وبتزود وقت المشاهدة.", 10),
        ("وصف كفاية", f"{desc_pct}% من الفيديوهات وصفها 250 حرف أو أكتر", _status(desc_pct, 80, 50),
         "الوصف بيفهّم يوتيوب الفيديو بيتكلم عن إيه.", 10),
        ("تاجز", f"{tags_pct}% من الفيديوهات فيها تاجز", _status(tags_pct, 80, 40),
         "التاجز تأثيرها صغير بس مفيدة للأسماء الإنجليزي والأخطاء الإملائية.", 5),
        ("طول العناوين", f"{titles_pct}% من العناوين 70 حرف أو أقل", _status(titles_pct, 90, 60),
         "العناوين الطويلة بتتقص في البحث.", 10),
        ("التفاعل", f"{engagement}% (لايكات وكومنتات من المشاهدات)", _status(engagement, 4, 2),
         "اطلب رأي المشاهد في سؤال محدد جوه الفيديو.", 15),
    ]
    rows = [{"label": l, "value": val, "status": s, "tip": "" if s == "pass" else tip, "points": p} for l, val, s, tip, p in checks]
    possible = sum(r["points"] for r in rows)
    earned = sum(r["points"] * (1 if r["status"] == "pass" else 0.5 if r["status"] == "warn" else 0) for r in rows)

    med = {fmt: util.median([v["views"] for v in videos if v["is_short"] == fmt]) for fmt in (False, True)}
    for v in videos:
        m = med[v["is_short"]]
        v["outlier"] = round(v["views"] / m, 2) if m else None
        v.pop("description", None)
        v.pop("tags", None)
    ranked = sorted((v for v in settled if v["outlier"]), key=lambda v: v["outlier"], reverse=True)
    return {
        "channel": c,
        "score": round(earned / possible * 100),
        "checks": rows,
        "stats": {"videos_checked": len(videos), "per_week": per_week, "long_median": round(med[False]),
                  "shorts_median": round(med[True]), "shorts_share": _share(videos, lambda v: v["is_short"]), "engagement": engagement},
        "best": ranked[:3],
        "worst": ranked[-3:][::-1] if len(ranked) > 3 else [],
    }


# ---------- retention (needs OAuth) ----------

def retention(url):
    vid = util.video_id(url)
    if not vid:
        raise YouTubeError("ده مش لينك فيديو يوتيوب.")
    token = oauth.access_token()
    items = youtube.videos([vid], ttl=HOUR, token=token)
    if not items:
        raise YouTubeError("الفيديو ده مش موجود.")
    v = youtube.summary(items[0])
    start = util.parse_time(v["published"]).date()
    end = date.today() - timedelta(days=analytics.LAG_DAYS)
    if start > end:
        raise YouTubeError("الفيديو لسه جديد، وداتا الاحتفاظ بتتأخر حوالي يومين.")
    rows = analytics.report("audienceWatchRatio,relativeRetentionPerformance", start, end,
                            dimensions="elapsedVideoTimeRatio", filters=f"video=={vid}", sort="elapsedVideoTimeRatio")
    if not rows:
        raise YouTubeError("يوتيوب لسه مطلعش داتا احتفاظ للفيديو ده (محتاج مشاهدات أكتر). ده بيشتغل على فيديوهات قناتك بس.")
    points = [{"t": round(r["elapsedVideoTimeRatio"] * v["duration"]), "pct": round(r["audienceWatchRatio"] * 100, 1),
               "relative": round(r["relativeRetentionPerformance"], 2)} for r in rows]

    def at(seconds):
        return next((p["pct"] for p in points if p["t"] >= seconds), points[-1]["pct"])

    drops = sorted(
        ({"from": points[i - 1]["t"], "to": points[i]["t"], "drop": round(points[i - 1]["pct"] - points[i]["pct"], 1)}
         for i in range(2, len(points))),
        key=lambda d: d["drop"], reverse=True,
    )
    return {
        "video": {"id": vid, "title": v["title"], "duration": v["duration"], "views": v["views"]},
        "points": points,
        "at_30s": at(30),
        "at_half": at(v["duration"] / 2),
        "average": round(sum(p["pct"] for p in points) / len(points), 1),
        "relative_avg": round(sum(p["relative"] for p in points) / len(points), 2),
        "biggest_drops": [d for d in drops[:3] if d["drop"] > 0],
    }


# ---------- scorecard / leaderboard ----------

def _channel_stats(videos, subs):
    long_recent = sorted((v for v in videos if not v["is_short"]), key=lambda v: v["age_days"])[:20]
    settled = [v for v in videos if v["age_days"] >= 3] or videos
    median_views = util.median([v["views"] for v in long_recent])
    med_all = {fmt: util.median([v["views"] for v in videos if v["is_short"] == fmt]) for fmt in (False, True)}
    return {
        "median_views": round(median_views),
        "uploads_30d": sum(v["age_days"] <= 30 for v in videos),
        "engagement": round(util.median([_engagement(v) for v in settled]), 2),
        "views_per_sub": round(median_views / subs, 3) if subs else None,
        "outliers_90d": sum(1 for v in videos if v["age_days"] <= 90 and med_all[v["is_short"]] and v["views"] >= 2 * med_all[v["is_short"]]),
    }


def scorecard():
    """Your channel next to every competitor, with growth once a few days of history exist."""
    rows = []
    for c in db.query("SELECT * FROM competitors"):
        videos = competitors._videos(c["channel_id"])
        rows.append({"channel_id": c["channel_id"], "title": c["title"], "thumbnail": c["thumbnail"], "subs": c["subs"],
                     "is_me": False, **_channel_stats(videos, c["subs"])})
    if config.get("MY_CHANNEL_ID"):
        item = mychannel.channel()
        me = youtube.channel_summary(item)
        competitors.snapshot_channel(me)
        videos = [youtube.summary(v) for v in youtube.uploads(item)]
        rows.append({"channel_id": me["id"], "title": me["title"], "thumbnail": me["thumbnail"], "subs": me["subs"],
                     "is_me": True, **_channel_stats(videos, me["subs"])})
    for r in rows:
        g = competitors.growth(r["channel_id"], 30)
        r["subs_growth"] = g["subs"] if g else None
        r["growth_days"] = g["days"] if g else None
    rows.sort(key=lambda r: r["subs"], reverse=True)
    for metric in ("subs", "median_views", "uploads_30d", "engagement", "views_per_sub", "outliers_90d", "subs_growth"):
        ordered = sorted((r for r in rows if r[metric] is not None), key=lambda r: r[metric], reverse=True)
        for rank, r in enumerate(ordered, 1):
            r.setdefault("ranks", {})[metric] = rank
    return {"rows": rows, "has_me": any(r["is_me"] for r in rows)}


# ---------- earnings ----------

def earnings(rpm=None, channel_text=""):
    """Estimated monthly earnings from views and an RPM you set (YouTube Studio shows your real RPM)."""
    rpm = rpm or config.rpm()
    monthly_views, source = None, ""
    if not channel_text and oauth.connected():
        start, end = analytics.window(28)
        rows = analytics.report("views", start, end)
        if rows:
            monthly_views, source = rows[0]["views"] / 28 * 30, "مشاهدات قناتك الحقيقية آخر 28 يوم من YouTube Analytics"
    item = youtube.find_channel(channel_text) if channel_text else mychannel.channel()
    c = youtube.channel_summary(item)
    if monthly_views is None:
        g = competitors.growth(c["id"], 30)
        if g and g["days"] >= 7:
            monthly_views, source = g["views_per_day"] * 30, f"الزيادة في إجمالي المشاهدات آخر {g['days']} يوم"
        else:
            age = util.age_days(item["snippet"]["publishedAt"])
            monthly_views = c["view_count"] / age * 30
            source = "متوسط عمر القناة كله (تقريبي جدًا لحد ما يتجمع أسبوع من الداتا)"
    monthly = monthly_views / 1000 * rpm
    return {
        "channel": c, "rpm": rpm, "source": source,
        "monthly_views": round(monthly_views),
        "monthly": {"low": round(monthly * 0.6), "mid": round(monthly), "high": round(monthly * 1.5)},
        "yearly": round(monthly * 12),
        "valuation": {"low": round(monthly * 24), "high": round(monthly * 36)},
        "note": "تقدير بس. الأرباح الحقيقية بتعتمد على نسبة المشاهدات المدفوعة، والدول، والموسم، والشورتس بتجيب أقل بكتير.",
    }


# ---------- milestones ----------

LADDER = [100, 500, 1_000, 5_000, 10_000, 25_000, 50_000, 100_000, 250_000, 500_000, 1_000_000, 5_000_000, 10_000_000,
          50_000_000, 100_000_000, 500_000_000, 1_000_000_000]


def milestones():
    item = mychannel.channel(ttl=0)
    c = youtube.channel_summary(item)
    competitors.snapshot_channel(c)
    g = competitors.growth(c["id"], 30)
    subs_rate = g["subs_per_day"] if g else None
    views_rate = g["views_per_day"] if g else None
    source = f"من زيادة آخر {g['days']} يوم" if g else ""
    watch_hours = None
    if oauth.connected():
        start, end = analytics.window(28)
        rows = analytics.report("subscribersGained,subscribersLost,views", start, end)
        if rows:
            subs_rate = (rows[0]["subscribersGained"] - rows[0]["subscribersLost"]) / 28
            views_rate = rows[0]["views"] / 28
            source = "من YouTube Analytics آخر 28 يوم"
        start, end = analytics.window(365)
        rows = analytics.report("estimatedMinutesWatched", start, end)
        watch_hours = round(rows[0]["estimatedMinutesWatched"] / 60) if rows else 0

    def goal(current, rate):
        nxt = next((m for m in LADDER if m > current), None)
        if nxt is None:
            return None
        days = (nxt - current) / rate if rate and rate > 0 else None
        eta = (date.today() + timedelta(days=days)).isoformat() if days is not None and days < 3650 else None
        return {"current": current, "next": nxt, "remaining": nxt - current, "days": round(days) if days else None,
                "eta": eta, "progress": round(current / nxt * 100, 1)}

    return {
        "channel": c, "source": source,
        "subs": goal(c["subs"], subs_rate),
        "views": goal(c["view_count"], views_rate),
        "achieved": [m for m in LADDER if m <= c["subs"]],
        "partner_program": {
            "subs": c["subs"], "subs_needed": 1000, "watch_hours": watch_hours, "watch_hours_needed": 4000,
            "note": "شرط برنامج الشركاء: 1,000 مشترك + 4,000 ساعة مشاهدة في آخر 12 شهر (أو 10M مشاهدة شورتس في 90 يوم).",
        },
    }


# ---------- ad-safety ----------

_WORDS = json.loads((config.ROOT / "app" / "data" / "ad_unfriendly.json").read_text(encoding="utf-8"))["categories"]
_PREFIXES = ["وال", "بال", "فال", "كال", "لل", "ال", "و", "ف", "ب", "ل"]
TOKEN = re.compile(r"[\w؀-ۿ]+")


def _forms(token):
    yield token
    for p in _PREFIXES:
        if token.startswith(p) and len(token) - len(p) >= 2:
            yield token[len(p):]


def ad_safety(title="", description="", tags=(), transcript=""):
    """Words that often get a video limited ads, by where they appear. A match means: check the context."""
    lookup = {util.normalize(w): cat for cat, words in _WORDS.items() for w in words}
    fields = {"العنوان": title, "الوصف": description, "التاجز": " ".join(tags), "الكلام": transcript}
    hits = []
    for field, text in fields.items():
        found = {}
        for token in TOKEN.findall(util.normalize(text)):
            for form in _forms(token):
                if form in lookup:
                    found[form] = lookup[form]
                    break
        hits += [{"field": field, "word": w, "category": cat} for w, cat in found.items()]
    in_title = any(h["field"] == "العنوان" for h in hits)
    risk = "high" if in_title else "medium" if any(h["field"] in ("الوصف", "التاجز") for h in hits) else "low" if hits else "none"
    return {"risk": risk, "hits": hits,
            "note": "يوتيوب بيراجع السياق مش الكلمة لوحدها. كلمة زي «اختراق» في شرح أمان عادي، بس الأفضل متبقاش في العنوان."}


# ---------- comments ----------

STOPWORDS = set(util.normalize(w) for w in """
في من على عن الى إلى الي مع ده دي دا اللي الي انا انت انتو هو هي احنا هم كان كانت يكون مش مش بس كده كدا جدا جداً اوي
والله ياريت لو ما لا لم لن قد كل ايه إيه ليه ازاي إزاي يا ياا او أو و ثم بعد قبل عند عشان علشان لان لأن هذا هذه ذلك التي الذي
the a an and or to of in on for is are was were be it this that you your i my me we our with but not have has can just so
thanks thank video
""".split())
REQUEST = re.compile(r"(ياريت|يا ريت|ممكن (تعمل|تشرح|فيديو)|اعمل|عايزين|عاوزين|عايز|عاوز|نفسي|please make|can you make|make a video|do a video|next video)", re.I)


def comments(url, pages=2, use_ai=False):
    """Top comments of a video: common words, questions, requests (1 quota unit per 100 comments)."""
    vid = util.video_id(url)
    if not vid:
        raise YouTubeError("ده مش لينك فيديو يوتيوب.")
    items, token = [], None
    for _ in range(pages):
        params = {"part": "snippet", "videoId": vid, "maxResults": 100, "order": "relevance", "textFormat": "plainText"}
        if token:
            params["pageToken"] = token
        res = youtube.call("commentThreads", params, ttl=HOUR)
        items += res.get("items", [])
        token = res.get("nextPageToken")
        if not token:
            break
    rows = []
    for it in items:
        s = it["snippet"]["topLevelComment"]["snippet"]
        rows.append({"text": s.get("textDisplay", ""), "likes": s.get("likeCount", 0), "author": s.get("authorDisplayName", ""),
                     "published": s.get("publishedAt"), "replies": it["snippet"].get("totalReplyCount", 0)})
    words = Counter()
    for r in rows:
        words.update({t for t in TOKEN.findall(util.normalize(r["text"])) if len(t) > 2 and t not in STOPWORDS and not t.isdigit()})
    by_likes = sorted(rows, key=lambda r: r["likes"], reverse=True)
    video = youtube.videos([vid], ttl=HOUR)
    title = video[0]["snippet"]["title"] if video else ""
    result = {
        "video": {"id": vid, "title": title},
        "count": len(rows),
        "words": [{"word": w, "count": n} for w, n in words.most_common(40)],
        "questions": [r for r in by_likes if "?" in r["text"] or "؟" in r["text"]][:10],
        "requests": [r for r in by_likes if REQUEST.search(r["text"])][:10],
        "top": by_likes[:5],
    }
    if use_ai and rows:
        from . import ai
        result["ai"] = ai.summarize_comments(title, rows)
    return result


# ---------- backup ----------

BACKUP_DIR = config.DATA_DIR / "backups"
SAFE_NAME = re.compile(r"^[\w\-.]+$")


def backup():
    """Save every upload's title, description, tags and stats as JSON and CSV (about 2 units per 50 videos)."""
    item = mychannel.channel(ttl=0)
    c = youtube.channel_summary(item)
    videos = mychannel.uploads_all(item)
    BACKUP_DIR.mkdir(exist_ok=True)
    stamp = datetime.now(config.tz()).strftime("%Y-%m-%d_%H%M")
    name = re.sub(r"[^\w-]", "", c["handle"] or c["id"]) or "channel"
    base = f"{name}_{stamp}"
    (BACKUP_DIR / f"{base}.json").write_text(json.dumps({"channel": c, "videos": videos}, ensure_ascii=False, indent=1), encoding="utf-8")
    with open(BACKUP_DIR / f"{base}.csv", "w", newline="", encoding="utf-8-sig") as f:  # utf-8-sig so Excel reads Arabic
        w = csv.writer(f)
        w.writerow(["id", "title", "published", "views", "likes", "comments", "duration_s", "is_short", "tags", "description"])
        for v in videos:
            w.writerow([v["id"], v["title"], v["published"], v["views"], v["likes"], v["comments"], v["duration"],
                        v["is_short"], ", ".join(v["tags"]), v["description"]])
    return {"count": len(videos), "files": [f"{base}.json", f"{base}.csv"], "folder": str(BACKUP_DIR)}


def backups():
    if not BACKUP_DIR.exists():
        return []
    return sorted((p.name for p in BACKUP_DIR.iterdir() if p.is_file()), reverse=True)


def backup_path(name):
    path = BACKUP_DIR / name
    if not SAFE_NAME.match(name) or not path.is_file():
        raise YouTubeError("الملف ده مش موجود.")
    return path


# ---------- idea signals ----------

def idea_signals():
    """Everything that hints at a good next video, gathered from data already collected (cheap on quota)."""
    s = {"niche_keywords": config.niche_keywords()}
    s["competitor_outliers"] = [{"title": r["title"], "channel": r["channel_title"], "times_usual": r["outlier"], "age_days": r["age_days"]}
                                for r in competitors.outliers(30, "long", limit=15)]
    try:
        s["niche_trending"] = [{"title": v["title"], "channel": v["channel_title"], "rank": v["rank"]}
                               for v in trends.trending() if v["niche"]][:10]
    except YouTubeError:
        s["niche_trending"] = []
    if oauth.connected():
        try:
            s["my_search_terms"] = [{"term": r["insightTrafficSourceDetail"], "views": r["views"]} for r in analytics.search_terms(28)][:15]
            s["my_top_videos"] = [{"title": r["title"], "views": r["views"]} for r in analytics.top_videos(28)][:5]
        except (oauth.AuthError, YouTubeError):
            pass
    s["already_planned"] = [i["title"] for i in planner.ideas()]
    return s
