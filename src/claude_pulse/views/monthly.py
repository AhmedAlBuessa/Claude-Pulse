"""Monthly usage view."""

from collections import defaultdict
from datetime import datetime

from rich.console import Console
from rich.table import Table
from rich.text import Text

from claude_pulse.cost import calculate_cost_raw, format_cost, format_tokens
from claude_pulse.data.conversations import load_all_conversations
from claude_pulse.data.history import group_by_date, load_history


def render_monthly(console: Console):
    """Render the monthly aggregation table."""
    entries = load_history()
    by_date = group_by_date(entries)
    conversations = load_all_conversations()

    # Aggregate messages by month from history
    monthly: dict[str, dict] = defaultdict(lambda: {
        "messages": 0,
        "sessions": set(),
        "active_days": 0,
    })

    for date_str, day_entries in by_date.items():
        month = date_str[:7]
        monthly[month]["messages"] += len(day_entries)
        monthly[month]["sessions"].update(e.session_id for e in day_entries if e.session_id)
        monthly[month]["active_days"] += 1

    # Aggregate tokens by month from conversations
    monthly_tokens: dict[str, dict] = defaultdict(lambda: {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_create_tokens": 0,
        "tool_calls": 0,
        "models": set(),
    })

    for conv in conversations:
        for usage in conv.usage:
            if not usage.timestamp:
                continue
            month = usage.timestamp[:7]
            monthly_tokens[month]["input_tokens"] += usage.input_tokens
            monthly_tokens[month]["output_tokens"] += usage.output_tokens
            monthly_tokens[month]["cache_read_tokens"] += usage.cache_read_tokens
            monthly_tokens[month]["cache_create_tokens"] += usage.cache_create_tokens
            if usage.model:
                monthly_tokens[month]["models"].add(usage.model)
        # Attribute tool calls to the conversation's last month
        if conv.last_timestamp:
            month = conv.last_timestamp[:7]
            monthly_tokens[month]["tool_calls"] += conv.tool_calls

    all_months = sorted(set(list(monthly.keys()) + list(monthly_tokens.keys())))

    if not all_months:
        console.print("\n  [dim]No usage data found.[/dim]\n")
        return

    table = Table(
        title="Monthly Usage",
        title_style="bold cyan",
        show_lines=True,
        padding=(0, 1),
    )
    table.add_column("Month", style="bold", min_width=10)
    table.add_column("Messages", justify="right", style="green")
    table.add_column("Sessions", justify="right", style="blue")
    table.add_column("Active Days", justify="right", style="white")
    table.add_column("Tool Calls", justify="right", style="yellow")
    table.add_column("Output Tokens", justify="right", style="magenta")
    table.add_column("Est. Cost", justify="right", style="red")

    current_month = datetime.now().strftime("%Y-%m")
    grand_total_cost = 0.0

    for month in all_months:
        msg_data = monthly.get(month, {"messages": 0, "sessions": set(), "active_days": 0})
        tok_data = monthly_tokens.get(month, {
            "input_tokens": 0, "output_tokens": 0,
            "cache_read_tokens": 0, "cache_create_tokens": 0,
            "tool_calls": 0, "models": set(),
        })

        sessions = len(msg_data["sessions"]) if isinstance(msg_data["sessions"], set) else 0
        models = tok_data.get("models", set())
        model = next(iter(models)) if models else "claude-sonnet-4-6"
        cost = calculate_cost_raw(
            model,
            tok_data["input_tokens"],
            tok_data["output_tokens"],
            tok_data["cache_read_tokens"],
            tok_data["cache_create_tokens"],
        )
        grand_total_cost += cost

        month_display = f"[bold]{month}[/bold]" if month == current_month else month

        table.add_row(
            month_display,
            str(msg_data["messages"]),
            str(sessions),
            str(msg_data["active_days"]),
            str(tok_data["tool_calls"]) if tok_data["tool_calls"] else "—",
            format_tokens(tok_data["output_tokens"]) if tok_data["output_tokens"] else "—",
            format_cost(cost) if cost > 0 else "—",
        )

    # Totals
    total_msgs = sum(
        monthly.get(m, {"messages": 0})["messages"] for m in all_months
    )

    summary = Text()
    summary.append(f"  {total_msgs}", style="bold green")
    summary.append(" total messages  •  ")
    summary.append(f"{len(all_months)}", style="bold")
    summary.append(" months  •  ")
    summary.append(f"{format_cost(grand_total_cost)}", style="bold red")
    summary.append(" total est. cost")

    console.print()
    console.print(table)
    console.print(summary)
    console.print()
