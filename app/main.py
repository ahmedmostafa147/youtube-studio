import threading
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import analytics, competitors, config, db, keywords, oauth, seo, suggest, util, youtube
from .oauth import AuthError
from .youtube import YouTubeError


def _refresh_stale_competitors():
    try:
        if config.get("YOUTUBE_API_KEY"):
            competitors.refresh_all(only_stale=True)
    except (YouTubeError, httpx.HTTPError) as e:
        print("competitor refresh skipped:", e)


@asynccontextmanager
async def lifespan(app):
    threading.Thread(target=_refresh_stale_competitors, daemon=True).start()
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
    }


class Settings(BaseModel):
    youtube_api_key: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""
    region: str = ""
    lang: str = ""


@app.post("/api/settings")
def save_settings(s: Settings):
    updates = {
        "YOUTUBE_API_KEY": s.youtube_api_key,
        "GOOGLE_CLIENT_ID": s.google_client_id,
        "GOOGLE_CLIENT_SECRET": s.google_client_secret,
        "YT_REGION": s.region.upper(),
        "YT_LANG": s.lang.lower(),
    }
    # Empty fields mean "keep what is saved".
    config.save({k: v for k, v in updates.items() if v.strip()})
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
