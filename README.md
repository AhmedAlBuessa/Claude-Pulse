# claude-pulse

Monitor your Claude Code usage with clean terminal dashboards.

## Installation

```bash
uv tool install claude-pulse
```

Or with pip:

```bash
pip install claude-pulse
```

## Usage

```bash
# Real-time dashboard (default)
claude-pulse

# Daily usage table
claude-pulse -v daily

# Monthly summary
claude-pulse -v monthly

# JSON output
claude-pulse --json-output

# Custom refresh rate and days
claude-pulse -r 3 -d 14
```

## Aliases

Both `claude-pulse` and `cpulse` are available after installation.

## License

MIT
