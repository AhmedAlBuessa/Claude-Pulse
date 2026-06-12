"""Browse past sessions — extract a resumable summary per conversation.

Unlike ``conversations.py`` (which aggregates tokens for usage stats), this
module pulls the bits needed to *find and resume* a past session: its first
real prompt (used as a title), the working directory to resume it in, when it
started / was last active, and how big it was.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from claude_pulse.config import CLAUDE_DIR

PROJECTS_DIR = CLAUDE_DIR / "projects"

# Markers for user "messages" that aren't real typed prompts and so make poor
# titles: tool results, slash-command plumbing, and injected harness context.
_SKIP_TITLE_PREFIXES = (
    "<local-command",
    "<command-",
    "caveat:",
    "<bash-",
    "[request interrupted",
    "<system-reminder",
)


@dataclass
class SessionSummary:
    session_id: str
    project: str
    cwd: str
    title: str
    started_at: Optional[datetime]
    last_active: Optional[datetime]
    message_count: int = 0
    models: set = field(default_factory=set)
    path: str = ""

    @property
    def project_name(self) -> str:
        """Human-readable project folder name."""
        if self.cwd:
            return self.cwd.rstrip("/\\").replace("\\", "/").rsplit("/", 1)[-1]
        return self.project or "unknown"


def _parse_timestamp(ts: str) -> Optional[datetime]:
    if not ts or not isinstance(ts, str):
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def _extract_text(content) -> str:
    """Flatten a message ``content`` (string or list of blocks) to plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return " ".join(parts)
    return ""


def _clean_title(text: str) -> str:
    text = " ".join(text.split())  # collapse whitespace/newlines
    # Strip a leading "[Image #1]" style marker so the real ask shows.
    while text.startswith("[Image #"):
        end = text.find("]")
        if end == -1:
            break
        text = text[end + 1:].lstrip()
    return text


def _is_real_prompt(text: str) -> bool:
    if not text or len(text.strip()) < 2:
        return False
    lowered = text.lstrip().lower()
    return not lowered.startswith(_SKIP_TITLE_PREFIXES)


def _parse_session(path: Path, project_dir: str) -> Optional[SessionSummary]:
    """Single pass over a conversation file to build its summary."""
    session_id = path.stem
    cwd = ""
    title = ""
    first_ts: Optional[datetime] = None
    last_ts: Optional[datetime] = None
    message_count = 0
    models: set = set()

    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if not cwd:
                    raw_cwd = entry.get("cwd")
                    if raw_cwd:
                        cwd = raw_cwd

                ts = _parse_timestamp(entry.get("timestamp", ""))
                if ts:
                    if first_ts is None or ts < first_ts:
                        first_ts = ts
                    if last_ts is None or ts > last_ts:
                        last_ts = ts

                msg_type = entry.get("type", "")
                if msg_type == "user":
                    message_count += 1
                    if not title and not entry.get("isMeta"):
                        text = _clean_title(
                            _extract_text(entry.get("message", {}).get("content"))
                        )
                        if _is_real_prompt(text):
                            title = text
                elif msg_type == "assistant":
                    message_count += 1
                    model = entry.get("message", {}).get("model", "")
                    if model:
                        models.add(model)
    except OSError:
        return None

    if message_count == 0:
        return None

    return SessionSummary(
        session_id=session_id,
        project=Path(project_dir).name,
        cwd=cwd,
        title=title or "(no prompt text)",
        started_at=first_ts,
        last_active=last_ts,
        message_count=message_count,
        models=models,
        path=str(path),
    )


# File-level cache: path -> (mtime, SessionSummary). Mirrors conversations.py.
_summary_cache: dict[str, tuple[float, SessionSummary]] = {}


def list_sessions(
    days: Optional[int] = None,
    project: Optional[str] = None,
) -> list[SessionSummary]:
    """Return past sessions, newest first.

    ``days``    — only sessions active within the last N days (None = all).
    ``project`` — case-insensitive substring match on project/cwd name.
    """
    if not PROJECTS_DIR.exists():
        return []

    cutoff = None
    if days is not None:
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    summaries: list[SessionSummary] = []
    seen_paths = set()

    for project_dir in PROJECTS_DIR.iterdir():
        if not project_dir.is_dir():
            continue
        for jsonl_file in project_dir.glob("*.jsonl"):
            path_str = str(jsonl_file)
            seen_paths.add(path_str)
            try:
                mtime = jsonl_file.stat().st_mtime
            except OSError:
                continue

            cached = _summary_cache.get(path_str)
            if cached and cached[0] == mtime:
                summary = cached[1]
            else:
                summary = _parse_session(jsonl_file, str(project_dir))
                if summary:
                    _summary_cache[path_str] = (mtime, summary)
            if not summary:
                continue

            if cutoff and (summary.last_active is None or summary.last_active < cutoff):
                continue
            if project:
                needle = project.lower()
                if needle not in summary.project_name.lower() and needle not in summary.cwd.lower():
                    continue

            summaries.append(summary)

    for stale in set(_summary_cache.keys()) - seen_paths:
        del _summary_cache[stale]

    summaries.sort(
        key=lambda s: s.last_active or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    return summaries
