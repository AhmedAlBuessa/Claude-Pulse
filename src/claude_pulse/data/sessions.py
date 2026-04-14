"""Parse active session files."""

import json
import os
import signal
from typing import Optional

from claude_pulse.config import SESSIONS_DIR
from claude_pulse.models import ActiveSession


def _is_pid_alive(pid: int) -> bool:
    """Check if a process is still running."""
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # process exists but we can't signal it


def get_active_sessions() -> list[ActiveSession]:
    """Load sessions that have a live PID."""
    if not SESSIONS_DIR.exists():
        return []

    sessions = []
    for path in SESSIONS_DIR.glob("*.json"):
        try:
            raw = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue

        pid = raw.get("pid", 0)
        if not pid or not _is_pid_alive(pid):
            continue

        sessions.append(ActiveSession(
            pid=pid,
            session_id=raw.get("sessionId", ""),
            cwd=raw.get("cwd", ""),
            started_at=raw.get("startedAt", 0),
            kind=raw.get("kind", ""),
            entrypoint=raw.get("entrypoint", ""),
        ))

    return sessions
