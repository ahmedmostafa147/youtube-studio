"""MCP server: the studio's features as tools for Claude Code (or any MCP client).

Shares .env and data/ with the dashboard, so competitors added in one show up in the other.
Linking your own channel (OAuth) is done once from the dashboard: run.bat → قناتي.

Register with Claude Code:
  claude mcp add youtube-studio -- "<path>/studio/.venv/Scripts/python.exe" "<path>/studio/mcp_server.py"
"""

import functools

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from app import alerts as alerts_mod
from app import (analytics, competitors, config, db, insights, jobs, keywords, mychannel, oauth, planner, seo,
                 suggest, trends, util, youtube)

server = MCPServer(
    name="youtube-studio",
    instructions=(
        "YouTube research tools (a local vidIQ/TubeBuddy alternative). The YouTube Data API has a free quota "
        "of 10,000 units/day: analyze_keyword costs ~102 units, everything else 0-4. Prefer the free tools "
        "(autocomplete, keyword_ideas, seo_check) for brainstorming and only analyze the most promising keywords. "
        "Scores are estimates for comparing keywords, not real search volumes. "
        "For titles, descriptions, scripts, chapters and video ideas, write them yourself from this data "
        "(idea_signals, analyze_keyword, competitor_outliers, my_search_terms) and check them with score_titles, "
        "seo_check and ad_safety_check. No extra AI key is needed for that."
    ),
)

VIDEO_URL = "https://www.youtube.com/watch?v="


def tool(fn):
    """Register a tool, turning the app's errors into messages the model can read and act on."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except youtube.YouTubeError as e:
            raise ToolError(str(e)) from e
        except oauth.AuthError as e:
            raise ToolError(f"{e} Link the channel once from the dashboard: run studio/run.bat, open قناتي.") from e
        except httpx.HTTPError as e:
            raise ToolError("Network error talking to Google. Check the internet connection and retry.") from e
    return server.tool()(wrapper)


def _video(v, *extra):
    """Compact video row for the model: no thumbnails or descriptions."""
    row = {
        "title": v["title"],
        "url": VIDEO_URL + (v.get("id") or v.get("video_id")),
        "channel": v.get("channel_title", ""),
        "views": v["views"],
        "views_per_day": v["vpd"],
        "age_days": v["age_days"],
        "is_short": v["is_short"],
    }
    for key in extra:
        if key in v:
            row[key] = v[key]
    return row


# ---------- keywords ----------

@tool
def autocomplete(query: str) -> list[str]:
    """YouTube search suggestions for a query, as people type it. Free (no quota)."""
    return suggest.autocomplete(query)


@tool
def keyword_ideas(keyword: str) -> list[str]:
    """Long-tail keyword ideas: autocomplete for the keyword + every letter, and question words in front. Free."""
    return suggest.explore(keyword)


@tool
def analyze_keyword(keyword: str) -> dict:
    """Score a keyword 0-100 (overall, demand, competition) from the top 25 YouTube results, with notes,
    related searches, most-used tags and the ranking videos. Costs ~102 quota units."""
    d = keywords.analyze(keyword)
    if d.get("empty"):
        return d
    d["videos"] = [_video(v, "subs", "outlier", "title_match") for v in d["videos"]]
    d["note"] = "outlier here = views / channel subscribers. demand/competition are estimates."
    return d


# ---------- videos & SEO ----------

@tool
def analyze_video(url: str, keyword: str = "") -> dict:
    """A video's stats, tags, description, performance vs its channel's usual (outlier = views / channel median)
    and an SEO checklist (pass `keyword` to check targeting). Costs ~4 quota units."""
    vid = util.video_id(url)
    if not vid:
        raise youtube.YouTubeError("Not a YouTube video URL.")
    items = youtube.videos([vid], ttl=3600)
    if not items:
        raise youtube.YouTubeError("Video not found or private.")
    v = youtube.summary(items[0])
    channel = youtube.channels([v["channel_id"]])[0]
    recent = [youtube.summary(x) for x in youtube.uploads(channel)]
    median = util.median([x["views"] for x in recent if x["is_short"] == v["is_short"] and x["id"] != v["id"]])
    row = _video(v, "likes", "comments", "duration", "tags", "description", "published")
    row["channel_subs"] = youtube.channel_summary(channel)["subs"]
    row["channel_median_views"] = round(median)
    row["outlier"] = round(v["views"] / median, 2) if median else None
    row["seo"] = seo.score(v["title"], v["description"], v["tags"], keyword)
    return row


@tool
def seo_check(title: str, description: str = "", tags: list[str] | None = None, keyword: str = "") -> dict:
    """Score a draft title/description/tags 0-100 with a checklist and fix tips (Arabic). Free."""
    return seo.score(title, description, tags or [], keyword)


# ---------- competitors ----------

@tool
def list_competitors() -> list[dict]:
    """Tracked competitor channels with subscribers, usual views (median) and uploads in the last 30 days."""
    return [
        {k: c[k] for k in ("channel_id", "title", "handle", "subs", "median_views", "median_views_shorts", "uploads_30d")}
        for c in competitors.list_all()
    ]


@tool
def add_competitor(channel: str) -> dict:
    """Track a channel by URL, @handle or UC… id (a plain name costs a 100-unit search). ~3 quota units."""
    c = competitors.add(channel)
    return {k: c[k] for k in ("id", "title", "handle", "subs", "video_count")}


@tool
def remove_competitor(channel_id: str) -> str:
    """Stop tracking a competitor (channel_id from list_competitors) and delete its stored videos."""
    competitors.remove(channel_id)
    return "removed"


@tool
def competitor_outliers(days: int = 90, format: str = "long", channel_id: str = "", limit: int = 25) -> list[dict]:
    """Competitors' videos that beat their channel's usual views (outlier = views / channel median).
    format: long | short | all. Uses stored data (free); call refresh_competitors for fresh numbers."""
    rows = competitors.outliers(days, format, channel_id or None, limit)
    return [{**_video(r, "outlier", "channel_median", "growth_per_day"), "channel": r["channel_title"]} for r in rows]


@tool
def refresh_competitors() -> str:
    """Re-fetch all competitors' latest 50 uploads (~3 quota units per channel)."""
    return f"refreshed {competitors.refresh_all()} channels"


@tool
def best_posting_time() -> dict:
    """Median outlier score of competitors' long videos by weekday and 3-hour block (local time). Free."""
    return competitors.timing()


# ---------- my channel (needs OAuth from the dashboard) ----------

@tool
def my_channel(days: int = 28) -> dict:
    """Your channel: totals vs the previous period and daily views. Requires linking the channel once in the dashboard."""
    return {"channel": analytics.me(), **analytics.overview(days)}


@tool
def my_search_terms(days: int = 28) -> list[dict]:
    """The real YouTube searches that brought viewers to your videos, with views."""
    return [{"term": r["insightTrafficSourceDetail"], "views": r["views"]} for r in analytics.search_terms(days)]


@tool
def my_top_videos(days: int = 28) -> list[dict]:
    """Your videos ranked by views in the period: watch time, average view duration/percentage, subscribers gained."""
    rows = analytics.top_videos(days)
    return [
        {
            "title": r["title"], "url": VIDEO_URL + r["video"], "views": r["views"],
            "watch_hours": round(r["estimatedMinutesWatched"] / 60, 1),
            "avg_view_seconds": r["averageViewDuration"], "avg_view_percent": round(r["averageViewPercentage"], 1),
            "subscribers_gained": r["subscribersGained"], "is_short": r["is_short"],
        }
        for r in rows
    ]


@tool
def my_traffic_sources(days: int = 28) -> list[dict]:
    """Where your views come from (search, suggested, browse, external...)."""
    return [{"source": r["label"], "views": r["views"], "watch_minutes": r["estimatedMinutesWatched"]} for r in analytics.traffic(days)]


@tool
def my_audience(days: int = 28) -> dict:
    """Top countries by views, and viewer percentage by age group and gender."""
    return analytics.audience(days)


@tool
def quota_status() -> dict:
    """YouTube Data API units used today (resets at midnight Pacific, ~10:00 Cairo) and whether keys are set."""
    return {
        "used": db.quota_used(), "limit": config.DAILY_QUOTA,
        "has_api_key": bool(config.get("YOUTUBE_API_KEY")), "channel_linked": oauth.connected(),
    }


# ---------- phase 1: ideas, alerts, trends ----------

@tool
def idea_signals() -> dict:
    """Everything that hints at a good next video: competitor outliers (30 days), trending videos in your niche,
    your real search terms and top videos (if the channel is linked), and ideas already planned.
    Use it to propose video ideas yourself; no AI key is needed. About 1-3 quota units."""
    return insights.idea_signals()


@tool
def trending_videos(category_id: str = "", niche_only: bool = False) -> list[dict]:
    """YouTube's most popular videos in your region (1 quota unit). niche_only keeps videos matching your niche keywords."""
    rows = trends.trending(category_id)
    if niche_only:
        rows = [v for v in rows if v["niche"]]
    return [{**_video(v), "rank": v["rank"], "niche": v["niche"]} for v in rows]


@tool
def alerts(unread_only: bool = True, limit: int = 30) -> list[dict]:
    """New competitor uploads, competitor videos taking off, and niche trends found by the background checks."""
    return [{k: a[k] for k in ("id", "kind", "title", "body", "url", "read")} for a in alerts_mod.recent(limit, unread_only)]


@tool
def mark_alerts_read() -> str:
    """Mark every alert as read."""
    alerts_mod.mark_read()
    return "done"


@tool
def run_checks() -> dict:
    """Run the background checks now: refresh competitors, find take-offs and niche trends, record your recent views.
    About 3 quota units per competitor."""
    return jobs.run_once()


@tool
def list_ideas() -> list[dict]:
    """The video planner: every idea with its stage (idea, writing, filming, editing, published)."""
    return [{k: i[k] for k in ("id", "title", "keyword", "notes", "status", "source")} for i in planner.ideas()]


@tool
def add_idea(title: str, keyword: str = "", notes: str = "") -> dict:
    """Add a video idea to the planner (shows up in the dashboard too)."""
    return planner.add_idea(title, keyword, notes, source="claude")


@tool
def update_idea(idea_id: int, status: str = "", title: str = "", keyword: str = "", notes: str = "") -> dict:
    """Change an idea's stage (idea, writing, filming, editing, published) or its text."""
    return planner.update_idea(idea_id, status=status or None, title=title or None, keyword=keyword or None, notes=notes or None)


# ---------- phase 1: writing helpers (you write; these check) ----------

@tool
def score_titles(titles: list[str], keyword: str = "") -> list[dict]:
    """Score candidate titles 0-100 on length and where the target phrase sits. Free. Use it to rank titles you wrote."""
    rows = [{"title": t, "length": len(t), "seo_score": seo.title_score(t, keyword)} for t in titles]
    return sorted(rows, key=lambda r: r["seo_score"], reverse=True)


@tool
def ad_safety_check(title: str = "", description: str = "", tags: list[str] | None = None, transcript: str = "") -> dict:
    """Words that often get a video limited ads (YouTube advertiser-friendly guidelines), by where they appear. Free."""
    return insights.ad_safety(title, description, tags or [], transcript)


@tool
def sort_tags(tags: list[str], keyword: str = "") -> list[str]:
    """Remove duplicate tags and put the exact target phrase first, then related tags. Free."""
    return planner.sort_tags(tags, keyword)


@tool
def tag_lists() -> list[dict]:
    """Saved tag lists."""
    return planner.tag_lists()


@tool
def save_tag_list(name: str, tags: list[str]) -> str:
    """Save (or replace) a named tag list."""
    planner.save_tag_list(name, tags)
    return "saved"


# ---------- phase 1: channel insights ----------

@tool
def set_my_channel(channel: str) -> dict:
    """Set your own channel by URL or @handle, so the my_* public tools and the scorecard know which one is yours."""
    c = mychannel.set_channel(channel)
    config.save({"MY_CHANNEL_TITLE": c["title"]})
    return c


@tool
def my_recent_videos() -> dict:
    """Your latest uploads with views, views per hour and last-48h views (needs your channel set). ~3 quota units."""
    d = mychannel.recent()
    return {"channel": d["channel"], "videos": [_video(v, "vph", "last_48h") for v in d["videos"]]}


@tool
def channel_audit(channel: str = "") -> dict:
    """Health check of a channel's last 50 uploads (yours by default): upload rhythm, view trend, chapters,
    descriptions, tags, title length, engagement, best and worst videos. ~3 quota units."""
    a = insights.audit(channel)
    for key in ("best", "worst"):
        a[key] = [_video(v, "outlier") for v in a.get(key, [])]
    return a


@tool
def video_retention(url: str) -> dict:
    """Audience retention curve of one of YOUR videos: % still watching at 30s and halfway, and the biggest drops.
    Needs the channel linked (OAuth)."""
    return insights.retention(url)


@tool
def scorecard() -> dict:
    """Your channel next to every competitor: subscribers, growth, usual views, uploads, engagement, views per sub,
    outliers in 90 days, each with its rank."""
    return insights.scorecard()


@tool
def earnings_estimate(rpm: float = 0, channel: str = "") -> dict:
    """Estimated monthly/yearly earnings and channel value from views and an RPM in USD (yours by default)."""
    return insights.earnings(rpm or None, channel)


@tool
def milestones() -> dict:
    """Next subscriber/view milestones with an estimated date, and progress toward the Partner Program."""
    return insights.milestones()


@tool
def comment_insights(url: str) -> dict:
    """A video's top 200 comments: most used words, questions, requests, most liked. Summarize them yourself. ~3 units."""
    return insights.comments(url)


@tool
def backup_channel() -> dict:
    """Save every upload's title, description, tags and stats to JSON + CSV in studio/data/backups."""
    return insights.backup()


if __name__ == "__main__":
    server.run()
