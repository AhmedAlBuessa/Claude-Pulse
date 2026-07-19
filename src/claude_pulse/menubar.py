"""macOS menu-bar usage indicator for Claude Pulse.

Shows the current rolling-window usage as a block bar in the menu bar, e.g.
``░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ 1%``, refreshing on a timer. Requires the
``[menubar]`` extra (``rumps``) and only runs on macOS.

Usage::

    acp-bar                # run the menu-bar app
    acp-bar --install      # install a LaunchAgent so it starts on login
    acp-bar --uninstall    # remove the LaunchAgent
"""

import os
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
BAR_WIDTH = 10  # keep short — a wide title gets hidden/truncated in the menu bar
LAUNCH_AGENT_LABEL = "com.claudepulse.menubar"
LAUNCH_AGENT_PATH = Path.home() / "Library" / "LaunchAgents" / f"{LAUNCH_AGENT_LABEL}.plist"


def render_bar(pct: float, width: int = BAR_WIDTH) -> str:
    """Render a plain-text usage bar, e.g. ``░░░… 1%``."""
    filled = int(pct / 100 * width)
    filled = max(0, min(filled, width))
    return "█" * filled + "░" * (width - filled) + f" {pct:.0f}%"


def current_usage_pct(use_live: bool = False) -> float:
    """Current usage percent.

    Defaults to the fast local plan estimate (reads log files only). Live
    utilization is opt-in because reading Anthropic's credential from the
    keychain triggers a permission prompt from any binary that isn't Claude
    Code itself — undesirable for an always-running menu-bar tool.
    """
    if use_live:
        live = get_live_usage()
        if live and live.get("five_hour_pct") is not None:
            return min(live["five_hour_pct"], 100)
    return get_plan_usage(load_saved_plan() or DEFAULT_PLAN)["pct"]


def current_line() -> str:
    """One-line menu-bar string, e.g. ``⚡██████░░░░ 69%``."""
    try:
        return "⚡" + render_bar(current_usage_pct())
    except Exception:
        return "⚡" + "░" * BAR_WIDTH + " ?%"


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
            try:
                # Prefer Anthropic's real 5-hour utilization (matches `claude`
                # and claude.ai/usage); fall back to the local plan estimate.
                live = get_live_usage()
                if live and live.get("five_hour_pct") is not None:
                    pct = min(live["five_hour_pct"], 100)
                else:
                    pct = get_plan_usage(self._plan)["pct"]
                self.title = "⚡" + render_bar(pct)
            except Exception:
                self.title = "⚡" + "░" * BAR_WIDTH + " ?%"

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
    if "--print" in args:
        # Emit a single menu-bar line and exit. Used by the native Swift
        # menu-bar host (macOS renders status items reliably only from a
        # proper app bundle; a bare Python process does not on macOS 26+).
        print(current_line())
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
