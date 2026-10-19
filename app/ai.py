"""AI writing for the dashboard through the Claude API (needs ANTHROPIC_API_KEY in settings).

Inside Claude Code none of this is needed: Claude writes the titles itself using the MCP data tools.
"""

import json
import re

import anthropic

from . import config, seo

MODEL = "claude-opus-5-5"
# Price per million tokens for MODEL, used to show what each request cost.
PRICE_IN, PRICE_OUT = 4.00, 20.00

DEFAULT_VOICE = (
    "اكتب بالعربي البسيط اللي جمهور القناة بيفهمه. أسماء الأدوات والمصطلحات بالإنجليزي زي ما هي، والأرقام إنجليزي. "
    "ممنوع التهويل وكلمات زي «صدمة» و«لن تصدق». مفيش إيموجي في العناوين."
)

SYSTEM = """You help a YouTube creator plan and package videos.
Ground every suggestion in the data you are given and never invent statistics.
Write all creator-facing text (titles, descriptions, scripts, explanations) following the channel voice below.

CHANNEL VOICE:
{voice}"""


class AIError(Exception):
    pass


def available():
    return bool(config.get("ANTHROPIC_API_KEY"))


def _client():
    key = config.get("ANTHROPIC_API_KEY")
    if not key:
        raise AIError("مفيش Claude API key. حطه من الإعدادات، أو استخدم الميزة دي ببلاش من Claude Code.")
    return anthropic.Anthropic(api_key=key)


def _ask(content, schema, effort="medium"):
    """One structured request; returns (parsed JSON, usage info)."""
    system = SYSTEM.format(voice=config.get("CHANNEL_VOICE") or DEFAULT_VOICE)
    try:
        response = _client().beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            system=system,
            messages=[{"role": "user", "content": content}],
            output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
            # If a safety classifier declines, the API retries on Anthropic's recommended fallback model.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
    except anthropic.AuthenticationError as e:
        raise AIError("الـ Claude API key مش صح. راجعه من الإعدادات.") from e
    except anthropic.PermissionDeniedError as e:
        raise AIError("المفتاح ده مش مسموحله يستخدم الموديل. راجع حسابك على console.anthropic.com.") from e
    except anthropic.RateLimitError as e:
        raise AIError("طلبات كتير ورا بعض. استنى دقيقة وجرّب تاني.") from e
    except anthropic.APIStatusError as e:
        if e.status_code == 400 and "credit" in str(e.message).lower():
            raise AIError("رصيد حساب Claude API خلص. اشحنه من console.anthropic.com.") from e
        raise AIError(f"Claude API رد بخطأ {e.status_code}: {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise AIError("مش قادر أوصل لـ Claude. اتأكد إن النت شغال.") from e

    if response.stop_reason == "refusal":
        raise AIError("Claude رفض الطلب ده. جرّب تصيغه بشكل تاني.")
    if response.stop_reason == "max_tokens":
        raise AIError("الرد طلع أطول من المسموح. قلّل المدخلات وجرّب تاني.")
    text = next((b.text for b in response.content if b.type == "text"), "")
    usage = response.usage
    cost = usage.input_tokens / 1e6 * PRICE_IN + usage.output_tokens / 1e6 * PRICE_OUT
    return json.loads(text), {"input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens, "cost_usd": round(cost, 4)}


def _obj(properties, required=None):
    return {"type": "object", "properties": properties, "required": required or list(properties), "additionalProperties": False}


STR = {"type": "string"}
STRS = {"type": "array", "items": STR}


def _lines(title, items):
    return f"{title}:\n" + ("\n".join(f"- {i}" for i in items) if items else "(none)")


# ---------- writing ----------

def titles(topic, keyword="", notes="", reference_titles=(), count=10):
    schema = _obj({"titles": {"type": "array", "items": _obj({"title": STR, "angle": STR, "why": STR})}})
    prompt = f"""Write {count} YouTube title options for this video.

Topic: {topic}
Target search phrase: {keyword or "(none given)"}
Notes from the creator: {notes or "(none)"}

{_lines("Titles already ranking or performing in this space (be different, not a copy)", reference_titles)}

Rules: under 70 characters; put the target phrase early and exactly when one is given; each option takes a different angle
(how-to, comparison, result, mistake, question, list...). `angle` names the angle in 2-4 words, `why` says in one sentence why it would get clicks."""
    data, usage = _ask(prompt, schema)
    for t in data["titles"]:
        t["length"] = len(t["title"])
        t["seo_score"] = seo.title_score(t["title"], keyword)
    data["titles"].sort(key=lambda t: t["seo_score"], reverse=True)
    return {**data, "usage": usage}


def description(title, keyword="", notes="", transcript=""):
    schema = _obj({"description": STR, "hashtags": STRS, "tags": STRS})
    prompt = f"""Write the YouTube description, hashtags and tags for this video.

Title: {title}
Target search phrase: {keyword or "(none given)"}
Notes from the creator: {notes or "(none)"}
Transcript (may be empty): {transcript[:60000] or "(none)"}

Rules: the first 150 characters say what the viewer gets and include the target phrase; 250-1000 characters in total;
mention the phrase 2-4 times naturally; add chapters (first one at 0:00, at least 3) only if the transcript has timestamps;
1-3 hashtags; 8-15 tags under 450 characters total, the exact target phrase first."""
    data, usage = _ask(prompt, schema)
    body = data["description"].rstrip()
    if data["hashtags"]:
        body += "\n\n" + " ".join(h if h.startswith("#") else "#" + h.replace(" ", "") for h in data["hashtags"])
    data["full_description"] = body
    data["seo"] = seo.score(title, body, data["tags"], keyword)
    return {**data, "usage": usage}


def script(topic, keyword="", minutes=8, notes=""):
    section = _obj({"heading": STR, "talking_points": STRS, "seconds": {"type": "integer"}})
    schema = _obj({"hook": STR, "intro": STR, "sections": {"type": "array", "items": section}, "outro": STR})
    prompt = f"""Write a video script outline for a ~{minutes}-minute YouTube video.

Topic: {topic}
Target search phrase: {keyword or "(none given)"}
Notes from the creator: {notes or "(none)"}

The hook is the first 15 seconds, spoken word for word, and must make the viewer stay. Sections carry concrete talking points
(not generic filler) and an estimated duration in seconds; the durations add up to roughly the target length."""
    data, usage = _ask(prompt, schema)
    return {**data, "usage": usage}


TIME = re.compile(r"^(?:(\d+):)?(\d{1,2}):(\d{2})$")


def _seconds(stamp):
    m = TIME.match(stamp.strip())
    if not m:
        return None
    h, mi, s = (int(x or 0) for x in m.groups())
    return h * 3600 + mi * 60 + s


def _stamp(sec):
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def chapters(transcript):
    """Chapters from a transcript with timestamps (an .srt from scribe.py works)."""
    if not transcript.strip():
        raise AIError("حط الترانسكريبت الأول (ملف .srt فيه توقيتات).")
    schema = _obj({"chapters": {"type": "array", "items": _obj({"start": STR, "title": STR})}})
    prompt = f"""Split this video into YouTube chapters using the transcript timestamps.

Rules: the first chapter starts at 0:00; 4-10 chapters; each at least 30 seconds long; titles are 2-6 words that a viewer
would scan for; `start` is m:ss or h:mm:ss taken from the transcript.

Transcript:
{transcript[:200000]}"""
    data, usage = _ask(prompt, schema)
    # Make the list valid for YouTube: sorted, unique, starting at 0:00, at least 10 seconds apart.
    rows = sorted((s, c["title"].strip()) for c in data["chapters"] if (s := _seconds(c["start"])) is not None)
    clean = []
    for sec, title in rows:
        if clean and sec - clean[-1][0] < 10:
            continue
        clean.append((sec, title))
    if clean:
        clean[0] = (0, clean[0][1])
    lines = [f"{_stamp(s)} {t}" for s, t in clean]
    return {"chapters": [{"start": _stamp(s), "title": t} for s, t in clean], "text": "\n".join(lines), "usage": usage}


def daily_ideas(signals, count=10):
    idea = _obj({"title": STR, "keyword": STR, "why": STR, "based_on": STR})
    schema = _obj({"ideas": {"type": "array", "items": idea}})
    prompt = f"""Suggest {count} video ideas for this channel today, as titles ready to use.

Use only these signals; `based_on` names which one each idea comes from, `why` explains the opportunity in one sentence,
`keyword` is the search phrase to target. Skip anything already in the creator's planner.

{json.dumps(signals, ensure_ascii=False, indent=1)}"""
    data, usage = _ask(prompt, schema)
    return {**data, "usage": usage}


def review_thumbnail(image_b64, media_type, title="", keyword=""):
    schema = _obj({
        "score": {"type": "integer"}, "verdict": STR, "readable_small": {"type": "boolean"},
        "words_on_image": {"type": "integer"}, "focal_point": STR,
        "strengths": STRS, "issues": STRS, "suggestions": STRS,
    })
    rules = config.get("THUMBNAIL_RULES") or "(no channel-specific rules)"
    content = [
        {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_b64}},
        {"type": "text", "text": f"""Review this YouTube thumbnail as it would appear among other videos in search and on the home feed.

Video title: {title or "(not given)"}
Target search phrase: {keyword or "(not given)"}
Channel thumbnail rules: {rules}

Score 0-100 for click potential. Judge: is there one clear focal point; is any text readable at 160px wide; does the image add
to the title instead of repeating it; contrast; clutter; and the channel rules. Give at most 4 items per list, concrete and actionable."""},
    ]
    data, usage = _ask(content, schema)
    data["score"] = max(0, min(100, data["score"]))
    return {**data, "usage": usage}


def summarize_comments(video_title, comments):
    schema = _obj({
        "summary": STR,
        "sentiment": _obj({"positive": {"type": "integer"}, "neutral": {"type": "integer"}, "negative": {"type": "integer"}}),
        "requests": STRS, "questions": STRS, "video_ideas": STRS,
    })
    text = "\n".join(f"- ({c['likes']} likes) {c['text'][:500]}" for c in comments[:300])
    prompt = f"""Summarize what viewers say under this video.

Video: {video_title}
Comments:
{text}

`sentiment` is a percentage split adding up to 100. `requests` are things viewers ask the creator to make or change,
`questions` are recurring questions worth answering, `video_ideas` are follow-up videos these comments suggest. At most 6 per list."""
    data, usage = _ask(prompt, schema)
    return {**data, "usage": usage}
