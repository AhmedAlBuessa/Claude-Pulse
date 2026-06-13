"""Live plan-usage from Anthropic's OAuth usage endpoint.

Claude Code shows your real session usage by calling /api/oauth/usage with the
OAuth token Claude Code stores after you log in. We do the exact same thing so
the dashboard matches `claude` and claude.ai/usage — no manual calibration.

Credential storage differs by platform:
  - macOS:          the system Keychain (service "Claude Code-credentials")
  - Windows/Linux:  ~/.claude/.credentials.json (plaintext JSON)

Everything here fails soft: any problem yields a reason code and callers fall
back to the local estimate instead of crashing.
"""

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request

from claude_pulse.config import CLAUDE_DIR

CREDENTIALS_PATH = CLAUDE_DIR / ".credentials.json"
KEYCHAIN_SERVICE = "Claude Code-credentials"
OAUTH_USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
OAUTH_BETA = "oauth-2025-04-20"

# Cache so a sub-second UI refresh doesn't hammer the API.
_CACHE_TTL = 60.0
_cache: dict = {"at": 0.0, "data": None}

# Reason codes used by get_usage_status() / the --check-usage diagnostic.
REASONS = {
    "ok": "Live usage is working.",
    "no_creds": "No Claude credentials found — log in by running `claude` once.",
    "no_oauth": "Credentials found but no subscription token (API-key login has no session limits).",
    "expired": "Your login token expired — run `claude` once to refresh it.",
    "network": "Couldn't reach api.anthropic.com (offline, or the endpoint changed).",
}


def _credentials_source() -> str:
    """Human description of where credentials are read from on this platform."""
    if sys.platform == "darwin":
        return f"macOS Keychain ({KEYCHAIN_SERVICE})"
    return str(CREDENTIALS_PATH)


def _load_raw_credentials() -> dict | None:
    """Load and parse the raw credentials blob from the platform's store."""
    if sys.platform == "darwin":
        try:
            out = subprocess.run(
                ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
                capture_output=True, text=True, timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if out.returncode != 0 or not out.stdout.strip():
            return None
        blob = out.stdout.strip()
    else:
        try:
            blob = CREDENTIALS_PATH.read_text(encoding="utf-8")
        except OSError:
            return None
    try:
        return json.loads(blob)
    except (json.JSONDecodeError, ValueError):
        return None


def _read_oauth() -> tuple[dict | None, str]:
    """Return (oauth_dict, reason). oauth_dict is non-None only when reason == 'ok'."""
    raw = _load_raw_credentials()
    if raw is None:
        return None, "no_creds"
    oauth = raw.get("claudeAiOauth") or {}
    if not oauth.get("accessToken"):
        return None, "no_oauth"
    expires_at = oauth.get("expiresAt")  # epoch milliseconds
    if isinstance(expires_at, (int, float)) and expires_at > 0:
        if time.time() * 1000 >= expires_at:
            return None, "expired"
    return oauth, "ok"


def _fetch(token: str) -> dict:
    req = urllib.request.Request(
        OAUTH_USAGE_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "anthropic-beta": OAUTH_BETA,
            "User-Agent": "claude-pulse",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _fetch_usage() -> tuple[dict | None, str]:
    """Read creds, call the endpoint, normalise. Returns (data_or_None, reason)."""
    oauth, reason = _read_oauth()
    if reason != "ok":
        return None, reason
    try:
        raw = _fetch(oauth["accessToken"])
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError):
        return None, "network"

    fh = raw.get("five_hour") or {}
    sd = raw.get("seven_day") or {}
    data = {
        "five_hour_pct": fh.get("utilization"),
        "five_hour_resets_at": fh.get("resets_at"),
        "seven_day_pct": sd.get("utilization"),
        "seven_day_resets_at": sd.get("resets_at"),
        "subscription": (oauth.get("subscriptionType") or raw.get("subscription_type")),
    }
    return data, "ok"


def get_live_usage(force: bool = False) -> dict | None:
    """Return live plan usage, or None if it can't be fetched (cached, fails soft)."""
    now = time.time()
    if not force and _cache["data"] is not None and (now - _cache["at"]) < _CACHE_TTL:
        return _cache["data"]

    data, reason = _fetch_usage()
    if reason == "ok":
        _cache["at"] = now
        _cache["data"] = data
        return data
    # Transient failure: serve the last good value if we have one, else None.
    return _cache["data"]


def get_usage_status() -> dict:
    """Full uncached status for the `acp --check-usage` diagnostic."""
    data, reason = _fetch_usage()
    return {
        "reason": reason,
        "message": REASONS.get(reason, reason),
        "source": _credentials_source(),
        "platform": sys.platform,
        "data": data,
    }
