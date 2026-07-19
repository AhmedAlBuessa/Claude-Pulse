<div align="center">

# ⚡ Claude Pulse

### _Beautiful terminal dashboards for monitoring your Claude Code usage_

[![PyPI version](https://img.shields.io/pypi/v/claude-pulse?color=blueviolet&style=for-the-badge&logo=pypi&logoColor=white)](https://pypi.org/project/claude-pulse/)
[![Python](https://img.shields.io/badge/python-3.9+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-22c55e?style=for-the-badge)](LICENSE)
[![Built with Rich](https://img.shields.io/badge/built%20with-Rich-ff69b4?style=for-the-badge)](https://github.com/Textualize/rich)

[![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Linux%20%7C%20Windows-0ea5e9?style=flat-square)](#)
[![Status](https://img.shields.io/badge/status-beta-f59e0b?style=flat-square)](#)
[![Made for Claude Code](https://img.shields.io/badge/made%20for-Claude%20Code-D97757?style=flat-square)](https://claude.com/claude-code)

**Real-time insights · Daily & monthly breakdowns · Cost tracking · Plan limits · macOS menu bar**

[Installation](#-installation) · [Usage](#-usage) · [Menu Bar](#-macos-menu-bar) · [Features](#-features) · [Options](#%EF%B8%8F-options) · [License](#-license)

</div>

---

## ✨ Features

| | |
|---|---|
| 🔴 **Real-time Dashboard** | Watch your sessions live as they happen |
| 📅 **Daily Breakdown** | Per-day usage tables with customizable windows |
| 📆 **Monthly Summary** | At-a-glance totals across each month |
| 💰 **Cost Tracking** | Estimated spend by model, in real dollars |
| 🎯 **Live Plan Limits** | Real 5-hour & weekly usage, same numbers as `claude` and claude.ai/usage |
| 🍎 **macOS Menu Bar** | Live usage bar in the menu bar — `░░░…░ 1%` — with auto-start on login |
| 🎨 **Themes** | Light, dark, or auto — matches your terminal |
| 📁 **Project Filters** | Slice usage by working directory |
| 🕘 **Session Resume** | Browse past sessions and jump back into one |
| 🧩 **JSON Export** | Pipe structured data into your own tools |

---

## 📦 Installation

> **Beta:** the first PyPI release is on its way. Until then, install straight from GitHub — the commands below work today.

Install with [`uv`](https://github.com/astral-sh/uv) (recommended):

```bash
uv tool install git+https://github.com/AhmedAlBuessa/Claude-Pulse
```

> 🪟 **Don't have `uv` yet?** Install it first (Windows / PowerShell), then re-open your terminal:
>
> ```powershell
> powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
> ```
>
> On macOS / Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`

…or with `pip`:

```bash
pip install git+https://github.com/AhmedAlBuessa/Claude-Pulse
```

<details>
<summary>📦 Once it's on PyPI (coming soon)</summary>

```bash
uv tool install claude-pulse
# or
pip install claude-pulse
```

</details>

> 💡 Two CLI aliases are installed: **`acp`** (recommended) and **`claude-pulse`**.
>
> 🪟 **Windows:** if `pip` isn't recognized, your Python `Scripts` folder isn't on `PATH`. Use `py -m pip install …` instead, or add `…\PythonXXX\Scripts` to `PATH`.

For the macOS menu-bar app, install with the optional **`menubar`** extra:

```bash
uv tool install "claude-pulse[menubar] @ git+https://github.com/AhmedAlBuessa/Claude-Pulse"
# …or: pip install "claude-pulse[menubar] @ git+https://github.com/AhmedAlBuessa/Claude-Pulse"
```

> 💡 This adds a third command, **`acp-bar`** (macOS only). Once on PyPI: `uv tool install 'claude-pulse[menubar]'`.

---

## 🚀 Usage

### Real-time dashboard _(default)_

```bash
acp
```

### Daily usage table

```bash
acp -v daily -d 14
```

### Monthly summary

```bash
acp -v monthly
```

### Browse & resume past sessions

List the sessions you worked on (last 30 days by default), pick one by number, and Claude Pulse re-opens it with `claude --resume` in its original folder:

```bash
acp -v sessions            # last 30 days
acp -v sessions -d 60      # widen the window to 60 days
acp -v sessions -p api     # only sessions in projects matching "api"
acp -v sessions --list-only  # just print the list, don't prompt
```

Each row shows when you were last active, the project, message count, model, and the first thing you asked — so you can recognize the conversation at a glance. Type the `#` and you're back in it.

### JSON export

```bash
acp --json-output > usage.json
```

### Live plan-usage

The session bar shows your **real** 5-hour and weekly usage — the same numbers as `claude` and claude.ai/usage — pulled automatically from your existing Claude login. No setup.

```bash
acp                       # live bar appears automatically when you're logged in
acp --check-usage         # diagnose if the live bar isn't showing
acp --plan max20          # set your plan (used only for the fallback estimate)
acp --calibrate 9         # offline fallback: pin the baseline to the % on claude.ai/usage
```

> Live usage needs a Claude **subscription** login (Pro/Max). API-key users and offline runs fall back to a local token estimate.

---

## 🍎 macOS Menu Bar

Keep a live usage bar in your menu bar — the Claude mark next to a compact bar:

```text
✳ ■■■■■■□□□□ 69%
```

Click it for the full breakdown, mirroring claude.ai/usage:

```text
Session · 48% used · resets in 59m
All models · 40% used · resets Wed 10:59 PM
Fable · 10% used · resets Wed 10:59 PM
─────────────
Refresh now
Open dashboard
Quit
```

It refreshes every 60 seconds.

### Recommended: the native menu-bar app (macOS 13+, incl. Tahoe)

Modern macOS (26 / Tahoe) will not render a menu-bar item created by a bare Python process, so Claude Pulse ships a tiny **native Swift menu-bar app** that renders reliably and calls the tool for the number. Build and install it (requires Xcode command-line tools for `swiftc`):

```bash
# from a clone of this repo
bash packaging/ClaudePulseBar/build.sh          # builds ~/Applications/ClaudePulseBar.app
open ~/Applications/ClaudePulseBar.app          # launch it now
```

To start it automatically on login, add it in **System Settings → General → Login Items**, or run:

```bash
osascript -e 'tell application "System Events" to make login item at end with properties {path:(POSIX path of (path to home folder)) & "Applications/ClaudePulseBar.app"}'
```

The app displays the output of `acp-bar --print`, which shows your **real** 5-hour utilization from Anthropic's usage endpoint (the same number as `claude` and claude.ai/usage). If a fetch fails transiently (after sleep, offline, or an expired token), it shows your last known real value rather than jumping to a misleading estimate. The first read may prompt once for keychain access — click **Always Allow**.

### Python menu-bar app (older macOS)

On macOS versions that still render status items from Python, you can run the built-in app directly (requires the [`menubar` extra](#-installation)):

```bash
acp-bar               # run it
acp-bar --install     # install a LaunchAgent so it starts on login
acp-bar --uninstall   # remove it
```

### Troubleshooting the number

The bar shows your **real** 5-hour usage. To keep well under the usage endpoint's
rate limit, it caches the value on disk (~150s) and only re-fetches occasionally.
If a fetch fails (offline, expired token, or HTTP 429 rate-limiting) it shows your
last known real value — **never** a made-up number — with a trailing marker:

| Display | Meaning |
|---|---|
| `⚡███░░░░░░░ 32%` | live / recently-cached real value |
| `⚡███░░░░░░░ 32% ·` | last known real value (a fresh fetch failed) |
| `⚡██████████ 100% ≈` | local estimate (no live value available — e.g. not logged in) |

Run the built-in diagnostic to see exactly what's happening:

```bash
acp-bar --check
```

```text
Menu-bar line : ⚡███░░░░░░░ 32%
Value source  : live
Live endpoint : ok — Live usage is working.
Live 5-hour   : 32%
Cached value  : 32%  (67s old)
```

The `≈` estimate only appears when live usage can't be read at all — usually because
you're not logged in. Run `claude` once to refresh your login, then `acp-bar --check`.

---

## ⚙️ Options

| Flag | Description | Default |
|------|-------------|:-------:|
| `-v`, `--view` | Display mode — `realtime` · `daily` · `monthly` · `sessions` | `realtime` |
| `-d`, `--days` | Days to show in daily view (window for `sessions`, default 30) | `7` |
| `--list-only` | `sessions` view: list without prompting to resume | — |
| `-r`, `--refresh` | Refresh interval in seconds | `2` |
| `-t`, `--theme` | Color theme — `light` · `dark` · `auto` | `auto` |
| `-p`, `--project` | Filter by project path | _all_ |
| `--plan` | Subscription plan — `pro` · `max5` · `max20` (fallback when live usage is unavailable) | `pro` |
| `--calibrate` | Set a manual session baseline from the `%` on claude.ai/usage (offline fallback) | — |
| `--check-usage` | Diagnose whether live session-usage is working, and exit | — |
| `--json-output` | Emit structured JSON to stdout | — |
| `--version` | Show version and exit | — |

---

## 🖼️ Screens at a glance

<div align="center">

| 🔴 Real-time | 📅 Daily | 📆 Monthly |
|:---:|:---:|:---:|
| Live sessions, tokens, and spend | Per-day history with model breakdown | Rolled-up monthly totals |

</div>

---

## 🧠 How it works

Claude Pulse reads your local Claude Code conversation logs, aggregates tokens and tool calls, and renders them with [Rich](https://github.com/Textualize/rich). No telemetry — nothing about you is ever sent to us. 🔒

For the **live plan-usage** bar it makes one request to Anthropic's own usage endpoint (`api.anthropic.com/api/oauth/usage`), authenticated with the OAuth token Claude Code already stored on your machine (the macOS Keychain, or `~/.claude/.credentials.json` elsewhere) — the same call `claude` itself makes. That's the only network call, it goes only to Anthropic, and if it's unavailable (API-key login, expired token, or offline) the dashboard falls back to a local estimate. Run `acp --check-usage` to see exactly what's happening.

---

## 🛠️ Development

```bash
git clone https://github.com/AhmedAlBuessa/Claude-Pulse
cd Claude-Pulse
uv sync --extra dev --extra menubar   # drop --extra menubar if not on macOS
uv run pytest
```

---

## 🤝 Contributing

Contributions, bug reports, and feature ideas are all welcome! Open an [issue](https://github.com/AhmedAlBuessa/Claude-Pulse/issues) or send a PR.

---

## 📄 License

Released under the [MIT License](LICENSE) — free to use, modify, and share.

<div align="center">

Made with ❤️ for the Claude Code community.

<sub>If Claude Pulse helps you time, consider giving the repo a ⭐</sub>

</div>
