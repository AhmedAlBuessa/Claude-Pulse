"""Parse active session files."""

import json
import os
import sys
from typing import Optional

from claude_pulse.config import SESSIONS_DIR
from claude_pulse.models import ActiveSession


if sys.platform == "win32":
    import ctypes

    def _is_pid_alive(pid: int) -> bool:
        """Check if a process is still running (Windows)."""
        if pid <= 0:
            return False
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong()
            if kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return exit_code.value == STILL_ACTIVE
            return True  # exists but couldn't query exit code
        finally:
            kernel32.CloseHandle(handle)

else:

    def _is_pid_alive(pid: int) -> bool:
        """Check if a process is still running (POSIX)."""
        if pid <= 0:
            return False
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
            raw = json.loads(path.read_text(encoding="utf-8"))
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
