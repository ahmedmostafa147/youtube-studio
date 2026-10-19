import base64
import re
from contextlib import asynccontextmanager
from datetime import date

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import (ai, alerts, analytics, competitors, config, db, insights, jobs, keywords, mychannel, oauth, planner, seo,
               suggest, trends, util, youtube)
from .ai import AIError
from .oauth import AuthError
from .youtube import YouTubeError


@asynccontextmanager
async def lifespan(app):
    jobs.start()
    yield


app = FastAPI(title="Nuqta Studio", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=config.WEB_DIR), name="static")


@app.middleware("http")
async def no_cache(request: Request, call_next):
    # Local app: always serve the latest page files after an update.
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-cache"
    return response


@app.exception_handler(YouTubeError)
async def youtube_error(request: Request, e: YouTubeError):
    return JSONResponse({"error": str(e)}, status_code=400)


@app.exception_handler(AuthError)
async def auth_error(request: Request, e: AuthError):
    return JSONResponse({"error": str(e), "auth": True}, status_code=401)


@app.exception_handler(AIError)
async def ai_error(request: Request, e: AIError):
    return JSONResponse({"error": str(e), "ai": True}, status_code=400)


@app.exception_handler(ValueError)
async def value_error(request: Request, e: ValueError):
    return JSONResponse({"error": str(e)}, status_code=400)


@app.exception_handler(httpx.HTTPError)
async def network_error(request: Request, e: httpx.HTTPError):
    return JSONResponse({"error": "مشكلة في الاتصال بجوجل. اتأكد إن النت شغال وجرّب تاني."}, status_code=502)


@app.get("/")
def index():
    return FileResponse(config.WEB_DIR / "index.html")


# ---------- status & settings ----------

@app.get("/api/status")
def status():
    return {
        "has_key": bool(config.get("YOUTUBE_API_KEY")),
        "has_client": oauth.has_client(),
        "connected": oauth.connected(),
        "quota": {"used": db.quota_used(), "limit": config.DAILY_QUOTA},
        "region": config.region(),
        "lang": config.lang(),
        "redirect_uri": oauth.redirect_uri(),
        "has_ai": ai.available(),
        "my_channel": {"id": config.get("MY_CHANNEL_ID"), "title": config.get("MY_CHANNEL_TITLE")},
        "niche_keywords": config.get("NICHE_KEYWORDS"),
        "rpm": config.rpm(),
        "channel_voice": config.get("CHANNEL_VOICE"),
        "thumbnail_rules": config.get("THUMBNAIL_RULES"),
        "unread_alerts": alerts.unread_count(),
        "last_job": jobs.last_run(),
    }


class Settings(BaseModel):
    youtube_api_key: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""
    anthropic_api_key: str = ""
    region: str = ""
    lang: str = ""
    my_channel: str = ""
    niche_keywords: str | None = None
    rpm: str = ""
    channel_voice: str | None = None
    thumbnail_rules: str | None = None


@app.post("/api/settings")
def save_settings(s: Settings):
    updates = {
        "YOUTUBE_API_KEY": s.youtube_api_key,
        "GOOGLE_CLIENT_ID": s.google_client_id,
        "GOOGLE_CLIENT_SECRET": s.google_client_secret,
        "YT_REGION": s.region.upper(),
        "YT_LANG": s.lang.lower(),
        "ANTHROPIC_API_KEY": s.anthropic_api_key,
        "RPM": s.rpm,
    }
    # Empty fields mean "keep what is saved".
    changes = {k: v for k, v in updates.items() if v.strip()}
    # Free-text settings can be cleared on purpose, and .env holds one line per key.
    for key, value in (("NICHE_KEYWORDS", s.niche_keywords), ("CHANNEL_VOICE", s.channel_voice), ("THUMBNAIL_RULES", s.thumbnail_rules)):
        if value is not None:
            changes[key] = " ".join(value.split())
    config.save(changes)
    if s.my_channel.strip():
        c = mychannel.set_channel(s.my_channel)
        config.save({"MY_CHANNEL_TITLE": c["title"]})
    return status()


# ---------- keywords ----------

@app.get("/api/suggest")
def api_suggest(q: str):
    return suggest.autocomplete(q)


@app.get("/api/keywords/explore")
def api_explore(q: str):
    return suggest.explore(q)


@app.get("/api/keywords/analyze")
def api_analyze(q: str):
    if not q.strip():
        raise YouTubeError("اكتب كلمة الأول.")
    return keywords.analyze(q)


# ---------- single video ----------

@app.get("/api/video")
def api_video(url: str, keyword: str = ""):
    vid = util.video_id(url)
    if not vid:
        raise YouTubeError("ده مش لينك فيديو يوتيوب.")
    items = youtube.videos([vid], ttl=3600)
    if not items:
        raise YouTubeError("الفيديو ده مش موجود أو خاص.")
    v = youtube.summary(items[0])
    channel = youtube.channels([v["channel_id"]])[0]
    recent = [youtube.summary(x) for x in youtube.uploads(channel)]
    same_format = [x["views"] for x in recent if x["is_short"] == v["is_short"] and x["id"] != v["id"]]
    median = util.median(same_format)
    v["channel"] = {**youtube.channel_summary(channel), "median_views": round(median)}
    v["outlier"] = round(v["views"] / median, 2) if median else None
    reactions = (v["likes"] or 0) + (v["comments"] or 0)
    v["engagement"] = round(reactions / v["views"] * 100, 2) if v["views"] else 0
    v["seo"] = seo.score(v["title"], v["description"], v["tags"], keyword)
    return v


class SeoInput(BaseModel):
    title: str = ""
    description: str = ""
    tags: list[str] = []
    keyword: str = ""


@app.post("/api/seo")
def api_seo(body: SeoInput):
    return seo.score(body.title, body.description, body.tags, body.keyword)


# ---------- competitors ----------

class CompetitorInput(BaseModel):
    query: str


@app.get("/api/competitors")
def api_competitors():
    return competitors.list_all()


@app.post("/api/competitors")
def api_add_competitor(body: CompetitorInput):
    return competitors.add(body.query)


@app.delete("/api/competitors/{channel_id}")
def api_remove_competitor(channel_id: str):
    competitors.remove(channel_id)
    return {"ok": True}


@app.post("/api/competitors/refresh")
def api_refresh_competitors():
    return {"refreshed": competitors.refresh_all()}


@app.get("/api/outliers")
def api_outliers(days: int = 90, format: str = "all", channel: str = ""):
    return competitors.outliers(days, format, channel or None)


@app.get("/api/timing")
def api_timing():
    return competitors.timing()


# ---------- my channel ----------

@app.get("/auth/login")
def auth_login():
    return RedirectResponse(oauth.login_url())


@app.get("/auth/callback")
def auth_callback(code: str = "", state: str = "", error: str = ""):
    if error or not code:
        return HTMLResponse(f"<p dir=rtl>اتلغى ربط القناة ({error or 'مفيش كود'}). <a href='/#me'>ارجع</a></p>")
    oauth.handle_callback(code, state)
    if not config.get("MY_CHANNEL_ID"):
        me = analytics.me()
        config.save({"MY_CHANNEL_ID": me["id"], "MY_CHANNEL_TITLE": me["title"]})
    return RedirectResponse("/#me")


@app.post("/auth/logout")
def auth_logout():
    oauth.logout()
    return {"ok": True}


@app.get("/api/me")
def api_me():
    return analytics.me()


@app.get("/api/me/overview")
def api_me_overview(days: int = 28):
    return analytics.overview(days)


@app.get("/api/me/videos")
def api_me_videos(days: int = 28):
    return analytics.top_videos(days)


@app.get("/api/me/traffic")
def api_me_traffic(days: int = 28):
    return analytics.traffic(days)


@app.get("/api/me/search-terms")
def api_me_search_terms(days: int = 28):
    return analytics.search_terms(days)


@app.get("/api/me/audience")
def api_me_audience(days: int = 28):
    return analytics.audience(days)


@app.get("/api/me/recent")
def api_me_recent():
    return mychannel.recent()


# ---------- alerts & background jobs ----------

@app.get("/api/alerts")
def api_alerts(unread: bool = False):
    return alerts.recent(unread_only=unread)


class AlertRead(BaseModel):
    id: int | None = None


@app.post("/api/alerts/read")
def api_alerts_read(body: AlertRead):
    alerts.mark_read(body.id)
    return {"unread": alerts.unread_count()}


@app.post("/api/jobs/run")
def api_jobs_run():
    return jobs.run_once()


# ---------- trends & ideas ----------

@app.get("/api/trends")
def api_trends(category: str = ""):
    return trends.trending(category)


@app.get("/api/trends/categories")
def api_trend_categories():
    return trends.categories()


@app.get("/api/ideas")
def api_ideas():
    return planner.ideas()


class IdeaInput(BaseModel):
    title: str | None = None
    keyword: str | None = None
    notes: str | None = None
    status: str | None = None
    score: int | None = None
    source: str = "manual"


@app.post("/api/ideas")
def api_add_idea(body: IdeaInput):
    if not (body.title or "").strip():
        raise ValueError("اكتب الفكرة الأول.")
    return planner.add_idea(body.title, body.keyword or "", body.notes or "", body.source, body.score)


@app.patch("/api/ideas/{idea_id}")
def api_update_idea(idea_id: int, body: IdeaInput):
    return planner.update_idea(idea_id, title=body.title, keyword=body.keyword, notes=body.notes, status=body.status, score=body.score)


@app.delete("/api/ideas/{idea_id}")
def api_delete_idea(idea_id: int):
    planner.delete_idea(idea_id)
    return {"ok": True}


@app.get("/api/ideas/signals")
def api_idea_signals():
    return insights.idea_signals()


@app.get("/api/ideas/daily")
def api_daily_ideas(refresh: bool = False):
    key = f"ideas:{date.today().isoformat()}"
    cached = None if refresh else db.cache_get(key, 24 * 3600)
    if cached:
        return {**cached, "cached": True}
    result = ai.daily_ideas(insights.idea_signals())
    db.cache_set(key, result)
    return result


# ---------- tags ----------

@app.get("/api/taglists")
def api_tag_lists():
    return planner.tag_lists()


class TagListInput(BaseModel):
    name: str
    tags: list[str]


@app.post("/api/taglists")
def api_save_tag_list(body: TagListInput):
    if not body.name.strip():
        raise ValueError("اكتب اسم للقايمة.")
    planner.save_tag_list(body.name, body.tags)
    return planner.tag_lists()


@app.delete("/api/taglists/{name}")
def api_delete_tag_list(name: str):
    planner.delete_tag_list(name)
    return planner.tag_lists()


class SortTagsInput(BaseModel):
    tags: list[str]
    keyword: str = ""


@app.post("/api/tags/sort")
def api_sort_tags(body: SortTagsInput):
    return planner.sort_tags(body.tags, body.keyword)


# ---------- AI writing ----------

class WriteInput(BaseModel):
    topic: str = ""
    title: str = ""
    keyword: str = ""
    notes: str = ""
    transcript: str = ""
    minutes: int = 8


def _reference_titles(keyword):
    analysis = keywords.cached(keyword) if keyword else None
    if analysis and analysis.get("videos"):
        return [v["title"] for v in analysis["videos"][:12]]
    return [r["title"] for r in competitors.outliers(90, "long", limit=12)]


@app.post("/api/ai/titles")
def api_ai_titles(body: WriteInput):
    topic = body.topic or body.title
    if not topic.strip():
        raise ValueError("اكتب موضوع الفيديو الأول.")
    return ai.titles(topic, body.keyword, body.notes, _reference_titles(body.keyword))


@app.post("/api/ai/description")
def api_ai_description(body: WriteInput):
    if not body.title.strip():
        raise ValueError("اكتب عنوان الفيديو الأول.")
    return ai.description(body.title, body.keyword, body.notes, body.transcript)


@app.post("/api/ai/script")
def api_ai_script(body: WriteInput):
    if not body.topic.strip():
        raise ValueError("اكتب موضوع الفيديو الأول.")
    return ai.script(body.topic, body.keyword, body.minutes, body.notes)


@app.post("/api/ai/chapters")
def api_ai_chapters(body: WriteInput):
    return ai.chapters(body.transcript)


# ---------- thumbnails ----------

@app.get("/api/thumbnail/context")
def api_thumbnail_context(keyword: str = ""):
    """Real thumbnails to preview yours against, without spending quota."""
    analysis = keywords.cached(keyword) if keyword.strip() else None
    fields = ("id", "title", "channel_title", "thumbnail", "views", "age_days")
    search = [{k: v[k] for k in fields} for v in analysis["videos"][:12]] if analysis and analysis.get("videos") else []
    home = [{"id": r["video_id"], "title": r["title"], "channel_title": r["channel_title"], "thumbnail": r["thumbnail"],
             "views": r["views"], "age_days": r["age_days"]} for r in competitors.outliers(60, "long", limit=12)]
    return {"search": search, "home": home, "keyword_cached": bool(analysis)}


class ThumbnailInput(BaseModel):
    image: str  # data URL from the browser
    title: str = ""
    keyword: str = ""


DATA_URL = re.compile(r"^data:(image/(?:png|jpeg|webp|gif));base64,(.+)$", re.S)


@app.post("/api/thumbnail/review")
def api_thumbnail_review(body: ThumbnailInput):
    m = DATA_URL.match(body.image)
    if not m:
        raise ValueError("ارفع صورة PNG أو JPG.")
    if len(base64.b64decode(m.group(2), validate=False)) > 5_000_000:
        raise ValueError("الصورة أكبر من 5MB.")
    return ai.review_thumbnail(m.group(2), m.group(1), body.title, body.keyword)


# ---------- channel insights ----------

@app.get("/api/audit")
def api_audit(channel: str = ""):
    return insights.audit(channel)


@app.get("/api/retention")
def api_retention(url: str):
    return insights.retention(url)


@app.get("/api/scorecard")
def api_scorecard():
    return insights.scorecard()


@app.get("/api/earnings")
def api_earnings(rpm: float = 0, channel: str = ""):
    return insights.earnings(rpm or None, channel)


@app.get("/api/milestones")
def api_milestones():
    return insights.milestones()


class AdSafetyInput(BaseModel):
    title: str = ""
    description: str = ""
    tags: list[str] = []
    transcript: str = ""


@app.post("/api/ad-safety")
def api_ad_safety(body: AdSafetyInput):
    return insights.ad_safety(body.title, body.description, body.tags, body.transcript)


@app.get("/api/comments")
def api_comments(url: str, ai: bool = False):
    return insights.comments(url, use_ai=ai)


@app.post("/api/backup")
def api_backup():
    return insights.backup()


@app.get("/api/backups")
def api_backups():
    return insights.backups()


@app.get("/api/backups/{name}")
def api_backup_file(name: str):
    return FileResponse(insights.backup_path(name), filename=name)
