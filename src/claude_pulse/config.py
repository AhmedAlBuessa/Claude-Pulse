"""Paths, pricing constants, and defaults."""

import json
import re
from pathlib import Path

CLAUDE_DIR = Path.home() / ".claude"
PULSE_CONFIG_DIR = Path.home() / ".claude-pulse"
PULSE_CONFIG_FILE = PULSE_CONFIG_DIR / "config.json"
STATS_CACHE_PATH = CLAUDE_DIR / "stats-cache.json"
HISTORY_PATH = CLAUDE_DIR / "history.jsonl"
SESSIONS_DIR = CLAUDE_DIR / "sessions"

# Claude API pricing per million tokens (USD)
PRICING = {
    "claude-opus-4-8": {
        "input": 15.00,
        "output": 75.00,
        "cache_read": 1.50,
        "cache_create": 18.75,
    },
    "claude-opus-4-7": {
        "input": 15.00,
        "output": 75.00,
        "cache_read": 1.50,
        "cache_create": 18.75,
    },
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

# Per-family pricing, used when an exact/prefixed model id isn't listed above.
# This keeps cost correct for new model versions (e.g. a future opus-4-9)
# instead of silently falling back to Sonnet rates.
FAMILY_PRICING = {
    "opus": {"input": 15.00, "output": 75.00, "cache_read": 1.50, "cache_create": 18.75},
    "sonnet": {"input": 3.00, "output": 15.00, "cache_read": 0.30, "cache_create": 3.75},
    "haiku": {"input": 0.80, "output": 4.00, "cache_read": 0.08, "cache_create": 1.00},
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
    "claude-opus-4-8": "Opus 4.8",
    "claude-opus-4-7": "Opus 4.7",
    "claude-opus-4-6": "Opus 4.6",
    "claude-sonnet-4-6": "Sonnet 4.6",
    "claude-sonnet-4-5-20250929": "Sonnet 4.5",
    "claude-sonnet-4-5": "Sonnet 4.5",
    "claude-haiku-4-5-20251001": "Haiku 4.5",
    "claude-haiku-4-5": "Haiku 4.5",
}

# Plan limits (output tokens per 5-hour rolling window)
# These are estimates calibrated from website data. They intentionally
# lean slightly low so the tool warns you before the website would.
PLAN_LIMITS = {
    "pro": {"name": "Pro", "output_tokens": 25_000, "window_hours": 5},
    "max5": {"name": "Max 5x", "output_tokens": 125_000, "window_hours": 5},
    "max20": {"name": "Max 20x", "output_tokens": 500_000, "window_hours": 5},
}

# CLI defaults
DEFAULT_REFRESH = 0.5
DEFAULT_DAYS = 7
DEFAULT_PLAN = "max5"


def short_model_name(model_id: str) -> str:
    """Convert a full model ID to a short display name."""
    if model_id in MODEL_DISPLAY_NAMES:
        return MODEL_DISPLAY_NAMES[model_id]
    # Try matching by prefix
    for key, name in MODEL_DISPLAY_NAMES.items():
        if model_id.startswith(key):
            return name
    # Fallback: derive "Family X.Y" from an id like claude-opus-4-8[-20260101]
    m = re.match(r"claude-(opus|sonnet|haiku)-(\d+)-(\d+)", model_id)
    if m:
        family, major, minor = m.groups()
        return f"{family.title()} {major}.{minor}"
    # Last resort: clean up the raw id
    return model_id.replace("claude-", "").split("-2025")[0].replace("-", " ").title()


def get_pricing(model_id: str) -> dict:
    """Get pricing for a model, with prefix, family, and default fallback."""
    if model_id in PRICING:
        return PRICING[model_id]
    for key, pricing in PRICING.items():
        if model_id.startswith(key):
            return pricing
    # Family fallback so a new version is priced by its tier, not Sonnet default.
    for family, pricing in FAMILY_PRICING.items():
        if family in model_id:
            return pricing
    return DEFAULT_PRICING


def load_saved_limit() -> int | None:
    """Load calibrated limit from saved config."""
    if not PULSE_CONFIG_FILE.exists():
        return None
    try:
        data = json.loads(PULSE_CONFIG_FILE.read_text(encoding="utf-8"))
        return data.get("calibrated_limit")
    except (json.JSONDecodeError, OSError):
        return None


def save_calibrated_limit(limit: int):
    """Save calibrated limit to config."""
    PULSE_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    data = {}
    if PULSE_CONFIG_FILE.exists():
        try:
            data = json.loads(PULSE_CONFIG_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    data["calibrated_limit"] = limit
    PULSE_CONFIG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
