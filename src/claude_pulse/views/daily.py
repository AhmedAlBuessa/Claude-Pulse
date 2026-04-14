"""Daily usage view."""

from datetime import datetime, timedelta

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from claude_pulse.config import short_model_name
from claude_pulse.cost import calculate_cost, format_cost, format_tokens
from claude_pulse.data.history import get_daily_counts, group_by_date, load_history
from claude_pulse.data.stats import load_stats


def render_daily(console: Console, days: int = 7, project: str = None):
    """Render the daily usage table."""
    stats = load_stats()
    daily_counts = get_daily_counts(days=days)

    # Build lookup from stats-cache daily activity
    stats_by_date = {}
    if stats:
        for da in stats.daily_activity:
            stats_by_date[da.date] = da

    # Token data by date
    tokens_by_date = stats.daily_model_tokens if stats else {}

    # Table
    table = Table(
        title="Daily Usage",
        title_style="bold cyan",
        show_lines=True,
        padding=(0, 1),
    )
    table.add_column("Date", style="bold", min_width=12)
    table.add_column("Messages", justify="right", style="green")
    table.add_column("Sessions", justify="right", style="blue")
    table.add_column("Tool Calls", justify="right", style="yellow")
    table.add_column("Tokens", justify="right", style="magenta")
    table.add_column("Est. Cost", justify="right", style="red")

    today = datetime.now().strftime("%Y-%m-%d")

    for day in reversed(daily_counts):
        date = day["date"]
        messages = day["messages"]
        sessions = day["sessions"]

        # Try to get tool calls from stats-cache
        stats_day = stats_by_date.get(date)
        tool_calls = str(stats_day.tool_call_count) if stats_day else "—"

        # Use stats-cache message/session count if history has 0 but stats has data
        if messages == 0 and stats_day:
            messages = stats_day.message_count
            sessions = stats_day.session_count

        # Token info
        day_tokens = tokens_by_date.get(date, {})
        if day_tokens:
            token_parts = []
            for model_id, count in day_tokens.items():
                name = short_model_name(model_id)
                token_parts.append(f"{name}: {format_tokens(count)}")
            token_str = "\n".join(token_parts)
        else:
            token_str = "—"

        # Cost estimation (only if we have model-level data for this date)
        cost_str = "—"
        if stats and day_tokens:
            # Use aggregate model usage cost pro-rated by this day's token share
            total_cost = 0
            for model_id, usage in stats.model_usage.items():
                total_cost += calculate_cost(usage)
            if len(stats.daily_activity) == 1 and stats.daily_activity[0].date == date:
                cost_str = format_cost(total_cost)

        # Highlight today
        date_display = f"[bold]{date}[/bold]" if date == today else date

        table.add_row(
            date_display,
            str(messages),
            str(sessions),
            tool_calls,
            token_str,
            cost_str,
        )

    # Summary
    total_msgs = sum(d["messages"] for d in daily_counts)
    total_sessions = sum(d["sessions"] for d in daily_counts)
    active_days = sum(1 for d in daily_counts if d["messages"] > 0)

    summary = Text()
    summary.append(f"  {total_msgs}", style="bold green")
    summary.append(" messages across ")
    summary.append(f"{total_sessions}", style="bold blue")
    summary.append(" sessions over ")
    summary.append(f"{active_days}", style="bold")
    summary.append(f" active days (last {days} days)")

    console.print()
    console.print(table)
    console.print(summary)
    console.print()
