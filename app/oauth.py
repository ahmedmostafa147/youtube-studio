"""Google sign-in for your own channel, using a Desktop-app OAuth client.

Read-only by default. Turning on "editing" in Settings (ALLOW_EDITING=1) adds the youtube.force-ssl scope on the
next sign-in, which lets the studio change titles, descriptions, thumbnails, playlists and post comment replies.
The refresh token is stored in data/google_token.json on this computer only.
"""

import json
import secrets
import time
from urllib.parse import urlencode

import httpx

from . import config, db

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
READ_SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]
WRITE_SCOPE = "https://www.googleapis.com/auth/youtube.force-ssl"
TOKEN_FILE = config.DATA_DIR / "google_token.json"

_pending_states = set()


class AuthError(Exception):
    pass


def has_client():
    return bool(config.get("GOOGLE_CLIENT_ID") and config.get("GOOGLE_CLIENT_SECRET"))


def connected():
    return TOKEN_FILE.exists()


def editing_enabled():
    return config.get("ALLOW_EDITING") == "1"


def scopes():
    return READ_SCOPES + ([WRITE_SCOPE] if editing_enabled() else [])


def granted_scopes():
    if not TOKEN_FILE.exists():
        return []
    return json.loads(TOKEN_FILE.read_text()).get("scope", "").split()


def can_edit():
    """Editing is on in Settings and the saved sign-in actually includes the write scope."""
    return editing_enabled() and WRITE_SCOPE in granted_scopes()


def write_token():
    """Access token for changes on the channel; refuses unless the user opted in and approved the write scope."""
    if not editing_enabled():
        raise AuthError("التعديل على القناة مقفول. فعّله من الإعدادات الأول.")
    if not connected():
        raise AuthError("قناتك مش مربوطة لسه. اربطها من صفحة «قناتي».")
    if WRITE_SCOPE not in granted_scopes():
        raise AuthError("محتاج توافق على صلاحية التعديل: اربط القناة تاني من الإعدادات.")
    return access_token()


def redirect_uri():
    return f"http://127.0.0.1:{config.port()}/auth/callback"


def login_url():
    if not has_client():
        raise AuthError("حط الـ Client ID والـ Client Secret من صفحة الإعدادات الأول.")
    state = secrets.token_urlsafe(16)
    _pending_states.add(state)
    return AUTH_URL + "?" + urlencode({
        "client_id": config.get("GOOGLE_CLIENT_ID"),
        "redirect_uri": redirect_uri(),
        "response_type": "code",
        "scope": " ".join(scopes()),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    })


def handle_callback(code, state):
    if state not in _pending_states:
        raise AuthError("الطلب ده مش جاي من البرنامج. جرّب تربط القناة تاني.")
    _pending_states.discard(state)
    response = httpx.post(TOKEN_URL, data={
        "code": code,
        "client_id": config.get("GOOGLE_CLIENT_ID"),
        "client_secret": config.get("GOOGLE_CLIENT_SECRET"),
        "redirect_uri": redirect_uri(),
        "grant_type": "authorization_code",
    }, timeout=20)
    if response.status_code != 200:
        raise AuthError(f"جوجل رفضت تسجيل الدخول: {response.text[:200]}")
    _save(response.json())


def _save(token):
    previous = json.loads(TOKEN_FILE.read_text()) if TOKEN_FILE.exists() else {}
    data = {
        "access_token": token["access_token"],
        # Google only sends a refresh token on the first consent; keep the old one on refresh.
        "refresh_token": token.get("refresh_token") or previous.get("refresh_token"),
        "expires_at": time.time() + int(token.get("expires_in", 3600)),
        # Which permissions the user actually approved (refresh responses repeat them).
        "scope": token.get("scope") or previous.get("scope", ""),
    }
    TOKEN_FILE.write_text(json.dumps(data))


def access_token():
    if not TOKEN_FILE.exists():
        raise AuthError("قناتك مش مربوطة لسه.")
    data = json.loads(TOKEN_FILE.read_text())
    if data["expires_at"] - 60 > time.time():
        return data["access_token"]
    response = httpx.post(TOKEN_URL, data={
        "refresh_token": data["refresh_token"],
        "client_id": config.get("GOOGLE_CLIENT_ID"),
        "client_secret": config.get("GOOGLE_CLIENT_SECRET"),
        "grant_type": "refresh_token",
    }, timeout=20)
    if response.status_code != 200:
        # invalid_grant: revoked, or the 7-day limit of an OAuth app still in "Testing" mode.
        TOKEN_FILE.unlink(missing_ok=True)
        raise AuthError("انتهت صلاحية ربط القناة. اربطها تاني.")
    _save(response.json())
    return json.loads(TOKEN_FILE.read_text())["access_token"]


def logout():
    if TOKEN_FILE.exists():
        data = json.loads(TOKEN_FILE.read_text())
        try:
            httpx.post(REVOKE_URL, data={"token": data.get("refresh_token") or data["access_token"]}, timeout=10)
        except httpx.HTTPError:
            pass
        TOKEN_FILE.unlink(missing_ok=True)
    db.cache_clear("an:")
