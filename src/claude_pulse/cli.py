"""CLI entry point for Claude Pulse."""

import json
import sys

import click
from rich.console import Console
from rich.theme import Theme

from claude_pulse import __version__
from claude_pulse.config import DEFAULT_DAYS, DEFAULT_REFRESH

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
    type=click.Choice(["realtime", "daily", "monthly"], case_sensitive=False),
    default="realtime",
    help="Display mode.",
)
@click.option("-d", "--days", type=int, default=DEFAULT_DAYS, help="Days to show (daily view).")
@click.option(
    "-t", "--theme",
    type=click.Choice(["light", "dark", "auto"], case_sensitive=False),
    default="auto",
    help="Color theme.",
)
@click.option("-r", "--refresh", type=float, default=DEFAULT_REFRESH, help="Refresh interval in seconds.")
@click.option("-p", "--project", type=str, default=None, help="Filter by project path.")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON.")
@click.version_option(version=__version__, prog_name="claude-pulse")
def main(view, days, theme, refresh, project, as_json):
    """Monitor your Claude Code usage."""
    console = _get_console(theme)

    if as_json:
        _output_json(days, project)
        return

    if view == "daily":
        from claude_pulse.views.daily import render_daily
        render_daily(console, days=days, project=project)
    elif view == "monthly":
        from claude_pulse.views.monthly import render_monthly
        render_monthly(console)
    else:
        from claude_pulse.views.realtime import render_realtime
        render_realtime(console, refresh=refresh)


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
