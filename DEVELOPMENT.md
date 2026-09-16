# Development

## Prerequisites

- Python 3.12 (managed by `uv`)
- [uv](https://docs.astral.sh/uv/) for Python tooling
- [Rust](https://rustup.rs/) (for Tauri desktop builds)

## Quick start

```bash
# Install dependencies and run the dev server
uv sync
uv run diffr
```

This starts the FastAPI server on http://127.0.0.1:8787 and opens your browser.

## CLI

```bash
# Run from a git repo (auto-scopes to that repo)
cd ~/my-project
diffr

# Run from anywhere (shows repo picker)
diffr

# Reset all settings and data
diffr reset
```

Install globally so `diffr` is on your PATH:

```bash
uv tool install --editable /path/to/diffr
```

## Linting

```bash
bin/lint          # check
bin/lint --fix    # auto-fix
```

Runs ruff (lint + format) and mypy.

## Desktop App (Tauri)

The desktop app wraps the web UI in a native window using Tauri. The Python
server runs as a bundled sidecar binary.

### Setup

```bash
# Install Tauri CLI
cargo install tauri-cli

# Install PyInstaller (needed to bundle the Python sidecar)
uv add --dev pyinstaller
```

### Development

```bash
cd desktop
cargo tauri dev
```

This starts the Python server automatically and opens the native window. Changes
to Python code require restarting (`Ctrl+C` and re-run). Changes to
templates/CSS/JS are picked up on refresh.

### Building A Release

```bash
# 1. Bundle the Python app into a single binary
cd desktop
./build-sidecar

# 2. Build the Tauri app (.dmg on macOS, .msi on Windows, .AppImage on Linux)
cargo tauri build
```

The output goes to `desktop/src-tauri/target/release/bundle/`.

## Project Layout

```
diffr/
├── app/              # FastAPI routes, templates, static assets
│   ├── routes/       # API + page endpoints
│   ├── templates/    # Jinja2 templates (HTMX)
│   └── static/       # CSS, JS, favicon
├── core/             # Pure domain models, no external dependencies
├── ports/            # Abstract interfaces (ABCs)
├── adapters/         # Implementations (SQLite, git, Claude, SSE)
├── cli.py            # CLI entry point
├── main.py           # FastAPI app factory
├── config.py         # Config load/save (~/.local/share/diffr/)
├── desktop/          # Tauri desktop wrapper
│   ├── src-tauri/    # Rust source + config
│   └── build-sidecar # PyInstaller bundling script
└── bin/
    └── lint          # Lint runner
```

## Architecture

Hexagonal (ports and adapters). `core/` contains only domain models with zero
imports from the rest of the project. `ports/` defines abstract interfaces.
`adapters/` implements them. `app/` wires everything together.

The AI adapter is pluggable via `config.json` (`ai_provider` key). Current
adapters: `claude` (Claude Code CLI), `noop` (no AI).

## Data

All persistent data lives in `~/.local/share/diffr/`:

- `config.json` for settings (scan paths, AI provider)
- `diffr.db` SQLite database (reviews, comments, reactions)
- `reviews/<id>/context.md` per-review context files for AI
