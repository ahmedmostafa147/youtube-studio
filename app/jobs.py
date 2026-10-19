"""Background work while the dashboard is running: refresh competitors, record hourly views, raise alerts,
and (Phase 2) run scheduled changes, rotate A/B tests, track search ranks and brand mentions.

Each run costs about 3 quota units per competitor + 3 for trends + 3 for your channel. Once a day, rank tracking
costs 100 units per keyword and brand alerts 100 units when they are on. Scheduled changes and A/B switches cost
50 units per change.
"""

import threading
import time
import traceback

from . import abtest, competitors, config, db, mychannel, oauth, ranks, schedule, trends

INTERVAL = 3600
_lock = threading.Lock()


def run_once():
    has_key, can_edit = bool(config.get("YOUTUBE_API_KEY")), oauth.can_edit()
    if not has_key and not can_edit:
        return {"skipped": "no API key"}
    if not _lock.acquire(blocking=False):
        return {"skipped": "already running"}
    report = {"started": time.time()}
    try:
        steps = []
        if can_edit:
            # Changes on your channel first, so they happen on time even if a later step runs out of quota.
            steps += [("scheduled", schedule.run_due), ("ab_tests", abtest.tick)]
        if has_key:
            steps += [
                ("competitors", competitors.refresh_all),
                ("takeoffs", competitors.check_takeoffs),
                ("trends", trends.check_alerts),
                ("ranks", ranks.check_ranks),
                ("brand", ranks.brand_check),
            ]
        if has_key and config.get("MY_CHANNEL_ID"):
            steps.append(("my_channel", lambda: len(mychannel.recent()["videos"])))
        for name, fn in steps:
            try:
                report[name] = fn()
            except Exception as e:  # one failing step (quota, network) must not stop the others
                report[name] = f"error: {e}"
                traceback.print_exc()
        report["finished"] = time.time()
        db.cache_set("jobs:last", report)
        return report
    finally:
        _lock.release()


def last_run():
    return db.cache_get("jobs:last", 10 * 365 * 86400)


def _loop():
    while True:
        last = last_run()
        wait = INTERVAL - (time.time() - last["started"]) if last and "started" in last else 0
        if wait > 0:
            time.sleep(wait)
        if "skipped" in run_once():
            # No key yet (or a manual run in progress): check again in a few minutes.
            time.sleep(300)


def start():
    threading.Thread(target=_loop, daemon=True, name="studio-jobs").start()
