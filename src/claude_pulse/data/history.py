"""Parse history.jsonl."""

import json
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional

from claude_pulse.config import HISTORY_PATH
from claude_pulse.models import HistoryEntry


def load_history(
    since: Optional[datetime] = None,
    project: Optional[str] = None,
) -> list[HistoryEntry]:
    """Load history entries, optionally filtered by date and project."""
    if not HISTORY_PATH.exists():
        return []

    entries = []
    since_ms = int(since.timestamp() * 1000) if since else None

    try:
        with open(HISTORY_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError:
                    continue

                ts = raw.get("timestamp", 0)
                if since_ms and ts < since_ms:
                    continue

                proj = raw.get("project", "")
                if project and project not in proj:
                    continue

                entries.append(HistoryEntry(
                    display=raw.get("display", ""),
                    timestamp=ts,
                    project=proj,
                    session_id=raw.get("sessionId", ""),
                ))
    except OSError:
        return []

    return entries


def group_by_date(entries: list[HistoryEntry]) -> dict[str, list[HistoryEntry]]:
    """Group entries by date string (YYYY-MM-DD)."""
    groups: dict[str, list[HistoryEntry]] = defaultdict(list)
    for entry in entries:
        groups[entry.date_str].append(entry)
    return dict(groups)


def group_by_project(entries: list[HistoryEntry]) -> dict[str, list[HistoryEntry]]:
    """Group entries by project name."""
    groups: dict[str, list[HistoryEntry]] = defaultdict(list)
    for entry in entries:
        name = entry.project_name or "(unknown)"
        groups[name].append(entry)
    return dict(groups)


def group_by_session(entries: list[HistoryEntry]) -> dict[str, list[HistoryEntry]]:
    """Group entries by session ID."""
    groups: dict[str, list[HistoryEntry]] = defaultdict(list)
    for entry in entries:
        if entry.session_id:
            groups[entry.session_id].append(entry)
    return dict(groups)


def get_daily_counts(days: int = 7) -> list[dict]:
    """Get message and session counts per day for the last N days."""
    since = datetime.now() - timedelta(days=days)
    entries = load_history(since=since)
    by_date = group_by_date(entries)

    result = []
    for i in range(days):
        date = (datetime.now() - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d")
        day_entries = by_date.get(date, [])
        sessions = len({e.session_id for e in day_entries if e.session_id})
        result.append({
            "date": date,
            "messages": len(day_entries),
            "sessions": sessions,
        })

    return result
