import os
from dataclasses import asdict

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from adapters.git import (
    discover_repos,
    discover_worktrees,
    get_branches,
    get_commits,
    get_diff_files,
    get_repo_info,
    get_repo_root,
)
from app import deps
from config import load_config, save_config

router = APIRouter()


@router.get("/")
async def index(request: Request):
    templates = request.app.state.templates
    config = load_config()

    if not config.get("scan_paths"):
        return templates.TemplateResponse(request, "setup.html")

    repo_path = os.environ.get("DIFFR_REPO_PATH") or config.get("last_repo") or "."
    branch = os.environ.get("DIFFR_BRANCH") or config.get("last_branch") or ""
    base = os.environ.get("DIFFR_BASE") or config.get("last_base") or "main"

    repos = discover_repos(config["scan_paths"], config.get("max_depth", 2))

    root = get_repo_root(repo_path)
    worktrees = discover_worktrees(repo_path) if root else []

    recent_reviews = deps.reviews.recent()

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "repo_path": repo_path,
            "branch": branch,
            "base": base,
            "worktrees": worktrees,
            "recent_reviews": [asdict(r) for r in recent_reviews],
            "repos": repos,
            "scan_paths": config["scan_paths"],
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


@router.get("/api/repos", response_class=HTMLResponse)
async def list_repos(request: Request):
    templates = request.app.state.templates
    config = load_config()
    repos = discover_repos(config["scan_paths"], config.get("max_depth", 2))
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
    return templates.TemplateResponse(
        request,
        "partials/worktree_list.html",
        {
            "worktrees": worktrees,
            "repo_path": repo_path,
        },
    )


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

    return templates.TemplateResponse(
        request,
        "review.html",
        {
            "review": asdict(review),
            "files": files,
            "commits": commits,
            "comment_counts": comment_counts,
        },
    )
