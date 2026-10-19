"""Phase 2 checks on fake data: python tests/run_phase2.py (from the studio folder, with the .venv Python).

Covers the dashboard API and the MCP tools for editing, schedules, ranks, A/B rotation, playlists and replies,
including the safety rails: read-only by default, write scope required, dry runs without confirm.
"""

import base64
import time
import warnings
from datetime import datetime, timedelta

warnings.filterwarnings("ignore")
import fake_setup as fake  # noqa: E402  (patches the app before it is imported)
from fastapi.testclient import TestClient  # noqa: E402

from app import config, db, jobs, main  # noqa: E402

c = TestClient(main.app)
passed = failed = 0
MY = fake.MINE  # ids of videos on the fake "my channel"
PNG = "data:image/png;base64," + base64.b64encode(b"\x89PNG fake thumbnail").decode()


def check(name, condition, detail=""):
    global passed, failed
    passed += bool(condition)
    failed += not condition
    print("OK  " if condition else "FAIL", name, "" if condition else str(detail)[:400])


def call(method, path, expect=200, **kw):
    r = getattr(c, method)(path, **kw)
    if r.status_code != expect:
        check(f"{method.upper()} {path} -> {expect}", False, f"{r.status_code} {r.text[:300]}")
    try:
        return r.json()
    except ValueError:
        return r.text


def writes():
    return len(fake.WRITES)


def local_time(minutes):
    return (datetime.now(config.tz()) + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M")


# ---------- the gate: read-only by default ----------
st = call("get", "/api/status")
check("editing is off by default", st["editing"] == {**st["editing"], "enabled": False, "can_edit": False}, st["editing"])
import app.oauth as oauth  # noqa: E402
check("login asks for read scopes only by default", oauth.WRITE_SCOPE not in oauth.scopes())

body = {"field": "description", "mode": "replace", "find": "https://old.example/course", "replace": "https://new.example/course"}
prev = call("post", "/api/bulk/preview", json=body)
targets = [m["id"] for m in prev["matches"]]
check("bulk preview works read-only and finds the old link", len(targets) >= 5 and all(v in MY for v in targets), prev.get("matches", [])[:1])
check("preview excerpts show before and after", "old.example" in prev["matches"][0]["excerpts"][0]["before"]
      and "new.example" in prev["matches"][0]["excerpts"][0]["after"], prev["matches"][0]["excerpts"])
check("preview cost is 50 per video", prev["cost"] == 50 * len(targets), prev["cost"])

r = c.post("/api/bulk/apply", json={**body, "videos": targets[:2]})
check("apply refused while editing is off (401)", r.status_code == 401 and writes() == 0, r.text)

call("post", "/api/settings", json={"allow_editing": True})
check("enabling editing adds the write scope to the next login", oauth.WRITE_SCOPE in oauth.scopes())
st = call("get", "/api/status")
check("enabled but not approved yet -> can_edit false", st["editing"]["enabled"] and not st["editing"]["can_edit"], st["editing"])
r = c.post("/api/bulk/apply", json={**body, "videos": targets[:2]})
check("apply refused until the write scope is approved", r.status_code == 401 and "اربط" in r.json()["error"] and writes() == 0, r.text)

fake.link_channel(write_scope=True)
check("can_edit after re-linking with the write scope", call("get", "/api/status")["editing"]["can_edit"])

# ---------- bulk edit ----------
pick = targets[:2]
before_tags = {v: list(fake.VIDS[v]["snippet"].get("tags", [])) for v in pick}
untouched = targets[2]
q0 = db.quota_used()
res = call("post", "/api/bulk/apply", json={**body, "videos": pick})
check("bulk apply changed only the ticked videos", res.get("done") == 2 and writes() == 2, res)
check("description replaced", all("new.example" in fake.VIDS[v]["snippet"]["description"] for v in pick))
check("unticked video untouched", "old.example" in fake.VIDS[untouched]["snippet"]["description"])
check("tags and category kept (full snippet sent)", all(fake.VIDS[v]["snippet"].get("tags", []) == before_tags[v]
                                                     and fake.VIDS[v]["snippet"]["categoryId"] == "28" for v in pick))
check("quota: 1 read + 2 x 50", db.quota_used() - q0 == 101, db.quota_used() - q0)
res = call("post", "/api/bulk/apply", json={**body, "videos": pick})
check("re-applying skips already changed videos", res["done"] == 0 and all(x["status"] == "skipped" for x in res["results"]), res)

app_body = {"field": "description", "mode": "append", "replace": "كورس Claude Code الجديد: https://new.example"}
prev = call("post", "/api/bulk/preview", json={**app_body, "videos": MY[:3]})
check("append preview over chosen videos", len(prev["matches"]) == 3, prev)
call("post", "/api/bulk/apply", json={**app_body, "videos": MY[:1]})
prev = call("post", "/api/bulk/preview", json={**app_body, "videos": MY[:3]})
check("append is skipped where the text is already there", len(prev["matches"]) == 2, len(prev["matches"]))
long = call("post", "/api/bulk/preview", json={"field": "title", "mode": "append", "replace": "x" * 100, "videos": MY[:1]})
check("too-long title is flagged in preview", long["matches"][0]["problems"], long)
r = c.post("/api/bulk/apply", json={"field": "title", "mode": "append", "replace": "x" * 100, "videos": MY[:1]})
check("too-long title is not written", r.json()["results"][0]["status"] == "failed", r.text)

hist = call("get", "/api/edit/history")
check("edit log records changes with undo", hist and hist[0]["can_undo"] and hist[0]["action"] == "snippet", hist[:1])
undo_target = next(h for h in hist if h["video_id"] == pick[0] and "old.example" in (h["before"]["description"] or ""))
call("post", f"/api/edit/undo/{undo_target['id']}")
check("undo restores the old description", "old.example" in fake.VIDS[pick[0]]["snippet"]["description"])

# ---------- upload profiles ----------
call("post", "/api/profiles", json={"name": "شروحات", "title": "{title} | شرح بالعربي", "description": "{description}\n\nتابعني على X",
                                     "tags": ["claude", "شرح بالعربي"], "tags_mode": "append", "category_id": "27"})
check("profile saved", call("get", "/api/profiles")[0]["tags"] == ["claude", "شرح بالعربي"])
target = MY[3]
old_title = fake.VIDS[target]["snippet"]["title"]
n0 = writes()
pv = call("post", "/api/profiles/preview", json={"name": "شروحات", "url": target})
check("profile preview renders {title} and merges tags", pv["after"]["title"] == old_title + " | شرح بالعربي"
      and pv["after"]["tags"].count("claude") == 1 and "شرح بالعربي" in pv["after"]["tags"] and writes() == n0, pv["after"])
call("post", "/api/profiles/apply", json={"name": "شروحات", "url": target})
check("profile applied", fake.VIDS[target]["snippet"]["title"].endswith("| شرح بالعربي") and fake.VIDS[target]["snippet"]["categoryId"] == "27")
r = c.post("/api/profiles/preview", json={"name": "شروحات", "url": "vid00000000"})
check("someone else's video is refused", r.status_code == 400, r.text)

# ---------- translations ----------
tr = call("post", "/api/translate", json={"url": MY[4], "languages": ["en", "fr", "ar"]})
check("AI translation skips the video's own language", sorted(tr["translations"]) == ["en", "fr"], tr.get("translations"))
check("< and > are removed from AI descriptions", "<" not in tr["translations"]["en"]["description"])
call("post", "/api/localizations", json={"url": MY[4], "translations": tr["translations"]})
v = fake.VIDS[MY[4]]
check("localizations saved and default language set", sorted(v["localizations"]) == ["en", "fr"] and v["snippet"]["defaultLanguage"] == "ar", v.get("localizations"))
call("post", "/api/localizations", json={"url": MY[4], "translations": {"de": {"title": "Anleitung", "description": ""}}})
check("adding a language keeps the others", sorted(fake.VIDS[MY[4]]["localizations"]) == ["de", "en", "fr"])

# ---------- scheduled changes ----------
r = c.post("/api/schedule", json={"url": MY[5], "kind": "title", "value": "عنوان قديم", "when": local_time(-30)})
check("schedule in the past refused", r.status_code == 400, r.text)
s1 = call("post", "/api/schedule", json={"url": MY[5], "kind": "title", "value": "عنوان مجدول جديد", "when": local_time(5)})
s2 = call("post", "/api/schedule", json={"url": MY[6], "kind": "privacy", "value": "unlisted", "when": local_time(5)})
s3 = call("post", "/api/schedule", json={"url": MY[6], "kind": "thumbnail", "value": PNG, "when": local_time(5)})
s4 = call("post", "/api/schedule", json={"url": MY[7], "kind": "description", "value": "مش هيتنفذ", "when": local_time(5)})
call("delete", f"/api/schedule/{s4['id']}")
n0 = writes()
jobs.run_once()
check("nothing runs before its time", writes() == n0 and call("get", "/api/schedule")[0]["status"] == "pending")
db.execute("UPDATE scheduled SET run_at = ? WHERE status = 'pending'", (time.time() - 10,))
fake.VIDS[MY[6]]["status"]["publishAt"] = "2027-01-01T00:00:00Z"
rep = jobs.run_once()
rows = {r["id"]: r for r in call("get", "/api/schedule")}
check("hourly job ran the due changes", rep.get("scheduled") == 3 and all(rows[s["id"]]["status"] == "done" for s in (s1, s2, s3)), (rep, rows))
check("title changed on schedule", fake.VIDS[MY[5]]["snippet"]["title"] == "عنوان مجدول جديد")
check("sunset: video unlisted and publishAt dropped", fake.VIDS[MY[6]]["status"]["privacyStatus"] == "unlisted" and "publishAt" not in fake.WRITES[-2]["body"]["status"],
      fake.WRITES[-2])
check("thumbnail uploaded as bytes", any(w["endpoint"] == "thumbnails/set" and w["bytes"] > 0 for w in fake.WRITES))
check("cancelled change did not run", rows[s4["id"]]["status"] == "cancelled" and fake.VIDS[MY[7]]["snippet"]["description"] != "مش هيتنفذ")
check("scheduled changes raise alerts", any(a["kind"] == "scheduled" for a in call("get", "/api/alerts")))

# ---------- search ranks ----------
q0 = db.quota_used()
tags = call("post", "/api/ranks/tags", json={"url": MY[0], "tags": ["claude", "شرح claude", "ai"], "limit": 2})
check("tag rankings respect the limit and find the video", len(tags["rows"]) == 2 and tags["rows"][0]["rank"] == 6 and tags["cost"] == 200, tags)
check("tag rankings cost 100 per tag (+1 for the video)", db.quota_used() - q0 == 201, db.quota_used() - q0)
call("post", "/api/ranks", json={"keyword": "شرح claude"})
call("post", "/api/ranks", json={"keyword": "claude code", "url": MY[2]})
r = c.post("/api/ranks", json={"keyword": "كلمة تالتة"})
check("keyword cap from settings is enforced", r.status_code == 400 and "200" in r.json()["error"], r.text)
rk = call("post", "/api/ranks/check")
check("daily rank check records ranks", rk["checked"] == 2 and rk["keywords"][0]["latest"]["rank"] == 6 and rk["keywords"][1]["latest"]["rank"] == 18, rk["keywords"])
check("daily cost shown", rk["daily_cost"] == 200 and rk["max"] == 2, rk)
q0 = db.quota_used()
rk = call("post", "/api/ranks/check")
check("second check the same day is free", rk["checked"] == 0 and db.quota_used() == q0)
check("job skips brand search while it is off", jobs.run_once().get("brand") == "off")
br = call("post", "/api/brand/check")
brand = [a for a in call("get", "/api/alerts") if a["kind"] == "brand"]
check("brand check alerts on other channels only", br["found"] > 0 and brand and all(fake.MY_CHANNEL not in a["url"] for a in brand)
      and not any(m in a["url"] for a in brand for m in MY), br)

# ---------- A/B rotation ----------
ab_video = MY[8]
original = fake.VIDS[ab_video]["snippet"]["title"]
r = c.post("/api/ab", json={"url": ab_video, "variants": [], "days": 1})
check("A/B needs at least one new version", r.status_code == 400)
t = call("post", "/api/ab", json={"url": ab_video, "variants": [{"title": "عنوان B"}, {"title": None, "thumbnail": PNG}], "days": 1, "rounds": 1})
check("A/B started with A = current title and a saved copy of the current thumbnail", t["variants"][0]["title"] == original
      and t["variants"][0]["thumbnail"] and t["variants"][2]["title"] == original, t.get("variants"))
r = c.post("/api/ab", json={"url": ab_video, "variants": [{"title": "تاني"}]})
check("one running test per video", r.status_code == 400)


def age_test(days):
    shift = days * 86400
    db.execute("UPDATE ab_tests SET started = started - ?, last_switch = last_switch - ?", (shift, shift))
    db.execute("UPDATE ab_periods SET start = start - ?, end = CASE WHEN end IS NULL THEN NULL ELSE end - ? END", (shift, shift))


n0 = writes()
jobs.run_once()
check("no switch before the period ends", writes() == n0)
age_test(1)
jobs.run_once()
check("switched to B (title only)", fake.VIDS[ab_video]["snippet"]["title"] == "عنوان B" and writes() == n0 + 1, fake.WRITES[n0:])
age_test(1)
jobs.run_once()
check("switched to C (title back to A, new thumbnail)", fake.VIDS[ab_video]["snippet"]["title"] == original
      and fake.WRITES[-1]["endpoint"] == "thumbnails/set", fake.WRITES[n0:])
age_test(4)
jobs.run_once()
test = call("get", "/api/ab")[0]
check("after every version had its rounds, the test ends on A", test["status"] == "done" and test["winner"] == 0
      and fake.WRITES[-1]["endpoint"] == "thumbnails/set", test)
# Real switches land just after Pacific midnight; lay the periods out that way to check the day split:
# A owns 2 whole days, B one, C two; the half hour of C on the last day is too little to count.
from app import abtest  # noqa: E402
day0 = datetime.now(db.PACIFIC).date() - timedelta(days=8)
mid = lambda n: datetime(day0.year, day0.month, day0.day, tzinfo=db.PACIFIC).timestamp() + n * 86400 + 1800  # noqa: E731
db.execute("UPDATE ab_tests SET started = ? WHERE id = ?", (mid(0), test["id"]))
db.execute("DELETE FROM ab_periods WHERE test_id = ?", (test["id"],))
for variant, a, b in [(0, 0, 2), (1, 2, 3), (2, 3, 5)]:
    db.execute("INSERT INTO ab_periods (test_id, variant, start, end) VALUES (?, ?, ?, ?)", (test["id"], variant, mid(a), mid(b)))
check("switch time is the Pacific midnight after the period", datetime.fromtimestamp(abtest.next_switch(mid(0), 1), db.PACIFIC).hour == 0)
res = call("get", f"/api/ab/{test['id']}")
check("results split analytics days per version", sum(v["days"] for v in res["versions"]) == res["days_counted"] > 0
      and [v["days"] for v in res["versions"]] == [2, 1, 2] and res["leader"] in (0, 1, 2), [(v["index"], v["days"]) for v in res["versions"]])
call("post", f"/api/ab/{test['id']}/finish", json={"keep": 1})
check("choosing a winner after the test puts it on the video", fake.VIDS[ab_video]["snippet"]["title"] == "عنوان B"
      and call("get", "/api/ab")[0]["winner"] == 1)
check("thumbnail files are served", c.get(f"/api/thumbs/{t['variants'][2]['thumbnail']}").status_code == 200
      and c.get("/api/thumbs/..%2F.env").status_code in (400, 404))

# ---------- playlists ----------
pls = call("get", "/api/playlists")
check("playlists listed", pls[0]["id"] == "PLtest")
items = call("get", "/api/playlists/PLtest")
check("playlist items with views", len(items) == 5 and "views" in items[0])
n0 = writes()
res = call("post", "/api/playlists/PLtest/add", json={"videos": [MY[0], MY[9], f"https://youtu.be/{MY[10]}"]})
check("add skips videos already in the playlist", res["done"] == 2 and writes() == n0 + 2, res)
pv = call("post", "/api/playlists/PLtest/reorder/preview", json={"sort": "views"})
views = [r["views"] for r in pv["after"]]
check("reorder preview sorts by views and counts moves", views == sorted(views, reverse=True) and pv["cost"] == 50 * pv["moves"], pv["moves"])
call("post", "/api/playlists/PLtest/reorder", json={"sort": "views"})
after = [r["views"] for r in call("get", "/api/playlists/PLtest")]
check("playlist order applied", after == sorted(after, reverse=True), after)
r = c.post("/api/playlists/PLtest/reorder", json={"order": ["PLI0"]})
check("partial manual order refused", r.status_code == 400)

# ---------- replies ----------
th = call("get", "/api/replies/threads")
check("only unanswered comments, own comments hidden", th and all(not x["answered"] for x in th) and not any(x["comment_id"] == "cm7" for x in th)
      and not any(x["comment_id"] == "cm0" for x in th), [x["comment_id"] for x in th])
call("post", "/api/replies/canned", json={"name": "شكر", "text": "شكرًا يا {name}!"})
check("canned reply saved", call("get", "/api/replies/canned")[0]["name"] == "شكر")
n0 = writes()
dr = call("post", "/api/replies/drafts", json={"comments": [{"comment_id": x["comment_id"], "text": x["text"], "author": x["author"]} for x in th[:3]]})
check("AI drafts keyed by comment id, nothing posted", sorted(dr["replies"]) == sorted(x["comment_id"] for x in th[:3]) and writes() == n0, dr)
pr = call("post", "/api/replies/post", json={"comment_id": th[0]["comment_id"], "text": "شكرًا!"})
check("reply posted on click", pr["posted"] and fake.WRITES[-1]["endpoint"] == "comments" and fake.WRITES[-1]["body"]["snippet"]["parentId"] == th[0]["comment_id"])

# ---------- MCP: previews are free, writes need confirm ----------
import mcp_server as m  # noqa: E402

n0 = writes()
d = m.edit_video(MY[11], title="عنوان من Claude Code")
check("MCP edit_video without confirm is a dry run", d["confirmed"] is False and d["quota_cost"] == 50 and writes() == n0, d)
m.edit_video(MY[11], title="عنوان من Claude Code", confirm=True)
check("MCP edit_video with confirm writes", fake.VIDS[MY[11]]["snippet"]["title"] == "عنوان من Claude Code" and writes() == n0 + 1)
p = m.bulk_edit_preview(find="وصف قصير", replace="وصف")
d = m.bulk_edit_apply([p["matches"][0]["id"]], find="وصف قصير", replace="وصف")
check("MCP bulk_edit_apply dry run", d["confirmed"] is False and writes() == n0 + 1, d)
for name, fn in [("save_localizations", lambda: m.save_localizations(MY[12], {"en": {"title": "Hi", "description": ""}})),
                 ("schedule_change", lambda: m.schedule_change(MY[12], "privacy", "unlisted", local_time(60))),
                 ("start_ab_test", lambda: m.start_ab_test(MY[12], titles=["B"])),
                 ("add_to_playlist", lambda: m.add_to_playlist("PLtest", [MY[13]])),
                 ("reorder_playlist", lambda: m.reorder_playlist("PLtest", sort="title")),
                 ("reply_to_comment", lambda: m.reply_to_comment("cm1", "شكرا")),
                 ("apply_upload_profile", lambda: m.apply_upload_profile("شروحات", MY[12])),
                 ("undo_edit", lambda: m.undo_edit(m.edit_history(1)[0]["id"]))]:
    out = fn()
    check(f"MCP {name} without confirm changes nothing", out["confirmed"] is False and writes() == n0 + 1
          and not db.query("SELECT 1 FROM scheduled WHERE video_id = ? AND status = 'pending'", (MY[12],)), out)
check("MCP read tools", m.editing_status()["can_edit"] and m.tracked_keywords()["daily_cost"] == 200 and m.my_playlists()
      and m.unanswered_comments() and m.video_details(MY[4])["localizations"])
r = m.reply_to_comment("cm1", "شكرا", confirm=True)
check("MCP reply with confirm posts", r["posted"] and writes() == n0 + 2)

# ---------- turning editing off stops every write ----------
call("post", "/api/settings", json={"allow_editing": False})
r = c.post("/api/edit/video", json={"url": MY[0], "title": "x"})
check("disabling editing blocks writes again", r.status_code == 401 and writes() == n0 + 2, r.text)
check("job skips scheduled changes when editing is off", "scheduled" not in jobs.run_once())

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
