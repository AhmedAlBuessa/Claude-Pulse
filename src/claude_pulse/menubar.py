"""macOS menu-bar usage indicator for Claude Pulse.

Shows the current rolling-window usage as a block bar in the menu bar, e.g.
``░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ 1%``, refreshing on a timer. Requires the
``[menubar]`` extra (``rumps``) and only runs on macOS.

Usage::

    acp-bar                # run the menu-bar app
    acp-bar --install      # install a LaunchAgent so it starts on login
    acp-bar --uninstall    # remove the LaunchAgent
"""

import shutil
import subprocess
import sys
from pathlib import Path

from claude_pulse.config import (
    DEFAULT_PLAN,
    PLAN_LIMITS,
    load_saved_plan,
    save_selected_plan,
)
from claude_pulse.data.conversations import get_plan_usage
from claude_pulse.data.limits import get_live_usage

REFRESH_SECONDS = 60
BAR_WIDTH = 30  # matches the requested look; shrink (e.g. 10-15) if the menu bar truncates
LAUNCH_AGENT_LABEL = "com.claudepulse.menubar"
LAUNCH_AGENT_PATH = Path.home() / "Library" / "LaunchAgents" / f"{LAUNCH_AGENT_LABEL}.plist"


def render_bar(pct: float, width: int = BAR_WIDTH) -> str:
    """Render a plain-text usage bar, e.g. ``░░░… 1%``."""
    filled = int(pct / 100 * width)
    filled = max(0, min(filled, width))
    return "█" * filled + "░" * (width - filled) + f" {pct:.0f}%"


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
        "</dict>\n"
        "</plist>\n"
    )


def install_launch_agent() -> None:
    LAUNCH_AGENT_PATH.parent.mkdir(parents=True, exist_ok=True)
    LAUNCH_AGENT_PATH.write_text(_plist_contents())
    subprocess.run(["launchctl", "unload", str(LAUNCH_AGENT_PATH)],
                   capture_output=True)
    subprocess.run(["launchctl", "load", str(LAUNCH_AGENT_PATH)], check=False)
    print(f"Installed LaunchAgent at {LAUNCH_AGENT_PATH}")
    print("Claude Pulse menu bar will now start automatically on login.")


def uninstall_launch_agent() -> None:
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
            try:
                # Prefer Anthropic's real 5-hour utilization (matches `claude`
                # and claude.ai/usage); fall back to the local plan estimate.
                live = get_live_usage()
                if live and live.get("five_hour_pct") is not None:
                    pct = min(live["five_hour_pct"], 100)
                else:
                    pct = get_plan_usage(self._plan)["pct"]
                self.title = render_bar(pct)
            except Exception:
                self.title = "░" * BAR_WIDTH + " ?%"

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

    _build_app().run()


if __name__ == "__main__":
    main()
