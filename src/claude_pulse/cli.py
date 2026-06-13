"""CLI entry point for Claude Pulse."""

import json
import sys

import click
from rich.console import Console
from rich.theme import Theme

from claude_pulse import __version__
from claude_pulse.config import DEFAULT_DAYS, DEFAULT_PLAN, DEFAULT_REFRESH

DARK_THEME = Theme({
    "info": "cyan",
    "warning": "yellow",
    "error": "red bold",
})

LIGHT_THEME = Theme({
    "info": "blue",
    "warning": "dark_orange",
    "error": "red bold",
})


def _get_console(theme: str) -> Console:
    if theme == "light":
        return Console(theme=LIGHT_THEME)
    elif theme == "dark":
        return Console(theme=DARK_THEME)
    return Console()


@click.command()
@click.option(
    "-v", "--view",
    type=click.Choice(["realtime", "daily", "monthly", "sessions"], case_sensitive=False),
    default="realtime",
    help="Display mode.",
)
@click.option("-d", "--days", type=int, default=DEFAULT_DAYS, help="Days to show (daily/sessions view).")
@click.option("--list-only", is_flag=True, help="Sessions view: list without prompting to resume.")
@click.option(
    "-t", "--theme",
    type=click.Choice(["light", "dark", "auto"], case_sensitive=False),
    default="auto",
    help="Color theme.",
)
@click.option("-r", "--refresh", type=float, default=DEFAULT_REFRESH, help="Refresh interval in seconds.")
@click.option("-p", "--project", type=str, default=None, help="Filter by project path.")
@click.option(
    "--plan",
    type=click.Choice(["pro", "max5", "max20"], case_sensitive=False),
    default=DEFAULT_PLAN,
    help="Subscription plan for limit tracking.",
)
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON.")
@click.option(
    "--calibrate",
    type=float,
    default=None,
    metavar="PERCENT",
    help="Calibrate the session limit: pass the %% claude.ai/usage shows right now.",
)
@click.option("--check-usage", is_flag=True, help="Diagnose live session-usage and exit.")
@click.version_option(version=__version__, prog_name="claude-pulse")
def main(view, days, list_only, theme, refresh, project, plan, as_json, calibrate, check_usage):
    """Monitor your Claude Code usage."""
    console = _get_console(theme)

    if check_usage:
        _check_usage(console)
        return

    if calibrate is not None:
        _calibrate(console, plan, calibrate)
        return

    if as_json:
        _output_json(days, project)
        return

    if view == "daily":
        from claude_pulse.views.daily import render_daily
        render_daily(console, days=days, project=project)
    elif view == "monthly":
        from claude_pulse.views.monthly import render_monthly
        render_monthly(console)
    elif view == "sessions":
        from claude_pulse.views.sessions import render_sessions
        # Default to a one-month window for browsing unless overridden.
        window = days if days != DEFAULT_DAYS else 30
        render_sessions(console, days=window, project=project, list_only=list_only)
    else:
        from claude_pulse.views.realtime import render_realtime
        render_realtime(console, refresh=refresh, plan=plan)


def _check_usage(console: Console):
    """Diagnose why live session-usage is or isn't available."""
    from claude_pulse.data.limits import get_usage_status

    status = get_usage_status()
    console.print("[bold]Claude Pulse — live usage check[/bold]")
    console.print(f"[dim]platform   :[/dim] {status['platform']}")
    console.print(f"[dim]credentials:[/dim] {status['source']}")

    if status["reason"] == "ok":
        d = status["data"]
        console.print("[info]✓ Live usage is working.[/info]")
        if d.get("subscription"):
            console.print(f"[dim]plan       :[/dim] {d['subscription']}")
        fh = d.get("five_hour_pct")
        sd = d.get("seven_day_pct")
        if fh is not None:
            console.print(f"[dim]5-hour     :[/dim] {fh:g}% used")
        if sd is not None:
            console.print(f"[dim]7-day      :[/dim] {sd:g}% used")
        console.print("\n[dim]The dashboard will show these as the live bar.[/dim]")
    else:
        console.print(f"[warning]✗ Live usage unavailable[/warning] [dim]({status['reason']})[/dim]")
        console.print(f"  {status['message']}")
        console.print(
            "\n[dim]The dashboard falls back to a token estimate. You can set a manual "
            "baseline with[/dim] [bold]acp --calibrate <percent>[/bold][dim] "
            "(the % from claude.ai/usage).[/dim]"
        )


def _calibrate(console: Console, plan: str, website_pct: float):
    """Back-solve the real session limit from the % claude.ai/usage shows now.

    Anthropic's session-usage percentage isn't available locally, so we infer
    the limit: if the website says you're at P% and we measure U output tokens
    in the current window, then 100% ~= U / (P/100).
    """
    from claude_pulse.config import PLAN_LIMITS, save_calibrated_limit
    from claude_pulse.data.conversations import (
        get_rolling_window_usage,
        load_all_conversations,
    )

    if not (0 < website_pct <= 100):
        console.print("[error]--calibrate expects a percentage between 0 and 100[/error]")
        console.print("[dim]Read the current value from https://claude.ai/usage[/dim]")
        return

    plan_info = PLAN_LIMITS.get(plan, PLAN_LIMITS["max5"])
    window = get_rolling_window_usage(
        load_all_conversations(), window_hours=plan_info["window_hours"]
    )
    used = window["output_tokens"]
    if used <= 0:
        console.print("[warning]No usage in the current window — run Claude a bit, then calibrate.[/warning]")
        return

    limit = int(round(used / (website_pct / 100)))
    save_calibrated_limit(limit)
    console.print(
        f"[info]Calibrated[/info] from {website_pct:g}% "
        f"({used:,} output tokens in the last {plan_info['window_hours']}h)."
    )
    console.print(f"[info]Session limit set to[/info] {limit:,} output tokens / "
                  f"{plan_info['window_hours']}h window.")
    console.print("[dim]Re-run `acp` to see the calibrated bar. Recalibrate any time the website drifts.[/dim]")


def _output_json(days: int, project: str = None):
    """Output usage data as JSON."""
    from claude_pulse.cost import calculate_cost_raw
    from claude_pulse.data.conversations import (
        get_daily_usage,
        get_model_totals,
        load_all_conversations,
    )
    from claude_pulse.data.sessions import get_active_sessions

    conversations = load_all_conversations()
    sessions = get_active_sessions()
    daily = get_daily_usage(conversations, days=days)
    model_totals = get_model_totals(conversations)

    daily_merged = []
    for d in daily:
        daily_merged.append({
            "date": d["date"],
            "messages": d["messages"],
            "sessions": d["sessions"],
            "input_tokens": d["input_tokens"],
            "output_tokens": d["output_tokens"],
            "cache_read_tokens": d["cache_read_tokens"],
            "cache_create_tokens": d["cache_create_tokens"],
        })

    output = {
        "daily": daily_merged,
        "active_sessions": [
            {
                "pid": s.pid,
                "project": s.project_name,
                "cwd": s.cwd,
                "started_at": s.started_at,
            }
            for s in sessions
        ],
        "model_usage": {},
        "totals": {
            "conversations": len(conversations),
            "messages": sum(c.messages for c in conversations),
            "tool_calls": sum(c.tool_calls for c in conversations),
        },
    }

    for model_id, tokens in model_totals.items():
        output["model_usage"][model_id] = {
            "input_tokens": tokens["input_tokens"],
            "output_tokens": tokens["output_tokens"],
            "cache_read_tokens": tokens["cache_read_tokens"],
            "cache_create_tokens": tokens["cache_create_tokens"],
            "estimated_cost_usd": round(calculate_cost_raw(
                model_id,
                tokens["input_tokens"],
                tokens["output_tokens"],
                tokens["cache_read_tokens"],
                tokens["cache_create_tokens"],
            ), 4),
        }

    json.dump(output, sys.stdout, indent=2)
    print()
