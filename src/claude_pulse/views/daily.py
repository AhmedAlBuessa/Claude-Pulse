"""Daily usage view."""

from datetime import datetime

from rich.console import Console
from rich.table import Table
from rich.text import Text

from claude_pulse.cost import calculate_cost_raw, format_cost, format_tokens
from claude_pulse.data.conversations import get_daily_usage, load_all_conversations


def render_daily(console: Console, days: int = 7, project: str = None):
    """Render the daily usage table."""
    conversations = load_all_conversations()
    daily = get_daily_usage(conversations, days=days)

    table = Table(
        title=f"Daily Usage (Last {days} Days)",
        title_style="bold cyan",
        show_lines=True,
        padding=(0, 1),
    )
    table.add_column("Date", style="bold", min_width=12)
    table.add_column("Messages", justify="right", style="green")
    table.add_column("Sessions", justify="right", style="blue")
    table.add_column("Input", justify="right", style="magenta")
    table.add_column("Output", justify="right", style="magenta")
    table.add_column("Cache Read", justify="right", style="yellow")
    table.add_column("Cache Write", justify="right", style="yellow")
    table.add_column("Est. Cost", justify="right", style="red")

    today = datetime.now().strftime("%Y-%m-%d")
    total_cost = 0.0

    for day in reversed(daily):
        date = day["date"]
        messages = day["messages"]
        sessions = day["sessions"]
        inp = day["input_tokens"]
        out = day["output_tokens"]
        cache_r = day["cache_read_tokens"]
        cache_w = day["cache_create_tokens"]

        models = day.get("models", set())
        day_cost = 0.0
        if inp or out or cache_r or cache_w:
            model = next(iter(models)) if models else "claude-sonnet-4-6"
            day_cost = calculate_cost_raw(model, inp, out, cache_r, cache_w)
            total_cost += day_cost

        date_display = f"[bold]{date}[/bold]" if date == today else date

        table.add_row(
            date_display,
            str(messages) if messages else "[dim]0[/dim]",
            str(sessions) if sessions else "[dim]0[/dim]",
            format_tokens(inp) if inp else "[dim]—[/dim]",
            format_tokens(out) if out else "[dim]—[/dim]",
            format_tokens(cache_r) if cache_r else "[dim]—[/dim]",
            format_tokens(cache_w) if cache_w else "[dim]—[/dim]",
            format_cost(day_cost) if day_cost > 0 else "[dim]—[/dim]",
        )

    total_msgs = sum(d["messages"] for d in daily)
    total_sessions = sum(d["sessions"] for d in daily)
    active_days = sum(1 for d in daily if d["messages"] > 0)

    summary = Text()
    summary.append(f"  {total_msgs}", style="bold green")
    summary.append(" messages  •  ")
    summary.append(f"{total_sessions}", style="bold blue")
    summary.append(" sessions  •  ")
    summary.append(f"{active_days}", style="bold")
    summary.append(" active days  •  ")
    summary.append(f"{format_cost(total_cost)}", style="bold red")
    summary.append(" est. cost")

    console.print()
    console.print(table)
    console.print(summary)
    console.print()
