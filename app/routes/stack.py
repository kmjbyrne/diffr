import asyncio
import json
import uuid
from dataclasses import asdict

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

from adapters.git import (
    detect_stacks,
    discover_repos,
    discover_worktrees,
    get_branch_graph,
    get_branch_graph_cached,
    get_branches,
    get_default_branch,
    get_repo_info,
    get_repo_root,
    rebase_branch,
    refresh_branch_graph,
)
from app import deps
from config import load_config
from core.models import Stack

router = APIRouter()


@router.get("/stack")
async def stack_page(request: Request, repo_path: str = ""):
    templates = request.app.state.templates
    config = load_config()

    if not repo_path:
        repo_path = config.get("last_repo") or ""

    repos = discover_repos(config["scan_paths"], config.get("max_depth", 2))

    return templates.TemplateResponse(
        request,
        "stack.html",
        {"repo_path": repo_path, "repos": repos},
    )


@router.get("/api/stack", response_class=HTMLResponse)
async def stack_data(request: Request, repo_path: str):
    templates = request.app.state.templates
    root = get_repo_root(repo_path)
    if not root:
        return HTMLResponse('<p class="no-worktrees">Not a git repository.</p>')

    info = get_repo_info(root)
    registered = deps.stacks.for_repo(root)
    worktrees = discover_worktrees(root)
    wt_branches = {wt.branch for wt in worktrees}
    all_branches = get_branches(root)

    reviews: dict[str, dict] = {}
    all_stack_branches = set()
    for s in registered:
        all_stack_branches.update(s.branches)
        for sidecar_list in s.sidecars.values():
            all_stack_branches.update(sidecar_list)
        for b in list(s.branches) + [sb for sl in s.sidecars.values() for sb in sl]:
            found = deps.reviews.search(root, b, limit=1)
            if found:
                reviews[b] = asdict(found[0])

    detected, _debug = await asyncio.to_thread(detect_stacks, root)
    suggestions = [
        chain for chain in detected
        if not all(b in all_stack_branches for b in chain)
    ]

    return templates.TemplateResponse(
        request,
        "partials/stack_map.html",
        {
            "repo_path": root,
            "default_branch": info.default_branch,
            "stacks": registered,
            "suggestions": suggestions,
            "all_branches": all_branches,
            "worktree_branches": wt_branches,
            "reviews": reviews,
            "discovering": False,
        },
    )


class UpdateAllRequest(BaseModel):
    repo_path: str


@router.post("/api/stack/update-all")
async def update_all(data: UpdateAllRequest):
    root = get_repo_root(data.repo_path)
    if not root:
        return {"ok": False, "results": [], "message": "Not a git repository"}

    default_branch = get_default_branch(root)
    roots = get_branch_graph(root)
    results = []

    def rebase_tree(nodes, onto):
        for node in nodes:
            r = rebase_branch(root, node.name, onto)
            results.append({"branch": node.name, "onto": onto, "ok": r.ok, "message": r.message})
            if r.ok and node.children:
                rebase_tree(node.children, node.name)

    rebase_tree(roots, default_branch)

    all_ok = all(r["ok"] for r in results)
    return {"ok": all_ok, "results": results}


class UpdateStackRequest2(BaseModel):
    stack_id: str
    repo_path: str


@router.post("/api/stack/update-stream")
async def update_stack_stream(data: UpdateStackRequest2):
    root = get_repo_root(data.repo_path)
    if not root:
        return StreamingResponse(
            iter(["data: " + json.dumps({"done": True, "error": "Not a git repository"}) + "\n\n"]),
            media_type="text/event-stream",
        )

    stack = deps.stacks.get(data.stack_id)
    if not stack:
        return StreamingResponse(
            iter(["data: " + json.dumps({"done": True, "error": "Stack not found"}) + "\n\n"]),
            media_type="text/event-stream",
        )

    default_branch = get_default_branch(root)

    async def generate():
        branches = stack.branches
        for sidecar in stack.sidecars.get(default_branch, []):
            yield "data: " + json.dumps({
                "branch": sidecar,
                "onto": default_branch,
                "status": "rebasing",
                "sidecar": True,
            }) + "\n\n"
            sr = await asyncio.to_thread(rebase_branch, root, sidecar, default_branch)
            yield "data: " + json.dumps({
                "branch": sidecar,
                "onto": default_branch,
                "status": "ok" if sr.ok else "failed",
                "message": sr.message,
                "sidecar": True,
            }) + "\n\n"
        for i, branch in enumerate(branches):
            onto = branches[i - 1] if i > 0 else default_branch
            yield "data: " + json.dumps({
                "branch": branch,
                "onto": onto,
                "status": "rebasing",
                "index": i,
                "total": len(branches),
            }) + "\n\n"
            r = await asyncio.to_thread(rebase_branch, root, branch, onto)
            yield "data: " + json.dumps({
                "branch": branch,
                "onto": onto,
                "status": "ok" if r.ok else "failed",
                "message": r.message,
                "index": i,
                "total": len(branches),
            }) + "\n\n"
            for sidecar in stack.sidecars.get(branch, []):
                yield "data: " + json.dumps({
                    "branch": sidecar,
                    "onto": branch,
                    "status": "rebasing",
                    "sidecar": True,
                }) + "\n\n"
                sr = await asyncio.to_thread(rebase_branch, root, sidecar, branch)
                yield "data: " + json.dumps({
                    "branch": sidecar,
                    "onto": branch,
                    "status": "ok" if sr.ok else "failed",
                    "message": sr.message,
                    "sidecar": True,
                }) + "\n\n"
        yield "data: " + json.dumps({"done": True}) + "\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


class CreateStackRequest(BaseModel):
    name: str
    repo_path: str
    branches: list[str]


class UpdateStackRequest(BaseModel):
    name: str | None = None
    branches: list[str] | None = None


@router.get("/api/stacks")
async def list_stacks(repo_path: str):
    root = get_repo_root(repo_path)
    if not root:
        return []
    return [asdict(s) for s in deps.stacks.for_repo(root)]


@router.post("/api/stacks")
async def create_stack(data: CreateStackRequest):
    root = get_repo_root(data.repo_path)
    if not root:
        return {"error": "Not a git repository"}
    stack = Stack(
        id=str(uuid.uuid4()),
        name=data.name,
        repo_path=root,
        branches=data.branches,
    )
    deps.stacks.create(stack)
    return asdict(stack)


@router.get("/api/stacks/freshness")
async def stack_freshness(stack_id: str, repo_path: str):
    from adapters.git import _run_git
    root = get_repo_root(repo_path)
    if not root:
        return {"error": "Not a git repository"}
    stack = deps.stacks.get(stack_id)
    if not stack:
        return {"error": "Stack not found"}

    default_branch = get_default_branch(root)
    branches = stack.branches
    result: dict[str, dict] = {}

    def check_freshness():
        for i, branch in enumerate(branches):
            parent = branches[i - 1] if i > 0 else default_branch
            behind = _run_git(root, "rev-list", "--count", f"{branch}..{parent}")
            behind_count = int(behind) if behind and behind.isdigit() else 0
            result[branch] = {
                "parent": parent,
                "behind": behind_count,
                "stale": behind_count > 0,
            }

    await asyncio.to_thread(check_freshness)
    return result


@router.get("/api/stacks/branch-freshness")
async def branch_freshness(repo_path: str, branch: str, base: str):
    from adapters.git import _run_git
    root = get_repo_root(repo_path)
    if not root:
        return {"error": "Not a git repository"}

    def check():
        behind = _run_git(root, "rev-list", "--count", f"{branch}..{base}")
        return int(behind) if behind and behind.isdigit() else 0

    behind_count = await asyncio.to_thread(check)
    return {"branch": branch, "base": base, "behind": behind_count, "stale": behind_count > 0}


class RebaseBranchRequest(BaseModel):
    repo_path: str
    branch: str
    onto: str


@router.post("/api/stacks/rebase-branch")
async def rebase_single_branch(data: RebaseBranchRequest):
    root = get_repo_root(data.repo_path)
    if not root:
        return {"ok": False, "message": "Not a git repository"}
    result = await asyncio.to_thread(rebase_branch, root, data.branch, data.onto)
    return {"ok": result.ok, "message": result.message}


@router.get("/api/stacks/debug-detect")
async def debug_detect(repo_path: str):
    from adapters.git import _run_git, _is_ancestor, get_branches as gb
    root = get_repo_root(repo_path)
    if not root:
        return {"error": "Not a git repository"}
    worktrees = discover_worktrees(root)
    default_branch = get_default_branch(root)
    wt_branches = [wt.branch for wt in worktrees if wt.branch != default_branch]
    wt_set = set(wt_branches)

    heads = {}
    for b in wt_branches:
        sha = _run_git(root, "rev-parse", b)
        if sha:
            heads[b] = sha

    all_local = gb(root)
    non_wt = [b for b in all_local if b != default_branch and b not in wt_set]

    sha_to_branches = {}
    for b in non_wt:
        sha = _run_git(root, "rev-parse", b)
        if sha:
            sha_to_branches.setdefault(sha, []).append(b)

    target = "eu-core-port-resource"
    target_head = heads.get(target, "NOT FOUND")
    log_output = _run_git(root, "log", "--first-parent", "--format=%H", f"{default_branch}..{target}")
    log_shas = [s.strip() for s in log_output.split("\n") if s.strip()] if log_output else []

    v2_sha = _run_git(root, "rev-parse", "worktree-eu-core-port-v2")
    refactor_sha = _run_git(root, "rev-parse", "eu-core-port-refactor")

    v2_in_log = v2_sha in log_shas if v2_sha else False
    refactor_in_log = refactor_sha in log_shas if refactor_sha else False
    v2_in_map = v2_sha in sha_to_branches if v2_sha else False
    refactor_in_map = refactor_sha in sha_to_branches if refactor_sha else False

    detected, debug_info = await asyncio.to_thread(detect_stacks, root)

    return {
        "default_branch": default_branch,
        "worktree_branches": wt_branches,
        "target_head": target_head,
        "v2_sha": v2_sha or "EMPTY",
        "refactor_sha": refactor_sha or "EMPTY",
        "log_sha_count": len(log_shas),
        "log_first_5": log_shas[:5],
        "v2_in_log": v2_in_log,
        "refactor_in_log": refactor_in_log,
        "v2_in_sha_map": v2_in_map,
        "refactor_in_sha_map": refactor_in_map,
        "sha_map_branches_at_v2": sha_to_branches.get(v2_sha, []) if v2_sha else [],
        "sha_map_branches_at_refactor": sha_to_branches.get(refactor_sha, []) if refactor_sha else [],
        "non_wt_count": len(non_wt),
        "detected_chains": detected,
        "debug": debug_info,
    }


@router.get("/api/stacks/suggest")
async def suggest_stacks(repo_path: str):
    root = get_repo_root(repo_path)
    if not root:
        return []
    existing = deps.stacks.for_repo(root)
    registered = set()
    for s in existing:
        registered.update(s.branches)

    detected, _debug = await asyncio.to_thread(detect_stacks, root)
    return [chain for chain in detected if not all(b in registered for b in chain)]


@router.get("/api/stacks/branches")
async def available_branches(repo_path: str):
    root = get_repo_root(repo_path)
    if not root:
        return []
    return get_branches(root)


@router.put("/api/stacks/{stack_id}")
async def update_stack(stack_id: str, data: UpdateStackRequest):
    result = deps.stacks.update(stack_id, name=data.name, branches=data.branches)
    if not result:
        return {"error": "Stack not found"}
    return asdict(result)


@router.delete("/api/stacks/{stack_id}")
async def delete_stack(stack_id: str):
    deps.stacks.delete(stack_id)
    return {"ok": True}


class SidecarRequest(BaseModel):
    branch: str
    parent: str


@router.post("/api/stacks/{stack_id}/sidecars")
async def add_sidecar(stack_id: str, data: SidecarRequest):
    stack = deps.stacks.get(stack_id)
    if not stack:
        return {"error": "Stack not found"}
    default_branch = get_default_branch(get_repo_root(stack.repo_path) or stack.repo_path)
    valid_parents = set(stack.branches) | {default_branch}
    if data.parent not in valid_parents:
        return {"error": f"{data.parent} is not in this stack"}
    sidecars = dict(stack.sidecars)
    sidecars.setdefault(data.parent, [])
    if data.branch not in sidecars[data.parent]:
        sidecars[data.parent].append(data.branch)
    result = deps.stacks.update(stack_id, sidecars=sidecars)
    return asdict(result)


@router.delete("/api/stacks/{stack_id}/sidecars/{branch}")
async def remove_sidecar(stack_id: str, branch: str):
    stack = deps.stacks.get(stack_id)
    if not stack:
        return {"error": "Stack not found"}
    sidecars = dict(stack.sidecars)
    for parent, branches in sidecars.items():
        if branch in branches:
            branches.remove(branch)
    sidecars = {k: v for k, v in sidecars.items() if v}
    result = deps.stacks.update(stack_id, sidecars=sidecars)
    return asdict(result)


