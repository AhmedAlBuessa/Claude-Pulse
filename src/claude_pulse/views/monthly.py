"""Monthly usage view."""

from collections import defaultdict
from datetime import datetime

from rich.console import Console
from rich.table import Table
from rich.text import Text

from claude_pulse.data.history import group_by_date, load_history
from claude_pulse.data.stats import load_stats


def render_monthly(console: Console):
    """Render the monthly aggregation table."""
    # Load all history
    entries = load_history()
    by_date = group_by_date(entries)

    # Aggregate by month
    monthly: dict[str, dict] = defaultdict(lambda: {
        "messages": 0,
        "sessions": set(),
        "active_days": 0,
    })

    for date_str, day_entries in by_date.items():
        month = date_str[:7]  # YYYY-MM
        monthly[month]["messages"] += len(day_entries)
        monthly[month]["sessions"].update(e.session_id for e in day_entries if e.session_id)
        monthly[month]["active_days"] += 1

    if not monthly:
        console.print("\n  [dim]No usage data found.[/dim]\n")
        return

    # Also check stats-cache for token data
    stats = load_stats()
    stats_by_month: dict[str, dict] = defaultdict(lambda: {"tool_calls": 0})
    if stats:
        for da in stats.daily_activity:
            month = da.date[:7]
            stats_by_month[month]["tool_calls"] += da.tool_call_count

    table = Table(
        title="Monthly Usage",
        title_style="bold cyan",
        show_lines=True,
        padding=(0, 1),
    )
    table.add_column("Month", style="bold", min_width=10)
    table.add_column("Messages", justify="right", style="green")
    table.add_column("Sessions", justify="right", style="blue")
    table.add_column("Active Days", justify="right", style="yellow")
    table.add_column("Tool Calls", justify="right", style="magenta")
    table.add_column("Avg Msgs/Day", justify="right", style="cyan")

    current_month = datetime.now().strftime("%Y-%m")

    for month in sorted(monthly.keys()):
        data = monthly[month]
        sessions = len(data["sessions"])
        active_days = data["active_days"]
        messages = data["messages"]
        avg = messages / active_days if active_days > 0 else 0

        tool_calls = stats_by_month[month]["tool_calls"]
        tool_str = str(tool_calls) if tool_calls > 0 else "—"

        month_display = f"[bold]{month}[/bold]" if month == current_month else month

        table.add_row(
            month_display,
            str(messages),
            str(sessions),
            str(active_days),
            tool_str,
            f"{avg:.0f}",
        )

    # Totals
    total_msgs = sum(m["messages"] for m in monthly.values())
    total_sessions = len({s for m in monthly.values() for s in m["sessions"]})

    summary = Text()
    summary.append(f"  {total_msgs}", style="bold green")
    summary.append(" total messages across ")
    summary.append(f"{total_sessions}", style="bold blue")
    summary.append(" sessions over ")
    summary.append(f"{len(monthly)}", style="bold")
    summary.append(" months")

    console.print()
    console.print(table)
    console.print(summary)
    console.print()
