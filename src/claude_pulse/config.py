"""Paths, pricing constants, and defaults."""

from pathlib import Path

CLAUDE_DIR = Path.home() / ".claude"
STATS_CACHE_PATH = CLAUDE_DIR / "stats-cache.json"
HISTORY_PATH = CLAUDE_DIR / "history.jsonl"
SESSIONS_DIR = CLAUDE_DIR / "sessions"

# Claude API pricing per million tokens (USD)
PRICING = {
    "claude-opus-4-6": {
        "input": 15.00,
        "output": 75.00,
        "cache_read": 1.50,
        "cache_create": 18.75,
    },
    "claude-sonnet-4-6": {
        "input": 3.00,
        "output": 15.00,
        "cache_read": 0.30,
        "cache_create": 3.75,
    },
    "claude-sonnet-4-5": {
        "input": 3.00,
        "output": 15.00,
        "cache_read": 0.30,
        "cache_create": 3.75,
    },
    "claude-haiku-4-5": {
        "input": 0.80,
        "output": 4.00,
        "cache_read": 0.08,
        "cache_create": 1.00,
    },
}

# Default fallback pricing (sonnet-level)
DEFAULT_PRICING = {
    "input": 3.00,
    "output": 15.00,
    "cache_read": 0.30,
    "cache_create": 3.75,
}

# Map full model IDs to short display names
MODEL_DISPLAY_NAMES = {
    "claude-opus-4-6": "Opus 4.6",
    "claude-sonnet-4-6": "Sonnet 4.6",
    "claude-sonnet-4-5-20250929": "Sonnet 4.5",
    "claude-sonnet-4-5": "Sonnet 4.5",
    "claude-haiku-4-5-20251001": "Haiku 4.5",
    "claude-haiku-4-5": "Haiku 4.5",
}

# CLI defaults
DEFAULT_REFRESH = 5
DEFAULT_DAYS = 7


def short_model_name(model_id: str) -> str:
    """Convert a full model ID to a short display name."""
    if model_id in MODEL_DISPLAY_NAMES:
        return MODEL_DISPLAY_NAMES[model_id]
    # Try matching by prefix
    for key, name in MODEL_DISPLAY_NAMES.items():
        if model_id.startswith(key):
            return name
    # Fallback: clean up the ID
    return model_id.replace("claude-", "").split("-2025")[0].replace("-", " ").title()


def get_pricing(model_id: str) -> dict:
    """Get pricing for a model, with prefix matching and fallback."""
    if model_id in PRICING:
        return PRICING[model_id]
    for key, pricing in PRICING.items():
        if model_id.startswith(key):
            return pricing
    return DEFAULT_PRICING
