"""Sessions browser — list past sessions, pick one, and resume it."""

import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone

from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text

from claude_pulse.config import short_model_name
from claude_pulse.data.browse import SessionSummary, list_sessions


def _relative_time(dt: datetime) -> str:
    """Compact 'time ago' string from an aware datetime."""
    if dt is None:
        return "—"
    now = datetime.now(timezone.utc)
    delta = now - dt
    secs = int(delta.total_seconds())
    if secs < 60:
        return "just now"
    mins = secs // 60
    if mins < 60:
        return f"{mins}m ago"
    hours = mins // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    if days == 1:
        return "yesterday"
    if days < 7:
        return f"{days}d ago"
    if days < 31:
        return f"{days // 7}w ago"
    if days < 365:
        return f"{days // 30}mo ago"
    return f"{days // 365}y ago"


def _truncate(text: str, width: int) -> str:
    text = text.strip()
    return text if len(text) <= width else text[: width - 1] + "…"


def render_sessions(
    console: Console,
    days: int = 30,
    project: str = None,
    list_only: bool = False,
):
    """List past sessions and (interactively) resume a selected one."""
    sessions = list_sessions(days=days, project=project)

    window = f"Last {days} Days" if days else "All Time"
    scope = f" · {project}" if project else ""
    table = Table(
        title=f"Past Sessions ({window}{scope})",
        title_style="bold cyan",
        show_lines=False,
        padding=(0, 1),
    )
    table.add_column("#", justify="right", style="bold cyan", min_width=2)
    table.add_column("Last Active", style="green", min_width=11)
    table.add_column("Project", style="blue", max_width=22)
    table.add_column("Msgs", justify="right", style="magenta")
    table.add_column("Model", style="yellow", max_width=12)
    table.add_column("What you were working on", style="white", max_width=52)

    if not sessions:
        console.print()
        console.print(f"[yellow]No sessions found in the last {days} days.[/yellow]")
        console.print("[dim]Try a wider window, e.g.[/dim] acp -v sessions -d 90")
        console.print()
        return

    for idx, s in enumerate(sessions, start=1):
        model = short_model_name(next(iter(s.models))) if s.models else "—"
        when = s.last_active.astimezone() if s.last_active else None
        when_str = _relative_time(s.last_active)
        date_hint = f" [dim]{when.strftime('%b %d')}[/dim]" if when else ""
        table.add_row(
            str(idx),
            f"{when_str}{date_hint}",
            _truncate(s.project_name, 22),
            str(s.message_count),
            model,
            _truncate(s.title, 52),
        )

    console.print()
    console.print(table)

    footer = Text()
    footer.append(f"  {len(sessions)}", style="bold green")
    footer.append(" sessions  •  pick a ")
    footer.append("#", style="bold cyan")
    footer.append(" to resume, or ")
    footer.append("q", style="bold")
    footer.append(" to quit")
    console.print(footer)
    console.print()

    # Non-interactive (piped/CI) or explicit list-only: stop after printing.
    if list_only or not sys.stdin.isatty():
        return

    choice = Prompt.ask(
        "[bold cyan]Resume which session[/bold cyan]",
        default="q",
        console=console,
    ).strip().lower()

    if choice in ("q", "quit", "", "n", "no"):
        return

    if not choice.isdigit() or not (1 <= int(choice) <= len(sessions)):
        console.print(f"[error]'{choice}' is not a valid number.[/error]")
        return

    console.print()
    console.print("  [bold cyan]1[/bold cyan]  Normal              [dim]claude --resume[/dim]")
    console.print(
        "  [bold cyan]2[/bold cyan]  Skip permissions    "
        "[dim]claude --resume --dangerously-skip-permissions[/dim]"
    )
    mode = Prompt.ask(
        "[bold cyan]Launch how[/bold cyan]",
        choices=["1", "2", "q"],
        default="1",
        console=console,
    ).strip().lower()

    if mode in ("q", "quit"):
        return

    _resume(console, sessions[int(choice) - 1], skip_permissions=(mode == "2"))


def _resume(console: Console, session: SessionSummary, skip_permissions: bool = False):
    """Launch `claude --resume <id>` in the session's working directory."""
    cwd = session.cwd or os.getcwd()
    extra_args = ["--dangerously-skip-permissions"] if skip_permissions else []
    cmd_display = " ".join(["claude", "--resume", session.session_id, *extra_args])

    console.print()
    console.print(f"[bold]Resuming:[/bold] {_truncate(session.title, 70)}")
    console.print(f"[dim]Folder :[/dim] {cwd}")
    console.print(f"[dim]Command:[/dim] {cmd_display}")
    console.print()

    if not os.path.isdir(cwd):
        console.print(f"[error]Project folder no longer exists:[/error] {cwd}")
        console.print(f"[dim]Run manually once the folder is back:[/dim] {cmd_display}")
        return

    claude_exe = shutil.which("claude")
    if not claude_exe:
        console.print("[warning]Couldn't find the 'claude' command on your PATH.[/warning]")
        console.print("[dim]Open a terminal in the folder above and run:[/dim]")
        console.print(f"  cd {cwd}")
        console.print(f"  {cmd_display}")
        return

    try:
        if os.name == "nt":
            # claude is a .cmd shim on Windows; run through the shell so PATH
            # resolution and the .cmd extension are handled correctly.
            subprocess.run(
                cmd_display,
                cwd=cwd, shell=True, check=False,
            )
        else:
            subprocess.run(
                [claude_exe, "--resume", session.session_id, *extra_args],
                cwd=cwd, check=False,
            )
    except (OSError, subprocess.SubprocessError) as exc:
        console.print(f"[error]Failed to launch Claude:[/error] {exc}")
        console.print(f"[dim]Run manually:[/dim] cd {cwd} && {cmd_display}")
