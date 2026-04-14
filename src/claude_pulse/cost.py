"""Token cost calculation."""

from claude_pulse.config import get_pricing
from claude_pulse.models import ModelUsage


def calculate_cost(usage: ModelUsage) -> float:
    """Calculate USD cost from a ModelUsage object."""
    return calculate_cost_raw(
        usage.model,
        usage.input_tokens,
        usage.output_tokens,
        usage.cache_read_tokens,
        usage.cache_create_tokens,
    )


def calculate_cost_raw(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int,
    cache_create_tokens: int,
) -> float:
    """Calculate USD cost from raw token counts."""
    pricing = get_pricing(model)
    cost = (
        input_tokens * pricing["input"]
        + output_tokens * pricing["output"]
        + cache_read_tokens * pricing["cache_read"]
        + cache_create_tokens * pricing["cache_create"]
    ) / 1_000_000
    return cost


def format_cost(usd: float) -> str:
    """Format a USD amount for display."""
    if usd < 0.01:
        return f"${usd:.4f}"
    return f"${usd:.2f}"


def format_tokens(count: int) -> str:
    """Format a token count for display (e.g., 14.2K, 105.3M)."""
    if count >= 1_000_000_000:
        return f"{count / 1_000_000_000:.1f}B"
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M"
    if count >= 1_000:
        return f"{count / 1_000:.1f}K"
    return str(count)
