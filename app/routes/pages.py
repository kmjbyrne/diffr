import os
import shlex
import subprocess
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from adapters.claude_sessions import get_active_workers, get_jobs, get_recent_sessions
from adapters.git import (
    DiscoveredRepo,
    discover_repos,
    discover_repos_stale,
    discover_worktrees,
    get_branches,
    get_commits,
    get_default_branch,
    get_diff_files,
    get_diffstat,
    get_main_repo_root,
    get_repo_info,
    get_repo_root,
    is_branch_up_to_date,
    rebase_worktree,
)
from app import deps
from config import load_config, save_config


def _inject_cli_repo(repos: list[DiscoveredRepo]) -> list[DiscoveredRepo]:
    """Prepend the CLI-provided repo if it isn't already in the list."""
    cli_path = os.environ.get("DIFFR_REPO_PATH")
    if not cli_path:
        return repos
    root = get_repo_root(cli_path)
    if not root:
        return repos
    if any(r.path == root for r in repos):
        return repos
    cli_repo = DiscoveredRepo(
        path=root,
        name=Path(root).name,
        default_branch=get_default_branch(root),
        worktree_count=len(discover_worktrees(root)),
    )
    return [cli_repo] + repos

router = APIRouter()


@router.get("/")
async def index(request: Request):
    templates = request.app.state.templates
    config = load_config()

    cli_repo_path = os.environ.get("DIFFR_REPO_PATH")

    if not config.get("scan_paths") and not cli_repo_path:
        return templates.TemplateResponse(request, "setup.html")

    repo_path = cli_repo_path or config.get("last_repo") or "."
    branch = os.environ.get("DIFFR_BRANCH") or config.get("last_branch") or ""
    base = os.environ.get("DIFFR_BASE") or config.get("last_base") or "main"

    repos, needs_refresh = discover_repos_stale(
        config["scan_paths"], config.get("max_depth", 2)
    )
    repos = _inject_cli_repo(repos)
    needs_refresh = needs_refresh or not repos

    root = get_repo_root(repo_path)
    worktrees = discover_worktrees(repo_path) if root else []
    default = get_default_branch(root) if root else "main"
    wt_up_to_date = {
        wt.path for wt in worktrees
        if is_branch_up_to_date(wt.path, default)
    }
    stack_positions = _stack_positions(root) if root else {}
    if root and stack_positions:
        _fix_stack_diffstats(root, worktrees, _stack_bases(root))
    worktrees = _sort_worktrees_by_stack(worktrees, stack_positions)

    recent_reviews = deps.reviews.search(repo_path=repo_path, limit=20) if repo_path else deps.reviews.recent()

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "repo_path": repo_path,
            "branch": branch,
            "base": base,
            "worktrees": worktrees,
            "wt_up_to_date": wt_up_to_date,
            "stack_positions": stack_positions,
            "recent_reviews": [asdict(r) for r in recent_reviews],
            "repos": repos,
            "scan_paths": config["scan_paths"],
            "needs_refresh": needs_refresh,
        },
    )


@router.post("/api/remember-selection")
async def remember_selection(request: Request):
    data = await request.json()
    config = load_config()
    if data.get("repo_path"):
        config["last_repo"] = data["repo_path"]
    if data.get("branch"):
        config["last_branch"] = data["branch"]
    if data.get("base"):
        config["last_base"] = data["base"]
    save_config(config)
    return {"ok": True}


@router.post("/api/scan-paths")
async def add_scan_path(request: Request):
    data = await request.json()
    path = data.get("path", "").strip()
    if not path:
        return {"error": "path is required"}
    config = load_config()
    if path not in config["scan_paths"]:
        config["scan_paths"].append(path)
        save_config(config)
    return {"ok": True, "scan_paths": config["scan_paths"]}


@router.delete("/api/scan-paths")
async def remove_scan_path(request: Request):
    data = await request.json()
    path = data.get("path", "").strip()
    config = load_config()
    config["scan_paths"] = [p for p in config["scan_paths"] if p != path]
    save_config(config)
    return {"ok": True, "scan_paths": config["scan_paths"]}


@router.post("/api/open-terminal")
async def open_terminal(request: Request):
    data = await request.json()
    path = data.get("path", "").strip()
    if not path or not os.path.isdir(path):
        return {"error": "Invalid path"}
    script = (
        'tell application "iTerm"\n'
        "  create window with default profile\n"
        '  tell current session of current window\n'
        f'    write text "cd {shlex.quote(path)}"\n'
        "  end tell\n"
        "end tell"
    )
    subprocess.Popen(["osascript", "-e", script])
    return {"ok": True}


@router.get("/api/repos", response_class=HTMLResponse)
async def list_repos(request: Request):
    templates = request.app.state.templates
    config = load_config()
    repos = discover_repos(config["scan_paths"], config.get("max_depth", 2))
    repos = _inject_cli_repo(repos)
    return templates.TemplateResponse(
        request,
        "partials/repo_options.html",
        {
            "repos": repos,
        },
    )


@router.get("/api/worktrees", response_class=HTMLResponse)
async def list_worktrees(request: Request, repo_path: str):
    templates = request.app.state.templates
    root = get_repo_root(repo_path)
    worktrees = discover_worktrees(repo_path) if root else []
    default = get_default_branch(root) if root else "main"
    wt_up_to_date = {
        wt.path for wt in worktrees
        if is_branch_up_to_date(wt.path, default)
    }
    stack_positions = _stack_positions(root) if root else {}
    if root and stack_positions:
        _fix_stack_diffstats(root, worktrees, _stack_bases(root))
    worktrees = _sort_worktrees_by_stack(worktrees, stack_positions)
    return templates.TemplateResponse(
        request,
        "partials/worktree_list.html",
        {
            "worktrees": worktrees,
            "wt_up_to_date": wt_up_to_date,
            "repo_path": repo_path,
            "stack_positions": stack_positions,
        },
    )


@router.post("/api/worktrees/rebase")
async def rebase_worktree_endpoint(request: Request):
    data = await request.json()
    wt_path = data.get("worktree_path", "").strip()
    if not wt_path:
        return {"ok": False, "message": "worktree_path is required"}
    root = get_repo_root(wt_path)
    if not root:
        return {"ok": False, "message": "Not a git repository"}
    onto = data.get("onto") or get_default_branch(root)
    result = rebase_worktree(wt_path, onto)
    return {"ok": result.ok, "message": result.message}


def _stacked_branches(repo_path: str) -> set[str]:
    roots, _ = get_branch_graph_cached(repo_path)
    result: set[str] = set()
    def collect(nodes):
        for node in nodes:
            if node.children:
                result.add(node.name)
                for child in node.children:
                    result.add(child.name)
                collect(node.children)
    collect(roots)
    return result


def _stack_positions(repo_path: str) -> dict[str, tuple[str, int, int]]:
    registered = deps.stacks.for_repo(repo_path)
    positions: dict[str, tuple[str, int, int]] = {}
    for s in registered:
        for i, branch in enumerate(s.branches):
            positions[branch] = (s.name, i + 1, len(s.branches))
    return positions


def _stack_bases(repo_path: str) -> dict[str, str]:
    """Map each stacked branch to its parent branch in the stack."""
    from adapters.git import get_default_branch
    registered = deps.stacks.for_repo(repo_path)
    default = get_default_branch(repo_path)
    bases: dict[str, str] = {}
    for s in registered:
        for i, branch in enumerate(s.branches):
            bases[branch] = s.branches[i - 1] if i > 0 else default
    return bases


def _sort_worktrees_by_stack(worktrees, stack_positions):
    """Sort worktrees so stacked branches appear consecutively in stack order."""
    if not stack_positions:
        return worktrees

    stacked = []
    unstacked = []
    for wt in worktrees:
        if wt.branch in stack_positions:
            stacked.append(wt)
        else:
            unstacked.append(wt)

    stacked.sort(key=lambda wt: (stack_positions[wt.branch][0], stack_positions[wt.branch][1]))
    return stacked + unstacked


def _fix_stack_diffstats(repo_path: str, worktrees, stack_bases: dict[str, str]):
    """Recalculate diffstat for stacked branches using their stack parent."""
    for wt in worktrees:
        parent = stack_bases.get(wt.branch)
        if not parent:
            continue
        try:
            files, ins, dels = get_diffstat(wt.path, parent, "HEAD")
            wt.files_changed = files
            wt.insertions = ins
            wt.deletions = dels
        except Exception:
            pass


@router.get("/api/branches", response_class=HTMLResponse)
async def list_branches(request: Request, repo_path: str):
    templates = request.app.state.templates
    root = get_repo_root(repo_path)
    if not root:
        return HTMLResponse('<option value="">No branches found</option>')
    info = get_repo_info(root)
    branches = get_branches(root)
    worktrees = discover_worktrees(root)
    wt_branches = {wt.branch for wt in worktrees}
    return templates.TemplateResponse(
        request,
        "partials/branch_options.html",
        {
            "branches": branches,
            "worktree_branches": wt_branches,
            "current_branch": info.current_branch,
            "default_branch": info.default_branch,
        },
    )


@router.get("/review/{review_id}")
async def review_page(request: Request, review_id: str):
    templates = request.app.state.templates
    review = deps.reviews.get(review_id)

    if not review:
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "error": "Review not found",
                "repo_path": "",
                "branch": "",
                "base": "",
                "worktrees": [],
                "recent_reviews": [],
                "repos": [],
                "scan_paths": [],
            },
        )

    files = get_diff_files(review.repo_path, review.base_branch, review.branch)
    commits = get_commits(review.repo_path, review.base_branch, review.branch)
    comment_counts = deps.comments.comment_counts_by_file(review_id)
    up_to_date = is_branch_up_to_date(
        review.repo_path, review.base_branch, review.branch
    )

    prior_reviews = deps.reviews.search(review.repo_path, review.branch, limit=5)
    previous_review = next(
        (r for r in prior_reviews if r.id != review.id), None
    )

    stack_ctx = None
    root = get_main_repo_root(review.repo_path) or get_repo_root(review.repo_path)
    if root:
        for s in deps.stacks.for_repo(root):
            if review.branch in s.branches:
                idx = s.branches.index(review.branch)
                stack_ctx = {
                    "id": s.id,
                    "name": s.name,
                    "branches": s.branches,
                    "current": review.branch,
                    "position": idx + 1,
                    "total": len(s.branches),
                }
                break

    main_root = root or review.repo_path
    repo_name = os.path.basename(main_root)

    return templates.TemplateResponse(
        request,
        "review.html",
        {
            "review": asdict(review),
            "files": files,
            "commits": commits,
            "comment_counts": comment_counts,
            "previous_review": asdict(previous_review) if previous_review else None,
            "branch_up_to_date": up_to_date,
            "stack": stack_ctx,
            "repo_name": repo_name,
        },
    )


@router.get("/settings")
async def settings_page(request: Request):
    templates = request.app.state.templates
    config = load_config()
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "scan_paths": config.get("scan_paths", []),
            "max_depth": config.get("max_depth", 2),
            "claude_enabled": config.get("claude_integration", False),
            "ai_provider": config.get("ai_provider", "noop"),
        },
    )


@router.get("/sessions")
async def sessions_page(request: Request):
    templates = request.app.state.templates
    config = load_config()

    if not config.get("claude_integration"):
        return templates.TemplateResponse(
            request,
            "sessions.html",
            {
                "active_workers": {},
                "active_count": 0,
                "jobs": [],
                "recent": [],
                "sessions": [],
                "enabled": False,
            },
        )

    active_workers = get_active_workers()
    jobs = get_jobs(30)
    recent = get_recent_sessions(30)

    return templates.TemplateResponse(
        request,
        "sessions.html",
        {
            "active_workers": active_workers,
            "active_count": len(active_workers),
            "jobs": jobs,
            "recent": recent,
            "sessions": jobs + recent,
            "enabled": True,
        },
    )


@router.patch("/api/settings")
async def update_settings(request: Request):
    data = await request.json()
    config = load_config()
    for key in ("claude_integration", "ai_provider", "max_depth"):
        if key in data:
            config[key] = data[key]
    save_config(config)
    return {"ok": True}


@router.post("/api/reset")
async def reset_all():
    import shutil

    from config import CONFIG_PATH

    data_dir = CONFIG_PATH.parent
    if data_dir.exists():
        shutil.rmtree(data_dir)
    return {"ok": True}
