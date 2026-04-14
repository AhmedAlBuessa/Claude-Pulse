"""Data models for Claude Pulse."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class DailyActivity:
    date: str
    message_count: int = 0
    session_count: int = 0
    tool_call_count: int = 0


@dataclass
class ModelUsage:
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_create_tokens: int = 0
    cost_usd: float = 0.0
    web_search_requests: int = 0


@dataclass
class LongestSession:
    session_id: str
    duration_ms: int = 0
    message_count: int = 0
    timestamp: str = ""


@dataclass
class StatsCache:
    version: int = 0
    last_computed_date: str = ""
    daily_activity: list[DailyActivity] = field(default_factory=list)
    daily_model_tokens: dict[str, dict[str, int]] = field(default_factory=dict)
    model_usage: dict[str, ModelUsage] = field(default_factory=dict)
    total_sessions: int = 0
    total_messages: int = 0
    longest_session: Optional[LongestSession] = None
    first_session_date: str = ""
    hour_counts: dict[str, int] = field(default_factory=dict)


@dataclass
class HistoryEntry:
    display: str
    timestamp: int  # unix milliseconds
    project: str = ""
    session_id: str = ""

    @property
    def datetime(self) -> datetime:
        return datetime.fromtimestamp(self.timestamp / 1000)

    @property
    def date_str(self) -> str:
        return self.datetime.strftime("%Y-%m-%d")

    @property
    def project_name(self) -> str:
        if not self.project:
            return ""
        return self.project.rstrip("/").rsplit("/", 1)[-1]


@dataclass
class ActiveSession:
    pid: int
    session_id: str
    cwd: str
    started_at: int  # unix milliseconds
    kind: str = ""
    entrypoint: str = ""

    @property
    def project_name(self) -> str:
        if not self.cwd:
            return ""
        return self.cwd.rstrip("/").rsplit("/", 1)[-1]

    @property
    def started_datetime(self) -> datetime:
        return datetime.fromtimestamp(self.started_at / 1000)
