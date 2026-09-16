# diffr

Local code review interface for Git branches and worktrees. Review your changes,
comment inline, discuss with an AI model, fix, and iterate, all _before_ pushing
to a remote.

## Motivations

I couldn't find a tool that lets you review local worktree changes the way
GitHub lets you review a pull request (confession: didn't look very hard
though). VSCode shows worktree diffs, but there's no commenting, threading or
conversation.

The alternative is pushing to a remote and opening a PR. But that triggers CI,
burns compute (not good for mother earth 🌍), and puts half-finished work in
front of reviewers. Pre-reviewing locally before pushing means the PR you
eventually open is already iterated on. Less noise, less wasted CI, fewer rounds
of review.

This matters more now that AI writes a lot of code. Reviewing model-generated
changes before they leave your machine is just good practice. **diffr** gives
you a place to do that: read the diff, leave comments, talk to yourself, let the
model respond, fix what needs fixing, _then_ push a better draft.

## How It Works

Start `diffr` (in repo or in any workspace/directory), pick a repo and branch,
and you get a side-by-side diff view with inline commenting.

Post a comment with `@claude` and the configured AI model reads the code context
and replies. You can discuss, ask for fixes, or tell it to commit a change. When
you're satisfied, push to your remote.

You review the model's work, or the model reviews your work. Either way is good
if it means less naughty code released into the wild.

My workflow:

1. Work on a worktree or branch
2. Open `diffr`, review your changes
3. Comment on lines, discuss with the AI
4. Fix issues, repeat
5. Push to origin when it's ready

Worktrees are a natural fit here. You can have several features in progress,
each in its own worktree, and review them independently without stashing or
branch-switching.

You can run `diffr` in a repo (targeted session) or as an active session for all
configured repos.

## Setup

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```
cd diffr
uv sync
uv run diffr
```

On first run, `diffr` asks for a directory to scan for git repositories. You can
add or remove scan paths from the UI later.

To review a specific repo directly:

```shell
uv run diffr ~/projects/my-repo feature-branch --base main
```

## Architecture

Hexagonal structure. The domain is isolated from infrastructure.

```
diffr/
  core/       Pure domain models and business rules
  ports/      Abstract interfaces (AI, repositories, events)
  adapters/   Implementations (SQLite, Claude, SSE, git)
  app/        FastAPI routes, templates, static assets
  mcp/        MCP server for tool integration
```

`core/` has no imports from the rest of the project. `ports/` defines what the
domain needs. `adapters/` provides it. `app/` wires them together.

## AI Integration

The tool ships with a Claude adapter (currently) and a no-op adapter. The active
provider is set in `~/.local/share/diffr/config.json`:

```json
{
  "ai_provider": "claude"
}
```

NOTE: I am currently working on an OpenCode integration for local LLMs and
building out the "bring your own model" approach.

Set `ai_provider` to `"none"` to disable AI replies. To add a new provider,
implement `AIPort` from `diffr/ports/ai.py` and register it in
`diffr/app/deps.py`.

The AI model receives the review context (file list, previous discussion) and
the code around the commented line. It replies through the same comment API, so
replies appear inline next to your comments.

## MCP Server (Scrappy, Work In Progress)

The tool includes an MCP server so Claude (or any MCP-compatible tool) can
interact with reviews natively:

```
uv run diffr-mcp
```

Tools: `list_reviews`, `get_review_comments`, `get_unprocessed_comments`,
`reply_to_comment`, `mark_comments_processed`, `set_review_status`.

The issue I have here is that Claude doesn't have an event driven flow that
works but in theory, bypass Claude Code and using API directly would work here.

## Stack

Python 3.12, FastAPI, HTMX, SQLite, Server-Sent Events. No JavaScript framework.
No build step.
