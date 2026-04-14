"""Real-time usage dashboard."""

import time
from datetime import datetime, timedelta

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from claude_pulse.config import short_model_name
from claude_pulse.cost import calculate_cost, format_cost, format_tokens
from claude_pulse.data.history import get_daily_counts, load_history
from claude_pulse.data.sessions import get_active_sessions
from claude_pulse.data.stats import load_stats


def _format_duration(ms: int) -> str:
    """Format milliseconds to human-readable duration."""
    seconds = ms // 1000
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m {seconds % 60}s"
    hours = minutes // 60
    return f"{hours}h {minutes % 60}m"


def _build_display(console: Console) -> Group:
    """Build the full realtime display."""
    now = datetime.now()
    stats = load_stats()
    sessions = get_active_sessions()

    # Header
    status_parts = []
    status_parts.append(f"[bold]{len(sessions)}[/bold] active session{'s' if len(sessions) != 1 else ''}")
    status_parts.append(f"Updated: {now.strftime('%I:%M:%S %p')}")
    header = Panel(
        Text.from_markup("  |  ".join(status_parts)),
        title="[bold cyan]Claude Pulse[/bold cyan]",
        border_style="cyan",
        padding=(0, 2),
    )

    # Active sessions table
    session_table = Table(
        title="Active Sessions",
        title_style="bold white",
        padding=(0, 1),
        show_lines=False,
    )
    session_table.add_column("PID", style="dim", justify="right", min_width=6)
    session_table.add_column("Project", style="bold green", min_width=16)
    session_table.add_column("Duration", justify="right", style="cyan", min_width=10)
    session_table.add_column("Type", style="yellow", min_width=8)

    if sessions:
        for s in sessions:
            now_ms = int(now.timestamp() * 1000)
            duration = _format_duration(now_ms - s.started_at) if s.started_at else "—"
            kind = s.kind or s.entrypoint or "interactive"
            session_table.add_row(str(s.pid), s.project_name or s.cwd, duration, kind)
    else:
        session_table.add_row("—", "[dim]No active sessions[/dim]", "—", "—")

    # Token usage table
    token_table = Table(
        title="Token Usage (All Time)",
        title_style="bold white",
        padding=(0, 1),
        show_lines=False,
    )
    token_table.add_column("Model", style="bold", min_width=14)
    token_table.add_column("Input", justify="right", style="green", min_width=10)
    token_table.add_column("Output", justify="right", style="blue", min_width=10)
    token_table.add_column("Cache Read", justify="right", style="yellow", min_width=12)
    token_table.add_column("Cache Write", justify="right", style="yellow", min_width=12)
    token_table.add_column("Est. Cost", justify="right", style="bold red", min_width=10)

    total_cost = 0.0
    if stats and stats.model_usage:
        for model_id, usage in stats.model_usage.items():
            cost = calculate_cost(usage)
            total_cost += cost
            token_table.add_row(
                short_model_name(model_id),
                format_tokens(usage.input_tokens),
                format_tokens(usage.output_tokens),
                format_tokens(usage.cache_read_tokens),
                format_tokens(usage.cache_create_tokens),
                format_cost(cost),
            )
    else:
        token_table.add_row("—", "—", "—", "—", "—", "—")

    # Today's activity
    today_entries = load_history(since=datetime.now().replace(hour=0, minute=0, second=0))
    today_sessions = len({e.session_id for e in today_entries if e.session_id})

    # Recent days sparkline (last 7 days)
    daily = get_daily_counts(days=7)
    max_msgs = max((d["messages"] for d in daily), default=1) or 1
    bars = "▁▂▃▄▅▆▇█"
    sparkline = ""
    for d in daily:
        idx = min(int(d["messages"] / max_msgs * (len(bars) - 1)), len(bars) - 1)
        sparkline += bars[idx]

    # Summary panel
    summary_parts = []
    summary_parts.append(f"[bold green]{len(today_entries)}[/bold green] messages today")
    summary_parts.append(f"[bold blue]{today_sessions}[/bold blue] sessions today")
    if stats:
        summary_parts.append(f"[bold]{stats.total_messages}[/bold] messages all time")
        summary_parts.append(f"[bold]{stats.total_sessions}[/bold] sessions all time")
    if total_cost > 0:
        summary_parts.append(f"[bold red]{format_cost(total_cost)}[/bold red] total est. cost")

    summary_text = Text.from_markup("  •  ".join(summary_parts))
    activity_text = Text.from_markup(f"  Last 7 days: [bold cyan]{sparkline}[/bold cyan]  ({', '.join(str(d['messages']) for d in daily)})")

    summary = Panel(
        Group(summary_text, activity_text),
        title="Summary",
        border_style="dim",
        padding=(0, 2),
    )

    return Group(header, "", session_table, "", token_table, "", summary)


def render_realtime(console: Console, refresh: float = 5.0):
    """Render the live-updating realtime dashboard."""
    try:
        with Live(
            _build_display(console),
            console=console,
            refresh_per_second=1,
            screen=False,
        ) as live:
            while True:
                time.sleep(refresh)
                live.update(_build_display(console))
    except KeyboardInterrupt:
        console.print("\n[dim]Stopped.[/dim]")
