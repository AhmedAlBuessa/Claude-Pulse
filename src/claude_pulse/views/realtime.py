"""Real-time TUI dashboard — htop/btop style with responsive layout."""

import time
from datetime import datetime, timedelta

from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from claude_pulse.config import PLAN_LIMITS, short_model_name
from claude_pulse.cost import calculate_cost_raw, format_cost, format_tokens
from claude_pulse.data.conversations import (
    get_daily_usage,
    get_hourly_activity,
    get_model_totals,
    get_project_stats,
    get_rolling_window_usage,
    load_all_conversations,
)
from claude_pulse.data.sessions import get_active_sessions


# ── Helpers ──────────────────────────────────────────────────────────────────


def _format_duration(ms: int) -> str:
    seconds = ms // 1000
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m {seconds % 60}s"
    hours = minutes // 60
    return f"{hours}h {minutes % 60}m"


def _compact_cost(usd: float) -> str:
    """Shorter cost format for tight spaces."""
    if usd >= 100:
        return f"${usd:.0f}"
    if usd >= 10:
        return f"${usd:.1f}"
    if usd < 0.01:
        return f"${usd:.3f}"
    return f"${usd:.2f}"


# ── Panel Builders ───────────────────────────────────────────────────────────


def _build_header(sessions: list, now: datetime, total_cost: float, today_msgs: int, width: int) -> Panel:
    parts = []
    parts.append(f"[bold green]●[/bold green] {len(sessions)} sess")
    parts.append(f"[bold green]{today_msgs:,}[/bold green] today")
    parts.append(f"[bold red]{format_cost(total_cost)}[/bold red] total")
    if width >= 80:
        parts.append(f"[dim]{now.strftime('%a %b %d  %I:%M:%S %p')}[/dim]")
    else:
        parts.append(f"[dim]{now.strftime('%I:%M:%S %p')}[/dim]")

    sep = "  " if width < 80 else "    "
    return Panel(
        Text.from_markup(sep.join(parts), justify="center"),
        title="[bold cyan] Claude Pulse [/bold cyan]",
        border_style="bold cyan",
        padding=(0, 0),
    )


def _build_sessions_panel(sessions: list, now: datetime, compact: bool = False) -> Panel:
    table = Table(
        show_header=True, header_style="bold",
        padding=(0, 1), show_lines=False, expand=True,
    )
    if compact:
        table.add_column("Project", style="bold green", no_wrap=True, overflow="ellipsis")
        table.add_column("Dur", justify="right", style="cyan")
    else:
        table.add_column("PID", style="dim", justify="right", ratio=1)
        table.add_column("Project", style="bold green", ratio=3, no_wrap=True, overflow="ellipsis")
        table.add_column("Duration", justify="right", style="cyan", ratio=2)

    if sessions:
        now_ms = int(now.timestamp() * 1000)
        for s in sessions:
            dur = _format_duration(now_ms - s.started_at) if s.started_at else "—"
            proj = s.project_name or s.cwd
            if compact:
                table.add_row(proj, dur)
            else:
                table.add_row(str(s.pid), proj, dur)
    else:
        if compact:
            table.add_row("[dim]None[/dim]", "—")
        else:
            table.add_row("—", "[dim]No active sessions[/dim]", "—")

    return Panel(table, title="[bold] Sessions [/bold]", border_style="green", padding=(0, 0))


def _build_tokens_panel(model_totals: dict, compact: bool = False) -> Panel:
    table = Table(
        show_header=True, header_style="bold",
        padding=(0, 1), show_lines=False, expand=True,
    )

    if compact:
        table.add_column("Model", style="bold", no_wrap=True, overflow="ellipsis")
        table.add_column("Out", justify="right", style="blue")
        table.add_column("$", justify="right", style="bold red")
    else:
        table.add_column("Model", style="bold", ratio=2, no_wrap=True, overflow="ellipsis")
        table.add_column("Input", justify="right", style="green", ratio=1)
        table.add_column("Output", justify="right", style="blue", ratio=1)
        table.add_column("Cache R", justify="right", style="yellow", ratio=1)
        table.add_column("Cache W", justify="right", style="yellow", ratio=1)
        table.add_column("Cost", justify="right", style="bold red", min_width=7)

    total_cost = 0.0
    for model_id, tokens in model_totals.items():
        if sum(tokens.values()) == 0:
            continue
        cost = calculate_cost_raw(
            model_id,
            tokens["input_tokens"], tokens["output_tokens"],
            tokens["cache_read_tokens"], tokens["cache_create_tokens"],
        )
        total_cost += cost
        if compact:
            table.add_row(
                short_model_name(model_id),
                format_tokens(tokens["output_tokens"]),
                _compact_cost(cost),
            )
        else:
            table.add_row(
                short_model_name(model_id),
                format_tokens(tokens["input_tokens"]),
                format_tokens(tokens["output_tokens"]),
                format_tokens(tokens["cache_read_tokens"]),
                format_tokens(tokens["cache_create_tokens"]),
                format_cost(cost),
            )

    active_models = sum(1 for t in model_totals.values() if sum(t.values()) > 0)
    if active_models > 1:
        if compact:
            table.add_row("[bold]TOTAL[/bold]", "", f"[bold red]{_compact_cost(total_cost)}[/bold red]")
        else:
            table.add_row("[bold]TOTAL[/bold]", "", "", "", "", f"[bold red]{format_cost(total_cost)}[/bold red]")

    return Panel(table, title="[bold] Tokens [/bold]", border_style="blue", padding=(0, 0))


def _build_daily_chart(daily: list, hours: list, width: int) -> Panel:
    values = [d["messages"] for d in daily]
    costs = []
    for d in daily:
        models = d.get("models", set())
        model = next(iter(models)) if models else "claude-sonnet-4-6"
        c = calculate_cost_raw(
            model, d["input_tokens"], d["output_tokens"],
            d["cache_read_tokens"], d["cache_create_tokens"],
        )
        costs.append(c)

    text = Text()
    if not values:
        text.append("  No data")
        return Panel(text, title="[bold] Activity [/bold]", border_style="yellow")

    max_val = max(values) or 1
    panel_inner = max(width // 2 - 6, 20) if width >= 80 else max(width - 6, 15)
    bar_width = max(panel_inner - 24, 8)
    today_str = datetime.now().strftime("%m-%d")
    total_cost = sum(costs)
    total_msgs = sum(values)
    show_cost = width >= 60

    for i, (day_data, cost) in enumerate(zip(reversed(daily), reversed(costs))):
        val = day_data["messages"]
        label = day_data["date"][-5:]
        bar_len = int(val / max_val * bar_width) if max_val > 0 else 0
        bar = "█" * bar_len
        pad = "░" * (bar_width - bar_len) if val > 0 else " " * bar_width

        is_today = label == today_str
        text.append(f" {label} ", style="bold white" if is_today else "dim")
        text.append(bar, style="bold green" if is_today else "green")
        text.append(pad, style="dim green" if val > 0 else "dim")
        text.append(f" {val:>4}", style="bold" if is_today else "")
        if show_cost and cost > 0:
            text.append(f" {_compact_cost(cost):>6}", style="red")
        text.append("\n")

    text.append(f" {'─' * min(bar_width + 18, 50)}\n", style="dim")
    text.append(" ", style="dim")
    text.append(f"{total_msgs:,}", style="bold green")
    text.append(" msgs ", style="dim")
    if show_cost:
        text.append(f"{_compact_cost(total_cost)}", style="bold red")
    text.append("\n\n")

    # Hourly heatmap inline
    max_h = max(hours) or 1
    blocks = ["  ", "░░", "▒▒", "▓▓", "██"]

    if width >= 80:
        for row_label, start in [("AM", 0), ("PM", 12)]:
            text.append(f" {row_label} ", style="dim")
            for h in range(start, start + 12):
                val = hours[h]
                if val == 0:
                    text.append("·· ", style="dim")
                else:
                    idx = max(1, min(int(val / max_h * 4), 4))
                    style = "bold magenta" if val == max_h else ("magenta" if idx >= 3 else "cyan")
                    text.append(f"{blocks[idx]} ", style=style)
            text.append("\n")
        text.append("    ", style="dim")
        for h in range(12):
            text.append(f"{h:<3}", style="dim")
        text.append("\n")
    else:
        # Compact sparkline
        bars = "▁▂▃▄▅▆▇█"
        text.append(" Hr ", style="dim")
        for h in range(24):
            val = hours[h]
            if val == 0:
                text.append("·", style="dim")
            else:
                idx = max(1, min(int(val / max_h * 7), 7))
                style = "bold magenta" if val == max_h else ("magenta" if idx >= 5 else "cyan")
                text.append(bars[idx], style=style)
        text.append("\n")
        text.append("    0     6     12    18  23\n", style="dim")

    peak_hour = hours.index(max(hours))
    text.append(f" Peak ", style="dim")
    text.append(f"{peak_hour:02d}:00", style="bold magenta")
    text.append(f" ({max(hours)} msgs/7d)", style="dim")

    return Panel(text, title="[bold] Activity [/bold]", border_style="yellow", padding=(0, 0))


def _build_projects_panel(project_stats: list, compact: bool = False) -> Panel:
    table = Table(
        show_header=True, header_style="bold",
        padding=(0, 1), show_lines=False, expand=True,
    )

    if compact:
        table.add_column("Project", style="bold", no_wrap=True, overflow="ellipsis")
        table.add_column("Msgs", justify="right", style="green")
        table.add_column("$", justify="right", style="red")
    else:
        table.add_column("Project", style="bold", ratio=3, no_wrap=True, overflow="ellipsis")
        table.add_column("Msgs", justify="right", style="green", ratio=1)
        table.add_column("Tools", justify="right", style="yellow", ratio=1)
        table.add_column("Cost", justify="right", style="red", ratio=1)
        table.add_column("Last", style="dim", ratio=2, no_wrap=True)

    limit = 5 if compact else 8
    for p in project_stats[:limit]:
        last = p["last_active"][:10] if p["last_active"] else "—"
        if compact:
            table.add_row(p["project"], str(p["user_messages"]), _compact_cost(p["cost"]))
        else:
            table.add_row(p["project"], str(p["user_messages"]), str(p["tool_calls"]), format_cost(p["cost"]), last)

    return Panel(table, title="[bold] Projects [/bold]", border_style="white", padding=(0, 0))


def _build_stats_panel(conversations: list, total_cost: float, today_cost: float, compact: bool = False) -> Panel:
    total_user = sum(c.user_messages for c in conversations)
    total_assistant = sum(c.assistant_messages for c in conversations)
    total_tools = sum(c.tool_calls for c in conversations)
    total_output = sum(c.total_output_tokens for c in conversations)
    total_cache = sum(c.total_cache_read_tokens for c in conversations)

    text = Text()

    if compact:
        text.append(" Convos  ", style="dim")
        text.append(f"{len(conversations):>6,}\n", style="bold")
        text.append(" Prompts ", style="dim")
        text.append(f"{total_user:>6,}\n", style="bold green")
        text.append(" Tools   ", style="dim")
        text.append(f"{total_tools:>6,}\n", style="bold yellow")
        text.append(" Output  ", style="dim")
        text.append(f"{format_tokens(total_output):>6}\n", style="bold")
        text.append(" ─────────────\n", style="dim")
        text.append(" Today   ", style="dim")
        text.append(f"{_compact_cost(today_cost):>6}\n", style="bold red")
        text.append(" Total   ", style="dim")
        text.append(f"{_compact_cost(total_cost):>6}\n", style="bold red")
    else:
        text.append("  Conversations   ", style="dim")
        text.append(f"{len(conversations):>8,}\n", style="bold")
        text.append("  User Prompts    ", style="dim")
        text.append(f"{total_user:>8,}\n", style="bold green")
        text.append("  AI Responses    ", style="dim")
        text.append(f"{total_assistant:>8,}\n", style="bold blue")
        text.append("  Tool Calls      ", style="dim")
        text.append(f"{total_tools:>8,}\n", style="bold yellow")
        text.append("  Output Tokens   ", style="dim")
        text.append(f"{format_tokens(total_output):>8}\n", style="bold")
        text.append("  Cache Reads     ", style="dim")
        text.append(f"{format_tokens(total_cache):>8}\n", style="bold")
        text.append("  ─────────────────────\n", style="dim")
        text.append("  Today's Cost    ", style="dim")
        text.append(f"{format_cost(today_cost):>8}\n", style="bold red")
        text.append("  Total Cost      ", style="dim")
        text.append(f"{format_cost(total_cost):>8}\n", style="bold red")

    return Panel(text, title="[bold] Stats [/bold]", border_style="cyan", padding=(0, 0))


def _build_plan_panel(window_usage: dict, plan: str, conversations: list,
                      total_cost: float, today_cost: float, compact: bool = False) -> Panel:
    """Build the usage + burn rate + stats panel."""
    plan_info = PLAN_LIMITS.get(plan, PLAN_LIMITS["max5"])
    plan_name = plan_info["name"]
    limit = plan_info["output_tokens"]
    window_h = plan_info["window_hours"]
    used = window_usage["output_tokens"]
    pct = min(used / limit * 100, 100) if limit > 0 else 0
    remaining = max(limit - used, 0)

    # Burn rate
    elapsed_min = window_usage["elapsed_minutes"]
    msgs_in_window = window_usage["messages"]
    if elapsed_min > 0 and msgs_in_window > 0:
        tokens_per_min = used / elapsed_min
        tokens_per_hour = tokens_per_min * 60
        if tokens_per_min > 0 and remaining > 0:
            mins_left = remaining / tokens_per_min
            hours_left = int(mins_left // 60)
            mins_rem = int(mins_left % 60)
            eta_str = f"{hours_left}h {mins_rem}m" if hours_left > 0 else f"{mins_rem}m"
        else:
            eta_str = "at limit" if remaining == 0 else "∞"
    else:
        tokens_per_hour = 0
        eta_str = "idle"

    # Color based on percentage
    if pct >= 90:
        bar_color, pct_color = "bold red", "bold red"
    elif pct >= 70:
        bar_color, pct_color = "yellow", "bold yellow"
    elif pct >= 40:
        bar_color, pct_color = "cyan", "bold cyan"
    else:
        bar_color, pct_color = "green", "bold green"

    # Stats
    total_user = sum(c.user_messages for c in conversations)
    total_tools = sum(c.tool_calls for c in conversations)

    text = Text()

    if compact:
        bar_w = 20
        filled = int(pct / 100 * bar_w)
        empty = bar_w - filled
        text.append(f" {plan_name} ", style="bold")
        text.append(f"~{pct:.0f}%\n", style=pct_color)
        text.append(" ", style="dim")
        text.append("█" * filled, style=bar_color)
        text.append("░" * empty, style="dim")
        text.append(f"\n")
        text.append(f" Burn ", style="dim")
        if tokens_per_hour > 0:
            text.append(f"{format_tokens(int(tokens_per_hour))}/hr\n", style="bold")
        else:
            text.append(f"idle\n", style="dim")
        text.append(f" ─────────────\n", style="dim")
        text.append(f" Today ", style="dim")
        text.append(f"{_compact_cost(today_cost):>6}\n", style="bold red")
        text.append(f" Total ", style="dim")
        text.append(f"{_compact_cost(total_cost):>6}\n", style="bold red")
    else:
        bar_w = 30
        filled = int(pct / 100 * bar_w)
        empty = bar_w - filled

        # Header
        text.append(f"  {plan_name}", style="bold")
        text.append(f"  {window_h}h window\n", style="dim")

        # Progress bar
        text.append("  ", style="dim")
        text.append("█" * filled, style=bar_color)
        text.append("░" * empty, style="dim")
        text.append(f" ~{pct:.0f}%\n", style=pct_color)

        # Usage line
        text.append(f"  {format_tokens(used)}", style="bold")
        text.append(f" / ~{format_tokens(limit)}", style="dim")
        text.append(f"   ETA: ", style="dim")
        text.append(f"{eta_str}\n", style=pct_color)

        # Burn rate
        text.append(f"  Burn: ", style="dim")
        if tokens_per_hour > 0:
            text.append(f"{format_tokens(int(tokens_per_hour))}/hr", style="bold")
        else:
            text.append(f"idle", style="dim")
        text.append(f"   Msgs: ", style="dim")
        text.append(f"{msgs_in_window}\n", style="bold")

        text.append(f"  ─────────────────────────────\n", style="dim")

        # Key stats
        text.append(f"  Convos ", style="dim")
        text.append(f"{len(conversations):>5,}", style="bold")
        text.append(f"   Prompts ", style="dim")
        text.append(f"{total_user:>6,}\n", style="bold green")
        text.append(f"  Tools  ", style="dim")
        text.append(f"{total_tools:>5,}", style="bold yellow")
        text.append(f"   Today   ", style="dim")
        text.append(f"{format_cost(today_cost):>6}\n", style="bold red")
        text.append(f"  Total  ", style="dim")
        text.append(f"{format_cost(total_cost):>5}\n", style="bold red")

    border_color = "red" if pct >= 90 else ("yellow" if pct >= 70 else ("cyan" if pct >= 40 else "green"))
    return Panel(text, title=f"[bold] Usage & Stats [/bold]", border_style=border_color, padding=(0, 0))


# ── Layout Builders ──────────────────────────────────────────────────────────


def _build_wide(data: dict) -> Layout:
    """Wide layout (120+): Plan+Stats+Tokens top, Activity+Sessions+Projects bottom."""
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="upper", ratio=2),
        Layout(name="lower", ratio=3),
    )
    layout["header"].update(data["header"])

    # Upper: Plan+Stats combined + Tokens
    layout["upper"].split_row(
        Layout(name="plan", ratio=2),
        Layout(name="tokens", ratio=3),
    )
    layout["plan"].update(data["plan"])
    layout["tokens"].update(data["tokens"])

    # Lower: Activity (daily+hours) left, Sessions+Projects right
    layout["lower"].split_row(
        Layout(name="daily", ratio=3),
        Layout(name="right_col", ratio=3),
    )
    layout["daily"].update(data["daily"])
    layout["right_col"].split_column(
        Layout(name="sessions", ratio=1),
        Layout(name="projects", ratio=2),
    )
    layout["sessions"].update(data["sessions"])
    layout["projects"].update(data["projects"])

    return layout


def _build_medium(data: dict) -> Layout:
    """Medium layout (80-119): 2-col stacked."""
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="row1", ratio=2),
        Layout(name="row2", ratio=3),
        Layout(name="row3", ratio=2),
    )
    layout["header"].update(data["header"])

    # Row 1: Plan+Stats left, Tokens right
    layout["row1"].split_row(
        Layout(name="plan", ratio=1),
        Layout(name="tokens", ratio=2),
    )
    layout["plan"].update(data["plan"])
    layout["tokens"].update(data["tokens"])

    # Row 2: Activity (daily+hours) left, Sessions right
    layout["row2"].split_row(
        Layout(name="daily", ratio=1),
        Layout(name="sessions", ratio=1),
    )
    layout["daily"].update(data["daily"])
    layout["sessions"].update(data["sessions"])

    # Row 3: Projects full width
    layout["row3"].update(data["projects"])

    return layout


def _build_narrow(data: dict) -> Layout:
    """Narrow layout (<80): single column, stacked."""
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="plan", size=9),
        Layout(name="tokens", ratio=1),
        Layout(name="sessions", size=max(4, len(data["_sessions_raw"]) + 3)),
        Layout(name="daily", ratio=2),
        Layout(name="projects", ratio=1),
    )
    layout["header"].update(data["header"])
    layout["plan"].update(data["plan"])
    layout["tokens"].update(data["tokens"])
    layout["sessions"].update(data["sessions"])
    layout["daily"].update(data["daily"])
    layout["projects"].update(data["projects"])

    return layout


# ── Main Dashboard ───────────────────────────────────────────────────────────


_slow_cache = {"ts": 0, "data": None}
_SLOW_CACHE_TTL = 15  # seconds


def _build_dashboard(console: Console, plan: str = "max5") -> Layout:
    """Build the dashboard, adapting layout to terminal width."""
    now = datetime.now()
    width = console.width
    compact = width < 100

    # Load conversations (fast with file-level cache)
    conversations = load_all_conversations()
    plan_info = PLAN_LIMITS.get(plan, PLAN_LIMITS["max5"])

    # Fast data (update every tick)
    sessions = get_active_sessions()
    window_usage = get_rolling_window_usage(conversations, window_hours=plan_info["window_hours"])
    model_totals = get_model_totals(conversations)

    # Slow data (cache for 15 seconds)
    cache_age = time.time() - _slow_cache["ts"]
    if _slow_cache["data"] is None or cache_age >= _SLOW_CACHE_TTL:
        _slow_cache["data"] = {
            "daily": get_daily_usage(conversations, days=14),
            "hourly": get_hourly_activity(conversations, days=7),
            "project_stats": get_project_stats(conversations),
        }
        _slow_cache["ts"] = time.time()

    daily = _slow_cache["data"]["daily"]
    hourly = _slow_cache["data"]["hourly"]
    project_stats = _slow_cache["data"]["project_stats"]

    # Calculate costs
    total_cost = 0.0
    for model_id, tokens in model_totals.items():
        if sum(tokens.values()) == 0:
            continue
        total_cost += calculate_cost_raw(
            model_id,
            tokens["input_tokens"], tokens["output_tokens"],
            tokens["cache_read_tokens"], tokens["cache_create_tokens"],
        )

    today_str = now.strftime("%Y-%m-%d")
    today_data = next((d for d in daily if d["date"] == today_str), None)
    today_msgs = today_data["messages"] if today_data else 0
    today_cost = 0.0
    if today_data:
        models = today_data.get("models", set())
        model = next(iter(models)) if models else "claude-sonnet-4-6"
        today_cost = calculate_cost_raw(
            model, today_data["input_tokens"], today_data["output_tokens"],
            today_data["cache_read_tokens"], today_data["cache_create_tokens"],
        )

    # Build panels with appropriate compactness
    data = {
        "header": _build_header(sessions, now, total_cost, today_msgs, width),
        "plan": _build_plan_panel(window_usage, plan, conversations, total_cost, today_cost, compact=compact),
        "sessions": _build_sessions_panel(sessions, now, compact=compact),
        "tokens": _build_tokens_panel(model_totals, compact=compact),
        "daily": _build_daily_chart(daily, hourly, width),
        "projects": _build_projects_panel(project_stats, compact=compact),
        "_sessions_raw": sessions,
    }

    if width >= 120:
        return _build_wide(data)
    elif width >= 80:
        return _build_medium(data)
    else:
        return _build_narrow(data)


def render_realtime(console: Console, refresh: float = 0.5, plan: str = "max5"):
    """Render the live-updating TUI dashboard."""
    try:
        with Live(
            _build_dashboard(console, plan=plan),
            console=console,
            refresh_per_second=4,
            screen=True,
        ) as live:
            while True:
                time.sleep(refresh)
                live.update(_build_dashboard(console, plan=plan))
    except KeyboardInterrupt:
        pass
