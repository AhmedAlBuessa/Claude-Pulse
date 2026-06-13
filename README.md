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

**Real-time insights · Daily & monthly breakdowns · Cost tracking · Plan limits**

[Installation](#-installation) · [Usage](#-usage) · [Features](#-features) · [Options](#%EF%B8%8F-options) · [License](#-license)

</div>

---

## ✨ Features

| | |
|---|---|
| 🔴 **Real-time Dashboard** | Watch your sessions live as they happen |
| 📅 **Daily Breakdown** | Per-day usage tables with customizable windows |
| 📆 **Monthly Summary** | At-a-glance totals across each month |
| 💰 **Cost Tracking** | Estimated spend by model, in real dollars |
| 🎯 **Plan Limits** | Pro, Max 5, and Max 20 subscription calibration |
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

### Plan-aware tracking

```bash
acp --plan max20
```

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
| `--plan` | Subscription plan — `pro` · `max5` · `max20` | `pro` |
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

Claude Pulse reads your local Claude Code conversation logs, aggregates tokens and tool calls, and renders them with [Rich](https://github.com/Textualize/rich) — no network calls, no telemetry, everything stays on your machine. 🔒

---

## 🛠️ Development

```bash
git clone https://github.com/AhmedAlBuessa/Claude-Pulse
cd Claude-Pulse
uv sync --extra dev
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

<sub>If Claude Pulse saves you time, consider giving the repo a ⭐</sub>

</div>
