"""Parse stats-cache.json."""

import json
from typing import Optional

from claude_pulse.config import STATS_CACHE_PATH
from claude_pulse.models import DailyActivity, LongestSession, ModelUsage, StatsCache


def load_stats() -> Optional[StatsCache]:
    """Load and parse stats-cache.json. Returns None if file missing or invalid."""
    if not STATS_CACHE_PATH.exists():
        return None

    try:
        raw = json.loads(STATS_CACHE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

    stats = StatsCache(
        version=raw.get("version", 0),
        last_computed_date=raw.get("lastComputedDate", ""),
        total_sessions=raw.get("totalSessions", 0),
        total_messages=raw.get("totalMessages", 0),
        first_session_date=raw.get("firstSessionDate", ""),
        hour_counts=raw.get("hourCounts", {}),
    )

    # Daily activity
    for entry in raw.get("dailyActivity", []):
        stats.daily_activity.append(DailyActivity(
            date=entry["date"],
            message_count=entry.get("messageCount", 0),
            session_count=entry.get("sessionCount", 0),
            tool_call_count=entry.get("toolCallCount", 0),
        ))

    # Daily model tokens
    for entry in raw.get("dailyModelTokens", []):
        stats.daily_model_tokens[entry["date"]] = entry.get("tokensByModel", {})

    # Model usage
    for model_id, usage in raw.get("modelUsage", {}).items():
        stats.model_usage[model_id] = ModelUsage(
            model=model_id,
            input_tokens=usage.get("inputTokens", 0),
            output_tokens=usage.get("outputTokens", 0),
            cache_read_tokens=usage.get("cacheReadInputTokens", 0),
            cache_create_tokens=usage.get("cacheCreationInputTokens", 0),
            cost_usd=usage.get("costUSD", 0),
            web_search_requests=usage.get("webSearchRequests", 0),
        )

    # Longest session
    ls = raw.get("longestSession")
    if ls:
        stats.longest_session = LongestSession(
            session_id=ls.get("sessionId", ""),
            duration_ms=ls.get("duration", 0),
            message_count=ls.get("messageCount", 0),
            timestamp=ls.get("timestamp", ""),
        )

    return stats
