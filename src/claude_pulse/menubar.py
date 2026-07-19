"""macOS menu-bar usage indicator for Claude Pulse.

Shows the current rolling-window usage as a thin-line bar in the menu bar, e.g.
``━━━───────── 1%``, refreshing on a timer. Requires the
``[menubar]`` extra (``rumps``) and only runs on macOS.

Usage::

    acp-bar                # run the menu-bar app
    acp-bar --install      # install a LaunchAgent so it starts on login
    acp-bar --uninstall    # remove the LaunchAgent
"""

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from claude_pulse.config import (
    DEFAULT_PLAN,
    PLAN_LIMITS,
    load_live_snapshot,
    load_saved_plan,
    save_live_snapshot,
    save_selected_plan,
)
from claude_pulse.data.conversations import get_plan_usage
from claude_pulse.data.limits import get_live_usage

REFRESH_SECONDS = 60
BAR_WIDTH = 10  # keep short — a wide title gets hidden/truncated in the menu bar
# Reuse a disk-cached live value for this long before re-fetching. Each
# `--print` is a fresh process, so the in-memory cache never helps; without
# this we'd call the usage endpoint on every refresh and get rate-limited (429).
LIVE_CACHE_TTL = 150
LIVE_STALE_MAX = 10800  # accept a last-good value up to 3h old when a fetch fails
LAUNCH_AGENT_LABEL = "com.claudepulse.menubar"
LAUNCH_AGENT_PATH = Path.home() / "Library" / "LaunchAgents" / f"{LAUNCH_AGENT_LABEL}.plist"


def render_bar(pct: float, width: int = BAR_WIDTH) -> str:
    """Render a thin-line usage bar, e.g. ``━━━───── 1%``."""
    filled = int(pct / 100 * width)
    filled = max(0, min(filled, width))
    return "━" * filled + "─" * (width - filled) + f" {pct:.0f}%"


def _live_snapshot() -> tuple[dict | None, str]:
    """Full live usage snapshot (disk-cached) with its freshness source.

    source is "live" (fresh or recently-cached), "stale" (older than the cache
    window because a fetch failed), or "estimate" (no live value at all).

    The snapshot comes from Anthropic's usage endpoint. Since each `--print`
    is a fresh process, we cache it on disk and only re-fetch every
    LIVE_CACHE_TTL — otherwise every refresh hits the endpoint and gets
    rate-limited (HTTP 429).
    """
    fresh = load_live_snapshot(max_age_seconds=LIVE_CACHE_TTL)
    if fresh is not None:
        return fresh, "live"
    data = get_live_usage()
    if data and data.get("five_hour_pct") is not None:
        save_live_snapshot(data)
        return data, "live"
    stale = load_live_snapshot(max_age_seconds=LIVE_STALE_MAX)
    if stale is not None:
        return stale, "stale"
    return None, "estimate"


def current_usage(use_live: bool = True) -> tuple[float, str]:
    """Return (percent, source) for the 5-hour window (see :func:`_live_snapshot`)."""
    if use_live:
        snap, source = _live_snapshot()
        if snap is not None and snap.get("five_hour_pct") is not None:
            return min(snap["five_hour_pct"], 100), source
    return get_plan_usage(load_saved_plan() or DEFAULT_PLAN)["pct"], "estimate"


def current_usage_pct(use_live: bool = True) -> float:
    """Just the percentage (see :func:`current_usage`)."""
    return current_usage(use_live=use_live)[0]


def status_text() -> str:
    """Menu-bar text (no icon): bar + %, e.g. ``━━━━━━──── 69%``.

    A trailing marker distinguishes non-live values so a fallback can never be
    mistaken for real usage: ``·`` = last-known (stale), ``≈`` = local estimate.
    The native app supplies the Claude logo alongside this text.
    """
    try:
        pct, source = current_usage(use_live=True)
        marker = {"stale": " ·", "estimate": " ≈"}.get(source, "")
        return render_bar(pct) + marker
    except Exception:
        return "─" * BAR_WIDTH + " ?%"


def current_line() -> str:
    """Text with a ``⚡`` prefix, for text-only menu bars (the rumps app)."""
    return "⚡" + status_text()


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _reset_countdown(resets_at: str) -> str:
    """'1h 9m' until an ISO reset timestamp (UTC-aware), or '' if unparseable."""
    try:
        secs = int((_parse_iso(resets_at) - datetime.now(timezone.utc)).total_seconds())
    except (ValueError, TypeError, AttributeError):
        return ""
    if secs <= 0:
        return "now"
    hours, mins = secs // 3600, (secs % 3600) // 60
    return f"{hours}h {mins}m" if hours else f"{mins}m"


def _reset_absolute(resets_at: str) -> str:
    """Local wall-clock like 'Wed 11:00 PM', or '' if unparseable."""
    try:
        dt = _parse_iso(resets_at).astimezone()
    except (ValueError, TypeError, AttributeError):
        return ""
    hour = dt.strftime("%I").lstrip("0") or "12"  # %-I isn't portable
    return dt.strftime(f"%a {hour}:%M %p")


def menu_details() -> list[str]:
    """Lines for the dropdown: session countdown + per-limit / per-model breakdown."""
    snap, source = _live_snapshot()
    if not snap:
        return ["Live usage unavailable — run `claude` once"]

    lines: list[str] = []
    limits = snap.get("limits") or []

    def _pct(entry) -> int:
        return int(entry.get("percent") or 0)

    for entry in (e for e in limits if e.get("kind") == "session"):
        cd = _reset_countdown(entry.get("resets_at"))
        tail = f" · resets in {cd}" if cd else ""
        lines.append(f"Session · {_pct(entry)}% used{tail}")

    for entry in (e for e in limits if e.get("kind") == "weekly_all"):
        when = _reset_absolute(entry.get("resets_at"))
        tail = f" · resets {when}" if when else ""
        lines.append(f"All models · {_pct(entry)}% used{tail}")

    for entry in (e for e in limits if e.get("kind") == "weekly_scoped"):
        model = ((entry.get("scope") or {}).get("model") or {}).get("display_name") or "Model"
        when = _reset_absolute(entry.get("resets_at"))
        tail = f" · resets {when}" if when else ""
        lines.append(f"{model} · {_pct(entry)}% used{tail}")

    if not lines:  # snapshot predates the per-limit breakdown
        pct = snap.get("five_hour_pct")
        if pct is not None:
            cd = _reset_countdown(snap.get("five_hour_resets_at"))
            tail = f" · resets in {cd}" if cd else ""
            lines.append(f"Session · {int(pct)}% used{tail}")

    if source == "stale":
        lines.append("(last known — reconnecting)")
    return lines


def print_check() -> None:
    """Self-diagnostic: explain exactly what the menu bar is showing and why."""
    import time

    from claude_pulse.config import PULSE_CONFIG_FILE
    from claude_pulse.data.limits import get_usage_status

    pct, source = current_usage(use_live=True)
    print(f"Menu-bar text : {status_text()}")
    print(f"Value source  : {source}")

    status = get_usage_status()
    print(f"Live endpoint : {status['reason']} — {status['message']}")
    data = status.get("data") or {}
    if data.get("five_hour_pct") is not None:
        print(f"Live 5-hour   : {data['five_hour_pct']:.0f}%")

    snap = load_live_snapshot(max_age_seconds=LIVE_STALE_MAX)
    if snap is not None and PULSE_CONFIG_FILE.exists():
        try:
            cfg = json.loads(PULSE_CONFIG_FILE.read_text(encoding="utf-8"))
            age = int(time.time() - cfg.get("live_snapshot_at", 0))
            print(f"Cached value  : {int(snap.get('five_hour_pct', 0))}%  ({age}s old)")
        except (json.JSONDecodeError, OSError):
            pass
    else:
        print("Cached value  : none yet")

    print("Dropdown      :")
    for line in menu_details():
        print(f"  {line}")

    if source == "estimate":
        print("\nShowing the local ESTIMATE (over-counts). Live usage is "
              "unavailable — see the reason above.")
    elif source == "stale":
        print("\nShowing the last known real value; a fresh fetch failed "
              "(see the reason above).")


def _acp_path() -> str:
    """Best-effort path to the ``acp`` CLI for the 'Open dashboard' action."""
    return shutil.which("acp") or "acp"


def _launch_program_args() -> list[str]:
    """Command the LaunchAgent should run to start the menu-bar app."""
    acp_bar = shutil.which("acp-bar")
    if acp_bar:
        return [acp_bar]
    return [sys.executable, "-m", "claude_pulse.menubar"]


def _plist_contents() -> str:
    args = "".join(f"        <string>{a}</string>\n" for a in _launch_program_args())
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0">\n'
        "<dict>\n"
        "    <key>Label</key>\n"
        f"    <string>{LAUNCH_AGENT_LABEL}</string>\n"
        "    <key>ProgramArguments</key>\n"
        "    <array>\n"
        f"{args}"
        "    </array>\n"
        "    <key>RunAtLoad</key>\n"
        "    <true/>\n"
        "    <key>KeepAlive</key>\n"
        "    <true/>\n"
        "    <key>ProcessType</key>\n"
        "    <string>Interactive</string>\n"
        "    <key>LimitLoadToSessionType</key>\n"
        "    <string>Aqua</string>\n"
        "    <key>StandardOutPath</key>\n"
        "    <string>/tmp/acp-bar.out.log</string>\n"
        "    <key>StandardErrorPath</key>\n"
        "    <string>/tmp/acp-bar.err.log</string>\n"
        "</dict>\n"
        "</plist>\n"
    )


def _gui_domain() -> str:
    """The user's GUI (Aqua) launchd domain, e.g. 'gui/501'."""
    return f"gui/{os.getuid()}"


def install_launch_agent() -> None:
    LAUNCH_AGENT_PATH.parent.mkdir(parents=True, exist_ok=True)
    LAUNCH_AGENT_PATH.write_text(_plist_contents())

    domain = _gui_domain()
    label = f"{domain}/{LAUNCH_AGENT_LABEL}"
    # Bootstrap into the GUI session so the menu-bar item actually appears
    # (a plain `launchctl load` targets the caller's domain, which may not be
    # the Aqua session when run from SSH/a non-GUI shell).
    subprocess.run(["launchctl", "bootout", label], capture_output=True)
    r = subprocess.run(
        ["launchctl", "bootstrap", domain, str(LAUNCH_AGENT_PATH)],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        # Older macOS fallback.
        subprocess.run(["launchctl", "load", str(LAUNCH_AGENT_PATH)], check=False)
    subprocess.run(["launchctl", "kickstart", "-k", label], capture_output=True)

    print(f"Installed LaunchAgent at {LAUNCH_AGENT_PATH}")
    print("Claude Pulse menu bar is now running and will start on every login.")


def uninstall_launch_agent() -> None:
    label = f"{_gui_domain()}/{LAUNCH_AGENT_LABEL}"
    subprocess.run(["launchctl", "bootout", label], capture_output=True)
    if LAUNCH_AGENT_PATH.exists():
        subprocess.run(["launchctl", "unload", str(LAUNCH_AGENT_PATH)],
                       capture_output=True)
        LAUNCH_AGENT_PATH.unlink()
        print(f"Removed LaunchAgent at {LAUNCH_AGENT_PATH}")
    else:
        print("No LaunchAgent installed.")


def _build_app():
    import rumps

    class PulseBar(rumps.App):
        def __init__(self):
            self._plan = load_saved_plan() or DEFAULT_PLAN
            super().__init__("⚡ …", quit_button="Quit")

            self._plan_items = {}
            plan_menu = rumps.MenuItem("Plan")
            for key, info in PLAN_LIMITS.items():
                item = rumps.MenuItem(info["name"], callback=self._make_plan_cb(key))
                self._plan_items[key] = item
                plan_menu.add(item)

            self.menu = [
                plan_menu,
                rumps.MenuItem("Refresh now", callback=self._on_refresh),
                rumps.MenuItem("Open dashboard", callback=self._on_open_dashboard),
                None,  # separator (Quit is added automatically below it)
            ]
            self._sync_plan_checkmarks()
            self._refresh()

        def _make_plan_cb(self, plan_key):
            def _cb(_sender):
                self._plan = plan_key
                save_selected_plan(plan_key)
                self._sync_plan_checkmarks()
                self._refresh()
            return _cb

        def _sync_plan_checkmarks(self):
            for key, item in self._plan_items.items():
                item.state = 1 if key == self._plan else 0

        def _refresh(self):
            self.title = current_line()

        def _on_refresh(self, _sender):
            self._refresh()

        def _on_open_dashboard(self, _sender):
            script = f'tell application "Terminal" to do script "{_acp_path()}"'
            subprocess.run(["osascript", "-e", script], check=False)
            subprocess.run(["open", "-a", "Terminal"], check=False)

        @rumps.timer(REFRESH_SECONDS)
        def _tick(self, _sender):
            self._refresh()

    return PulseBar()


def main() -> None:
    args = sys.argv[1:]
    if "--check" in args:
        print_check()
        return
    if "--print" in args:
        # The menu-bar text only (the native app draws the Claude logo beside it).
        print(status_text())
        return
    if "--details" in args:
        # The dropdown breakdown, one line per menu item.
        for line in menu_details():
            print(line)
        return
    if "--menu" in args:
        # Everything the native app needs in one call: line 1 is the title
        # text, the rest are the dropdown items. One process → one endpoint hit.
        print(status_text())
        for line in menu_details():
            print(line)
        return
    if "--install" in args:
        install_launch_agent()
        return
    if "--uninstall" in args:
        uninstall_launch_agent()
        return

    if sys.platform != "darwin":
        sys.exit("acp-bar is only supported on macOS.")

    try:
        import rumps  # noqa: F401
    except ImportError:
        sys.exit(
            "The menu-bar app needs the 'menubar' extra. Install it with:\n"
            "  uv tool install 'claude-pulse[menubar]'\n"
            "  # or: pip install 'claude-pulse[menubar]'"
        )

    app = _build_app()

    # Run as a menu-bar-only accessory app — no Dock icon, no app switcher entry.
    try:
        import AppKit
        AppKit.NSApplication.sharedApplication().setActivationPolicy_(
            AppKit.NSApplicationActivationPolicyAccessory
        )
    except Exception:
        pass

    app.run()


if __name__ == "__main__":
    main()
