"""Background work while the dashboard is running: refresh competitors, record hourly views, raise alerts.

Each run costs about 3 quota units per competitor + 3 for trends + 3 for your channel.
"""

import threading
import time
import traceback

from . import competitors, config, db, mychannel, trends

INTERVAL = 3600
_lock = threading.Lock()


def run_once():
    if not config.get("YOUTUBE_API_KEY"):
        return {"skipped": "no API key"}
    if not _lock.acquire(blocking=False):
        return {"skipped": "already running"}
    report = {"started": time.time()}
    try:
        steps = [
            ("competitors", competitors.refresh_all),
            ("takeoffs", competitors.check_takeoffs),
            ("trends", trends.check_alerts),
        ]
        if config.get("MY_CHANNEL_ID"):
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
