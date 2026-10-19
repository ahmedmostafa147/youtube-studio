"""MCP server: the studio's features as tools for Claude Code (or any MCP client).

Shares .env and data/ with the dashboard, so competitors added in one show up in the other.
Linking your own channel (OAuth) is done once from the dashboard: run.bat → قناتي.

Register with Claude Code:
  claude mcp add youtube-studio -- "<path>/studio/.venv/Scripts/python.exe" "<path>/studio/mcp_server.py"
"""

import base64
import functools
from datetime import datetime
from pathlib import Path

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from app import alerts as alerts_mod
from app import (abtest, analytics, bulk, competitors, config, db, editor, insights, jobs, keywords, mychannel, oauth,
                 planner, playlists, ranks, replies, schedule, seo, suggest, trends, util, youtube)

server = MCPServer(
    name="youtube-studio",
    instructions=(
        "YouTube research tools (a local vidIQ/TubeBuddy alternative). The YouTube Data API has a free quota "
        "of 10,000 units/day: analyze_keyword costs ~102 units, everything else 0-4. Prefer the free tools "
        "(autocomplete, keyword_ideas, seo_check) for brainstorming and only analyze the most promising keywords. "
        "Scores are estimates for comparing keywords, not real search volumes. "
        "For titles, descriptions, scripts, chapters and video ideas, write them yourself from this data "
        "(idea_signals, analyze_keyword, competitor_outliers, my_search_terms) and check them with score_titles, "
        "seo_check and ad_safety_check. No extra AI key is needed for that. "
        "Tools that change the channel (edit_video, bulk_edit_apply, save_localizations, schedule_change, "
        "start_ab_test, add_to_playlist, reorder_playlist, reply_to_comment, ...) are dry runs unless confirm=true: "
        "show the preview to the user and only call again with confirm=true after they explicitly approve. "
        "Each change costs 50 quota units; tag_rankings and rank tracking cost 100 units per keyword."
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
        except ValueError as e:
            raise ToolError(str(e)) from e
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


# ---------- phase 2: editing your channel ----------
# Reading and previewing is free to call. Every tool that changes something on YouTube is a dry run unless
# confirm=true: call it once without confirm, show the preview to the user, and only repeat with confirm=true
# after they explicitly approve. Each change costs 50 quota units.

NOT_CONFIRMED = ("Nothing was changed on YouTube. Show this preview to the user and call again with confirm=true "
                 "only after they explicitly approve it.")


def _dry(preview, writes):
    return {"confirmed": False, "preview": preview, "quota_cost": writes * youtube.WRITE_COST, "note": NOT_CONFIRMED}


def _image_data_url(path):
    """A local PNG/JPG file as a data URL, for thumbnails passed by path."""
    p = Path(path).expanduser()
    if p.suffix.lower() not in (".png", ".jpg", ".jpeg") or not p.is_file():
        raise ValueError("Thumbnail must be an existing .png or .jpg file.")
    mime = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
    return f"data:{mime};base64," + base64.b64encode(p.read_bytes()).decode()


def _brief(v):
    return {k: v[k] for k in ("id", "title", "description", "tags", "category_id", "default_language", "privacy", "localizations")}


@tool
def editing_status() -> dict:
    """Whether the studio may change the channel: editing turned on in Settings, and the write permission
    (youtube.force-ssl) approved when linking. Also today's quota left (each change = 50 units)."""
    return editor.status()


@tool
def video_details(url: str) -> dict:
    """Your video's current title, description, tags, category, language, visibility and translations. 1 unit."""
    return _brief(editor.video(url))


@tool
def edit_video(url: str, title: str | None = None, description: str | None = None, tags: list[str] | None = None,
               confirm: bool = False) -> dict:
    """Change a video's title, description and/or tags (fields left out stay as they are).
    Dry run unless confirm=true. 50 units when applied; undo with undo_edit."""
    v = editor.video(url)
    after = {"title": title if title is not None else v["title"], "description": description if description is not None else v["description"],
             "tags": tags if tags is not None else v["tags"]}
    found = editor.problems(after["title"], after["description"], after["tags"])
    if not confirm or found:
        before = {k: v[k] for k in after}
        return {**_dry({"before": before, "after": after, "problems": found}, 1), **({"error": found} if found else {})}
    return editor.update(url, title, description, tags, source="mcp")


@tool
def bulk_edit_preview(field: str = "description", mode: str = "replace", find: str = "", replace: str = "",
                      case_sensitive: bool = False, videos: list[str] | None = None) -> dict:
    """Dry run of a bulk change over all your uploads (or the given video links): field = description | title,
    mode = replace (find -> replace; empty replace deletes) | append | prepend (adds `replace` text, skipped where
    it is already present). Returns which videos would change with before/after excerpts. ~2 units per 50 videos."""
    d = bulk.preview(field, mode, find, replace, case_sensitive, videos)
    d["matches"] = [{k: m[k] for k in ("id", "title", "count", "excerpts", "problems")} for m in d["matches"]]
    return d


@tool
def bulk_edit_apply(video_ids: list[str], field: str = "description", mode: str = "replace", find: str = "",
                    replace: str = "", case_sensitive: bool = False, confirm: bool = False) -> dict:
    """Apply a bulk change to the chosen videos (ids from bulk_edit_preview that the user approved).
    Dry run unless confirm=true. 50 units per video; each video is re-read and the change recomputed first."""
    if not confirm:
        d = bulk.preview(field, mode, find, replace, case_sensitive, video_ids)
        return _dry([{k: m[k] for k in ("id", "title", "excerpts", "problems")} for m in d["matches"]], len(d["matches"]))
    return bulk.apply(video_ids, field, mode, find, replace, case_sensitive, source="mcp")


@tool
def upload_profiles() -> list[dict]:
    """Saved upload profiles: title/description templates ({title}, {description}, {date}) and tags."""
    return bulk.profiles()


@tool
def save_upload_profile(name: str, title: str = "", description: str = "", tags: list[str] | None = None,
                        tags_mode: str = "append", category_id: str = "") -> list[dict]:
    """Create or replace an upload profile (stored locally, changes nothing on YouTube).
    Empty title/description leave the video's own; tags_mode = append | replace."""
    return bulk.save_profile(name, title, description, tags or [], tags_mode, category_id)


@tool
def apply_upload_profile(name: str, url: str, confirm: bool = False) -> dict:
    """Apply a saved profile to one of your videos. Dry run (before/after) unless confirm=true. 50 units."""
    if not confirm:
        return _dry(bulk.profile_preview(name, url), 1)
    return bulk.profile_apply(name, url, source="mcp")


@tool
def save_localizations(url: str, translations: dict[str, dict[str, str]], confirm: bool = False) -> dict:
    """Save translated titles/descriptions on a video: {"en": {"title": ..., "description": ...}, ...}.
    Translate them yourself (keep links, names and chapter timestamps). Other existing languages are kept.
    Dry run unless confirm=true. 50 units."""
    if not confirm:
        v = editor.video(url)
        found = {lang: editor.problems(t.get("title", ""), t.get("description", "")) for lang, t in translations.items()}
        return _dry({"video": v["title"], "default_language": v["default_language"] or config.lang(),
                     "existing": sorted(v["localizations"]), "new": translations,
                     "problems": {k: p for k, p in found.items() if p}}, 1)
    return editor.save_localizations(url, translations, source="mcp")


@tool
def scheduled_changes() -> list[dict]:
    """Scheduled title/description/thumbnail/visibility changes and their status."""
    return [{k: r[k] for k in ("id", "video_id", "video_title", "kind", "value", "run_at_local", "status", "result")}
            for r in schedule.items()]


@tool
def schedule_change(url: str, kind: str, value: str, when: str, confirm: bool = False) -> dict:
    """Schedule a change: kind = title | description | thumbnail (value = path to a .png/.jpg file) |
    privacy (value = unlisted | private | public, e.g. "sunset" a video). when = local time "YYYY-MM-DDTHH:MM".
    Runs within an hour of `when` while the dashboard is running. Dry run unless confirm=true. 50 units when it runs."""
    run_at = schedule.parse_time(when)
    if not confirm:
        v = editor.video(url)
        current = {"title": v["title"], "description": v["description"], "privacy": v["privacy"], "thumbnail": "(current image)"}
        return _dry({"video": v["title"], "kind": kind, "current": current.get(kind), "new": value,
                     "when": datetime.fromtimestamp(run_at, config.tz()).isoformat()}, 1)
    if kind == "thumbnail":
        value = _image_data_url(value)
    r = schedule.add(url, kind, value, when, source="mcp")
    return {k: r[k] for k in ("id", "video_title", "kind", "run_at_local", "status")}


@tool
def cancel_scheduled_change(change_id: int) -> dict:
    """Cancel a pending scheduled change (nothing is written to YouTube)."""
    r = schedule.cancel(change_id)
    return {k: r[k] for k in ("id", "video_title", "kind", "status")}


@tool
def edit_history(limit: int = 30) -> list[dict]:
    """Every change the studio made on your channel (dashboard, MCP, schedules, A/B), newest first, with undo ids."""
    return [{k: r[k] for k in ("id", "video_id", "video_title", "action", "before", "after", "source", "can_undo")}
            for r in editor.history(limit)]


@tool
def undo_edit(log_id: int, confirm: bool = False) -> dict:
    """Put back the old value of a logged change (id from edit_history). Dry run unless confirm=true. 50 units."""
    if not confirm:
        rows = [r for r in editor.history(500) if r["id"] == log_id]
        if not rows:
            raise ValueError("No such change in the log.")
        r = rows[0]
        return _dry({"video": r["video_title"], "action": r["action"], "restore": r["before"], "current": r["after"],
                     "can_undo": r["can_undo"]}, 1)
    return editor.undo(log_id)


# ---------- phase 2: search ranks ----------

@tool
def tag_rankings(url: str, tags: list[str] | None = None, limit: int = 5) -> dict:
    """Where a video ranks (top 50) in YouTube search for each of its tags or the given keywords.
    Costs 100 quota units PER KEYWORD (limit caps it, max 10). Ask before running more than a few."""
    return ranks.tag_rankings(url, tags, limit)


@tool
def tracked_keywords() -> dict:
    """Keywords whose search rank is checked daily, with today's rank, change and 30-day history.
    daily_cost = keywords x 100 units per day."""
    d = ranks.keywords()
    d["keywords"] = [{k: r[k] for k in ("keyword", "video_id", "latest", "change", "history")} for r in d["keywords"]]
    return d


@tool
def track_keyword(keyword: str, url: str = "") -> dict:
    """Start tracking a keyword daily (adds 100 units/day). Without url: best-ranking video from your channel."""
    ranks.add_keyword(keyword, url)
    return tracked_keywords()


@tool
def untrack_keyword(keyword: str) -> str:
    """Stop tracking a keyword and delete its history."""
    ranks.remove_keyword(keyword)
    return "removed"


@tool
def check_ranks_now() -> dict:
    """Check tracked keywords not yet checked today (100 units each)."""
    return {"checked": ranks.check_ranks(), **tracked_keywords()}


@tool
def brand_mentions_check() -> dict:
    """Search new videos (last 3 days) from other channels mentioning your channel name; found ones become alerts. 100 units."""
    return {"found": ranks.brand_check(force=True), "query": ranks.brand_query()}


# ---------- phase 2: A/B rotation ----------

@tool
def ab_tests() -> list[dict]:
    """Title/thumbnail rotation tests: versions, which one is live, next switch time."""
    return [{k: t[k] for k in ("id", "video_id", "video_title", "variants", "days", "rounds", "current", "status", "winner", "next_switch")}
            for t in abtest.tests()]


@tool
def ab_test_results(test_id: int) -> dict:
    """Per-version daily views, watch minutes, average view duration and subscribers (YouTube Analytics, ~2-day lag).
    Note: YouTube Studio's built-in Test & Compare is more accurate when available."""
    r = abtest.results(test_id)
    r["test"] = {k: r["test"][k] for k in ("id", "video_title", "status", "current", "winner")}
    return r


@tool
def start_ab_test(url: str, titles: list[str] | None = None, thumbnails: list[str] | None = None, days: int = 1,
                  rounds: int = 2, confirm: bool = False) -> dict:
    """Rotate 1-2 new versions against the current one (version A): titles and/or thumbnail file paths, paired by
    position. Each version stays `days` days; each runs `rounds` times. Suggest YouTube Studio's Test & Compare
    first. Dry run unless confirm=true. 50 units per switched field."""
    titles, thumbnails = titles or [], thumbnails or []
    variants = [{"title": titles[i] if i < len(titles) else None, "thumbnail": thumbnails[i] if i < len(thumbnails) else None}
                for i in range(max(len(titles), len(thumbnails)))]
    if not confirm:
        v = editor.video(url)
        return _dry({"video": v["title"], "A (current)": v["title"], "new_versions": variants, "days": days, "rounds": rounds,
                     "switches": (len(variants) + 1) * rounds}, (len(variants) + 1) * rounds)
    for var in variants:
        if var["thumbnail"]:
            var["thumbnail"] = _image_data_url(var["thumbnail"])
    t = abtest.start(url, variants, days, rounds, source="mcp")
    return {k: t[k] for k in ("id", "video_title", "variants", "days", "next_switch")}


@tool
def finish_ab_test(test_id: int, keep: int | None = None, confirm: bool = False) -> dict:
    """Stop a test (or change the winner after it ended); keep = version index to leave on the video (0 = A).
    Dry run unless confirm=true."""
    if not confirm:
        t = abtest.get(test_id)
        return _dry({"video": t["video_title"], "status": t["status"], "live_now": t["current"], "keep": keep,
                     "versions": t["variants"]}, 1 if keep is not None else 0)
    t = abtest.finish(test_id, keep, source="mcp")
    return {k: t[k] for k in ("id", "status", "winner")}


# ---------- phase 2: playlists ----------

@tool
def my_playlists() -> list[dict]:
    """Your playlists with item counts. 1 unit per 50."""
    return playlists.mine()


@tool
def playlist_videos(playlist_id: str) -> list[dict]:
    """Videos in a playlist in order (item_id, video_id, title, views, published)."""
    return [{k: r[k] for k in ("item_id", "video_id", "title", "position", "views", "published")} for r in playlists.items(playlist_id)]


@tool
def add_to_playlist(playlist_id: str, videos: list[str], confirm: bool = False) -> dict:
    """Add videos (links or ids) to the end of a playlist; ones already in it are skipped.
    Dry run unless confirm=true. 50 units per added video."""
    if not confirm:
        existing = {r["video_id"] for r in playlists.items(playlist_id)}
        ids = [editor.video_id(v) for v in videos]
        new = [v for v in ids if v not in existing]
        return _dry({"add": new, "already_there": [v for v in ids if v in existing]}, len(new))
    return playlists.add(playlist_id, videos, source="mcp")


@tool
def reorder_playlist(playlist_id: str, sort: str = "", order: list[str] | None = None, confirm: bool = False) -> dict:
    """Reorder a playlist: sort = newest | oldest | views | title, or `order` = every item_id in the new order.
    The playlist must be set to manual order in YouTube Studio. Dry run unless confirm=true. 50 units per moved video."""
    if not confirm:
        p = playlists.reorder_preview(playlist_id, sort, order)
        return _dry({"new_order": [r["title"] for r in p["after"]], "moves": p["moves"]}, p["moves"])
    return playlists.reorder(playlist_id, sort, order, source="mcp")


# ---------- phase 2: comment replies ----------

@tool
def unanswered_comments(video: str = "", limit: int = 50) -> list[dict]:
    """Latest comments you haven't replied to, on one video (link) or across the channel. 1 unit.
    Draft replies yourself (short, in the commenter's language, channel voice) and show them to the user."""
    return replies.threads(video, True, limit)


@tool
def canned_replies() -> list[dict]:
    """Saved reply templates ({name} = commenter's name)."""
    return replies.canned()


@tool
def reply_to_comment(comment_id: str, text: str, confirm: bool = False) -> dict:
    """Post a reply under a comment as the channel. Dry run unless confirm=true; only send replies the user
    approved word for word. 50 units."""
    if not confirm:
        return _dry({"comment_id": comment_id, "reply": text}, 1)
    return replies.post(comment_id, text, source="mcp")


if __name__ == "__main__":
    server.run()
