"""Start the studio on http://127.0.0.1:8765 and open it in the browser."""

import threading
import webbrowser

import uvicorn

from app import config

if __name__ == "__main__":
    url = f"http://127.0.0.1:{config.port()}"
    threading.Timer(1.5, webbrowser.open, [url]).start()
    print(f"Studio running at {url}  (close this window to stop)")
    uvicorn.run("app.main:app", host="127.0.0.1", port=config.port())
