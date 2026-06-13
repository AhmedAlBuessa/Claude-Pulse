"""Parse per-conversation JSONL files — the real token usage data source."""

import json
import glob
import os
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from claude_pulse.config import CLAUDE_DIR


PROJECTS_DIR = CLAUDE_DIR / "projects"


@dataclass
class MessageUsage:
    timestamp: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_create_tokens: int = 0


@dataclass
class ConversationStats:
    session_id: str
    project: str
    messages: int = 0
    assistant_messages: int = 0
    user_messages: int = 0
    tool_calls: int = 0
    models: set = field(default_factory=set)
    usage: list[MessageUsage] = field(default_factory=list)
    first_timestamp: str = ""
    last_timestamp: str = ""

    @property
    def total_input_tokens(self) -> int:
        return sum(u.input_tokens for u in self.usage)

    @property
    def total_output_tokens(self) -> int:
        return sum(u.output_tokens for u in self.usage)

    @property
    def total_cache_read_tokens(self) -> int:
        return sum(u.cache_read_tokens for u in self.usage)

    @property
    def total_cache_create_tokens(self) -> int:
        return sum(u.cache_create_tokens for u in self.usage)


def _project_name_from_dir(dirname: str) -> str:
    """Extract human-readable project name from directory name."""
    # Format: -Users-user-Projects-ProjectName or similar
    parts = dirname.split("-")
    # Find the last meaningful segment
    if "Projects" in parts:
        idx = parts.index("Projects")
        return "-".join(parts[idx + 1:]) if idx + 1 < len(parts) else dirname
    # Fallback: last segment
    return parts[-1] if parts else dirname


def _parse_conversation(path: str, project_dir: str) -> Optional[ConversationStats]:
    """Parse a single conversation JSONL file."""
    session_id = Path(path).stem
    project = _project_name_from_dir(os.path.basename(project_dir.rstrip("/")))

    stats = ConversationStats(session_id=session_id, project=project)

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

                msg_type = entry.get("type", "")
                timestamp = entry.get("timestamp", "")

                if timestamp:
                    if not stats.first_timestamp or timestamp < stats.first_timestamp:
                        stats.first_timestamp = timestamp
                    if not stats.last_timestamp or timestamp > stats.last_timestamp:
                        stats.last_timestamp = timestamp

                if msg_type == "user":
                    stats.user_messages += 1
                    stats.messages += 1

                elif msg_type == "assistant":
                    stats.assistant_messages += 1
                    stats.messages += 1

                    message = entry.get("message", {})
                    model = message.get("model", "")
                    usage = message.get("usage")

                    if model:
                        stats.models.add(model)

                    if usage:
                        stats.usage.append(MessageUsage(
                            timestamp=timestamp,
                            model=model,
                            input_tokens=usage.get("input_tokens", 0),
                            output_tokens=usage.get("output_tokens", 0),
                            cache_read_tokens=usage.get("cache_read_input_tokens", 0),
                            cache_create_tokens=usage.get("cache_creation_input_tokens", 0),
                        ))

                    # Count tool uses in content
                    content = message.get("content", [])
                    if isinstance(content, list):
                        stats.tool_calls += sum(
                            1 for c in content
                            if isinstance(c, dict) and c.get("type") == "tool_use"
                        )
    except OSError:
        return None

    if stats.messages == 0:
        return None

    return stats


# File-level cache: path -> (mtime, ConversationStats)
_conv_cache: dict[str, tuple[float, ConversationStats]] = {}


def load_all_conversations() -> list[ConversationStats]:
    """Load all conversation files, using cache for unchanged files."""
    if not PROJECTS_DIR.exists():
        return []

    conversations = []
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

            # Use cache if file hasn't changed
            cached = _conv_cache.get(path_str)
            if cached and cached[0] == mtime:
                conversations.append(cached[1])
                continue

            conv = _parse_conversation(path_str, str(project_dir))
            if conv:
                _conv_cache[path_str] = (mtime, conv)
                conversations.append(conv)

    # Clean stale cache entries
    for stale in set(_conv_cache.keys()) - seen_paths:
        del _conv_cache[stale]

    conversations.sort(key=lambda c: c.last_timestamp, reverse=True)
    return conversations


def _count_user_messages_by_day(conv: ConversationStats, daily: dict, cutoff_str: str):
    """Count user messages per day by re-reading the conversation file."""
    # We need to find the file path from the conversation's session_id
    if not PROJECTS_DIR.exists():
        return
    for project_dir in PROJECTS_DIR.iterdir():
        if not project_dir.is_dir():
            continue
        jsonl_path = project_dir / f"{conv.session_id}.jsonl"
        if not jsonl_path.exists():
            continue
        try:
            with open(jsonl_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if entry.get("type") != "user":
                        continue
                    ts = entry.get("timestamp", "")
                    if not isinstance(ts, str) or len(ts) < 10:
                        continue
                    date = ts[:10]
                    if date >= cutoff_str:
                        daily[date]["user_messages"] += 1
                        daily[date]["sessions"].add(conv.session_id)
        except OSError:
            pass
        break


def get_daily_usage(conversations: list[ConversationStats], days: int = 7) -> list[dict]:
    """Aggregate all usage by day from conversation data (tokens, messages, sessions)."""
    from datetime import timezone
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    cutoff_str = cutoff.strftime("%Y-%m-%d")

    daily: dict[str, dict] = defaultdict(lambda: {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_create_tokens": 0,
        "user_messages": 0,
        "assistant_messages": 0,
        "tool_calls": 0,
        "sessions": set(),
        "models": set(),
    })

    for conv in conversations:
        # Count user messages per day by scanning the raw file
        # We already have usage entries with timestamps for assistant messages
        for usage in conv.usage:
            if not usage.timestamp:
                continue
            date = usage.timestamp[:10]
            if date < cutoff_str:
                continue
            daily[date]["input_tokens"] += usage.input_tokens
            daily[date]["output_tokens"] += usage.output_tokens
            daily[date]["cache_read_tokens"] += usage.cache_read_tokens
            daily[date]["cache_create_tokens"] += usage.cache_create_tokens
            daily[date]["assistant_messages"] += 1
            daily[date]["sessions"].add(conv.session_id)
            if usage.model:
                daily[date]["models"].add(usage.model)

    # We need user message counts per day too — re-scan conversations
    for conv in conversations:
        _count_user_messages_by_day(conv, daily, cutoff_str)

    # Fill in missing days
    result = []
    for i in range(days):
        date = (datetime.now() - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d")
        day_data = daily.get(date, {
            "input_tokens": 0, "output_tokens": 0,
            "cache_read_tokens": 0, "cache_create_tokens": 0,
            "user_messages": 0, "assistant_messages": 0,
            "tool_calls": 0, "sessions": set(), "models": set(),
        })
        result.append({
            "date": date,
            "input_tokens": day_data["input_tokens"],
            "output_tokens": day_data["output_tokens"],
            "cache_read_tokens": day_data["cache_read_tokens"],
            "cache_create_tokens": day_data["cache_create_tokens"],
            "messages": day_data["user_messages"],
            "sessions": len(day_data["sessions"]),
            "models": day_data["models"],
        })

    return result


def get_model_totals(conversations: list[ConversationStats]) -> dict[str, dict]:
    """Aggregate token usage by model across all conversations."""
    totals: dict[str, dict] = defaultdict(lambda: {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_create_tokens": 0,
    })

    for conv in conversations:
        for usage in conv.usage:
            model = usage.model or "unknown"
            totals[model]["input_tokens"] += usage.input_tokens
            totals[model]["output_tokens"] += usage.output_tokens
            totals[model]["cache_read_tokens"] += usage.cache_read_tokens
            totals[model]["cache_create_tokens"] += usage.cache_create_tokens

    return dict(totals)


def get_project_stats(conversations: list[ConversationStats]) -> list[dict]:
    """Aggregate stats per project."""
    projects: dict[str, dict] = defaultdict(lambda: {
        "conversations": 0,
        "messages": 0,
        "user_messages": 0,
        "tool_calls": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cost": 0.0,
        "last_active": "",
    })

    from claude_pulse.cost import calculate_cost_raw

    for conv in conversations:
        name = conv.project or "unknown"
        projects[name]["conversations"] += 1
        projects[name]["messages"] += conv.messages
        projects[name]["user_messages"] += conv.user_messages
        projects[name]["tool_calls"] += conv.tool_calls

        for usage in conv.usage:
            projects[name]["output_tokens"] += usage.output_tokens
            projects[name]["cache_read_tokens"] += usage.cache_read_tokens
            projects[name]["cost"] += calculate_cost_raw(
                usage.model or "claude-sonnet-4-6",
                usage.input_tokens,
                usage.output_tokens,
                usage.cache_read_tokens,
                usage.cache_create_tokens,
            )

        if conv.last_timestamp > projects[name]["last_active"]:
            projects[name]["last_active"] = conv.last_timestamp

    result = [{"project": k, **v} for k, v in projects.items()]
    result.sort(key=lambda x: x["cost"], reverse=True)
    return result


def get_hourly_activity(conversations: list[ConversationStats], days: int = 7) -> list[int]:
    """Get message counts per hour of day (0-23) for the last N days."""
    from datetime import timezone
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    cutoff_str = cutoff.strftime("%Y-%m-%dT")

    hours = [0] * 24
    for conv in conversations:
        for usage in conv.usage:
            if not usage.timestamp or usage.timestamp < cutoff_str:
                continue
            try:
                hour = int(usage.timestamp[11:13])
                hours[hour] += 1
            except (ValueError, IndexError):
                pass
    return hours


def get_rolling_window_usage(conversations: list[ConversationStats], window_hours: int = 5) -> dict:
    """Get token usage within the rolling window (last N hours)."""
    from datetime import timezone
    now_utc = datetime.now(timezone.utc)
    cutoff = now_utc - timedelta(hours=window_hours)
    cutoff_iso = cutoff.strftime("%Y-%m-%dT%H:%M:%S")

    totals = {
        "output_tokens": 0,
        "input_tokens": 0,
        "cache_read_tokens": 0,
        "cache_create_tokens": 0,
        "messages": 0,
        "window_hours": window_hours,
        "oldest_in_window": "",
        "newest_in_window": "",
        "elapsed_minutes": 0,
    }

    for conv in conversations:
        for usage in conv.usage:
            if not usage.timestamp or usage.timestamp < cutoff_iso:
                continue
            totals["output_tokens"] += usage.output_tokens
            totals["input_tokens"] += usage.input_tokens
            totals["cache_read_tokens"] += usage.cache_read_tokens
            totals["cache_create_tokens"] += usage.cache_create_tokens
            totals["messages"] += 1

            if not totals["oldest_in_window"] or usage.timestamp < totals["oldest_in_window"]:
                totals["oldest_in_window"] = usage.timestamp
            if not totals["newest_in_window"] or usage.timestamp > totals["newest_in_window"]:
                totals["newest_in_window"] = usage.timestamp

    # Calculate elapsed minutes since first message in window
    if totals["oldest_in_window"]:
        try:
            oldest = datetime.fromisoformat(totals["oldest_in_window"].replace("Z", "+00:00"))
            newest = datetime.fromisoformat(totals["newest_in_window"].replace("Z", "+00:00"))
            totals["elapsed_minutes"] = max(1, int((newest - oldest).total_seconds() / 60))
        except (ValueError, TypeError):
            totals["elapsed_minutes"] = 1

    return totals
