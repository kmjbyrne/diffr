import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from core.models import BranchNode, CommitInfo, DiffHunk, DiffLine, FileDiff

_repo_cache: dict[str, tuple[float, list]] = {}
_worktree_cache: dict[str, tuple[float, list]] = {}
_branch_graph_cache: dict[str, tuple[float, list[BranchNode]]] = {}
_CACHE_TTL = 30
_GRAPH_CACHE_TTL = 120


def _resolve_base_ref(repo_path: str, base: str) -> str:
    """Use origin/<base> when it exists and is ahead of the local ref."""
    remote_ref = f"origin/{base}"
    remote_sha = _run_git(repo_path, "rev-parse", "--verify", remote_ref)
    if not remote_sha:
        return base
    local_sha = _run_git(repo_path, "rev-parse", "--verify", base)
    if not local_sha:
        return remote_ref
    if remote_sha == local_sha:
        return base
    behind = _run_git(repo_path, "rev-list", "--count", f"{base}..{remote_ref}")
    if behind and int(behind) > 0:
        return remote_ref
    return base


def is_branch_up_to_date(repo_path: str, base: str, head: str = "HEAD") -> bool:
    """True when HEAD already contains the merge-base with the resolved base ref."""
    resolved = _resolve_base_ref(repo_path, base)
    merge_base = _run_git(repo_path, "merge-base", resolved, head)
    base_sha = _run_git(repo_path, "rev-parse", resolved)
    return bool(merge_base and base_sha and merge_base == base_sha)


@dataclass
class Worktree:
    path: str
    branch: str
    repo_path: str
    files_changed: int = 0
    insertions: int = 0
    deletions: int = 0


@dataclass
class RepoInfo:
    path: str
    current_branch: str
    default_branch: str
    remote_url: str | None = None


@dataclass
class DiscoveredRepo:
    path: str
    name: str
    default_branch: str
    worktree_count: int = 0


def _run_git(repo_path: str, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", repo_path, *args],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    return result.stdout.strip()


def _run_git_in(worktree_path: str, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", worktree_path, *args],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    return result.stdout.strip()


def get_repo_root(path: str) -> str | None:
    try:
        return _run_git(path, "rev-parse", "--show-toplevel") or None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def get_main_repo_root(path: str) -> str | None:
    """Resolve to the main repository root, even from a worktree."""
    try:
        git_common = _run_git(path, "rev-parse", "--git-common-dir")
        if git_common and not git_common.endswith("/.git"):
            git_common = git_common.rstrip("/")
        if git_common and git_common.endswith("/.git"):
            return str(Path(git_common).parent.resolve())
        return get_repo_root(path)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return get_repo_root(path)


def get_default_branch(repo_path: str) -> str:
    ref = _run_git(repo_path, "symbolic-ref", "refs/remotes/origin/HEAD")
    if ref:
        return ref.split("/")[-1]
    for candidate in ("main", "master", "develop"):
        result = _run_git(repo_path, "rev-parse", "--verify", f"refs/heads/{candidate}")
        if result:
            return candidate
    return "main"


def get_diffstat(repo_path: str, base: str, head: str = "HEAD") -> tuple[int, int, int]:
    output = _run_git(repo_path, "diff", "--shortstat", f"{base}...{head}")
    if not output:
        return 0, 0, 0
    files = insertions = deletions = 0
    m = re.search(r"(\d+) files? changed", output)
    if m:
        files = int(m.group(1))
    m = re.search(r"(\d+) insertions?", output)
    if m:
        insertions = int(m.group(1))
    m = re.search(r"(\d+) deletions?", output)
    if m:
        deletions = int(m.group(1))
    return files, insertions, deletions


def get_repo_info(repo_path: str) -> RepoInfo:
    branch = _run_git(repo_path, "rev-parse", "--abbrev-ref", "HEAD")
    default = get_default_branch(repo_path)
    remote = _run_git(repo_path, "config", "--get", "remote.origin.url") or None
    return RepoInfo(
        path=repo_path,
        current_branch=branch or "HEAD",
        default_branch=default,
        remote_url=remote,
    )


def get_branches(repo_path: str) -> list[str]:
    output = _run_git(repo_path, "branch", "--format=%(refname:short)")
    if not output:
        return []
    return [b.strip() for b in output.split("\n") if b.strip()]


def create_branch(repo_path: str, branch_name: str, start_point: str = "HEAD") -> str:
    _run_git(repo_path, "branch", branch_name, start_point)
    return branch_name


def get_commits(repo_path: str, base: str, head: str = "HEAD") -> list[CommitInfo]:
    resolved_base = _resolve_base_ref(repo_path, base)
    output = _run_git(
        repo_path,
        "log",
        "--format=%H%n%h%n%s%n%an%n%ai",
        f"{resolved_base}...{head}",
    )
    if not output:
        return []
    lines = output.split("\n")
    commits = []
    i = 0
    while i + 4 < len(lines):
        commits.append(
            CommitInfo(
                sha=lines[i],
                short_sha=lines[i + 1],
                subject=lines[i + 2],
                author=lines[i + 3],
                date=lines[i + 4],
            )
        )
        i += 5
    return commits


def get_branch_graph(repo_path: str) -> list[BranchNode]:
    now = time.monotonic()
    cached = _branch_graph_cache.get(repo_path)
    if cached and (now - cached[0]) < _GRAPH_CACHE_TTL:
        return cached[1]
    nodes = list(iter_branch_nodes(repo_path))
    roots = _build_branch_tree(repo_path, nodes)
    _branch_graph_cache[repo_path] = (time.monotonic(), roots)
    return roots


def get_branch_graph_cached(repo_path: str) -> tuple[list[BranchNode], bool]:
    cached = _branch_graph_cache.get(repo_path)
    if cached:
        stale = (time.monotonic() - cached[0]) >= _GRAPH_CACHE_TTL
        return cached[1], stale
    return [], True


def refresh_branch_graph(repo_path: str) -> list[BranchNode]:
    try:
        nodes = list(iter_branch_nodes(repo_path))
        roots = _build_branch_tree(repo_path, nodes)
    except subprocess.TimeoutExpired:
        nodes = list(iter_branch_nodes(repo_path))
        for n in nodes:
            n.children = []
        roots = nodes
    _branch_graph_cache[repo_path] = (time.monotonic(), roots)
    return roots


def iter_branch_nodes(repo_path: str):
    default_branch = get_default_branch(repo_path)
    wt_branches = {wt.branch for wt in discover_worktrees(repo_path)}

    ref_data = _run_git(
        repo_path, "for-each-ref",
        "--format=%(refname:short)%09%(objectname)%09%(authorname)%09%(creatordate:iso-strict)",
        "refs/heads/",
    )
    if not ref_data:
        return

    for line in ref_data.split("\n"):
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 4:
            continue
        name, head_sha, author, date = parts[0], parts[1], parts[2], parts[3]
        if name == default_branch:
            continue
        if name in wt_branches:
            merge_base = _run_git(repo_path, "merge-base", default_branch, name) or head_sha
            ahead = _run_git(repo_path, "rev-list", "--count", f"{default_branch}..{name}")
            behind = _run_git(repo_path, "rev-list", "--count", f"{name}..{default_branch}")
        else:
            merge_base = head_sha
            ahead = 0
            behind = 0
        yield BranchNode(
            name=name,
            head_sha=head_sha,
            merge_base=merge_base,
            ahead=int(ahead) if ahead and str(ahead).isdigit() else 0,
            behind=int(behind) if behind and str(behind).isdigit() else 0,
            author=author,
            date=date,
            parent=default_branch,
        )


_MAX_BRANCHES_FOR_TREE = 30


def _build_branch_tree(repo_path: str, nodes: list[BranchNode]) -> list[BranchNode]:
    by_name: dict[str, BranchNode] = {n.name: n for n in nodes}

    for node in nodes:
        node.children = []

    if len(nodes) <= _MAX_BRANCHES_FOR_TREE:
        wt_branches = {wt.branch for wt in discover_worktrees(repo_path)}
        candidates = [n for n in nodes if n.name in wt_branches]
        names = [n.name for n in candidates]

        for name in names:
            node = by_name[name]
            best_parent = node.parent
            best_distance = -1
            for cand_name in names:
                if cand_name == name:
                    continue
                cand = by_name[cand_name]
                if cand.merge_base == node.merge_base:
                    continue
                try:
                    mb = _run_git(repo_path, "merge-base", cand_name, name)
                except subprocess.TimeoutExpired:
                    continue
                if mb != cand.head_sha:
                    continue
                dist_out = _run_git(repo_path, "rev-list", "--count", f"{cand.head_sha}..{node.head_sha}")
                dist = int(dist_out) if dist_out.isdigit() else 999999
                if best_distance < 0 or dist < best_distance:
                    best_distance = dist
                    best_parent = cand_name
            node.parent = best_parent

    roots: list[BranchNode] = []
    for node in by_name.values():
        if node.parent in by_name:
            by_name[node.parent].children.append(node)
        else:
            roots.append(node)

    roots.sort(key=lambda n: n.date, reverse=True)
    for node in by_name.values():
        node.children.sort(key=lambda n: n.date, reverse=True)

    return roots


def discover_repos(scan_paths: list[str], max_depth: int = 2) -> list[DiscoveredRepo]:
    cache_key = "|".join(sorted(scan_paths)) + f"|{max_depth}"
    now = time.monotonic()
    cached = _repo_cache.get(cache_key)
    if cached and (now - cached[0]) < _CACHE_TTL:
        return cached[1]

    repos: list[DiscoveredRepo] = []
    seen: set[str] = set()

    for scan_path in scan_paths:
        root = Path(scan_path).expanduser().resolve()
        if not root.is_dir():
            continue
        _scan_dir(root, repos, seen, max_depth, 0)

    repos.sort(key=lambda r: r.name.lower())
    _repo_cache[cache_key] = (now, repos)
    return repos


def discover_repos_stale(scan_paths: list[str], max_depth: int = 2) -> tuple[list[DiscoveredRepo], bool]:
    cache_key = "|".join(sorted(scan_paths)) + f"|{max_depth}"
    cached = _repo_cache.get(cache_key)
    if cached:
        stale = (time.monotonic() - cached[0]) >= _CACHE_TTL
        return cached[1], stale
    return [], True


def _scan_dir(
    directory: Path,
    repos: list[DiscoveredRepo],
    seen: set[str],
    max_depth: int,
    current_depth: int,
) -> None:
    if current_depth > max_depth:
        return

    git_dir = directory / ".git"
    if git_dir.exists():
        resolved = str(directory.resolve())
        if resolved not in seen:
            seen.add(resolved)
            default = get_default_branch(resolved)
            wt_output = _run_git(resolved, "worktree", "list", "--porcelain")
            wt_count = max(0, wt_output.count("\nworktree ")) if wt_output else 0
            repos.append(
                DiscoveredRepo(
                    path=resolved,
                    name=directory.name,
                    default_branch=default,
                    worktree_count=wt_count,
                )
            )
        return

    try:
        for child in sorted(directory.iterdir()):
            if child.name.startswith(".") or child.name == "node_modules":
                continue
            if child.is_dir() and not child.is_symlink():
                _scan_dir(child, repos, seen, max_depth, current_depth + 1)
    except PermissionError:
        pass


def discover_worktrees(repo_path: str) -> list[Worktree]:
    now = time.monotonic()
    cached = _worktree_cache.get(repo_path)
    if cached and (now - cached[0]) < _CACHE_TTL:
        return cached[1]

    worktrees: list[Worktree] = []

    root = get_repo_root(repo_path)
    if not root:
        return worktrees

    default_branch = get_default_branch(root)

    claude_wt_dir = Path(root) / ".claude" / "worktrees"
    if claude_wt_dir.is_dir():
        for child in claude_wt_dir.iterdir():
            if child.is_dir() and (child / ".git").exists():
                branch = _run_git_in(str(child), "rev-parse", "--abbrev-ref", "HEAD")
                worktrees.append(
                    Worktree(
                        path=str(child),
                        branch=branch or "unknown",
                        repo_path=root,
                    )
                )

    porcelain = _run_git(root, "worktree", "list", "--porcelain")
    if porcelain:
        current_path = None
        current_branch = None
        for line in porcelain.split("\n"):
            if line.startswith("worktree "):
                current_path = line[len("worktree ") :]
            elif line.startswith("branch "):
                current_branch = line[len("branch refs/heads/") :]
            elif line == "" and current_path:
                if current_path != root:
                    already = any(w.path == current_path for w in worktrees)
                    if not already:
                        worktrees.append(
                            Worktree(
                                path=current_path,
                                branch=current_branch or "unknown",
                                repo_path=root,
                            )
                        )
                current_path = None
                current_branch = None
        if current_path and current_path != root:
            already = any(w.path == current_path for w in worktrees)
            if not already:
                worktrees.append(
                    Worktree(
                        path=current_path,
                        branch=current_branch or "unknown",
                        repo_path=root,
                    )
                )

    for wt in worktrees:
        try:
            resolved = _resolve_base_ref(wt.path, default_branch)
            files, ins, dels = get_diffstat(wt.path, resolved, "HEAD")
            wt.files_changed = files
            wt.insertions = ins
            wt.deletions = dels
        except (subprocess.SubprocessError, OSError):
            pass

    _worktree_cache[repo_path] = (time.monotonic(), worktrees)
    return worktrees


@dataclass
class RebaseResult:
    ok: bool
    message: str


def rebase_worktree(worktree_path: str, onto: str) -> RebaseResult:
    result = subprocess.run(
        ["git", "-C", worktree_path, "rebase", onto],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if result.returncode == 0:
        _worktree_cache.clear()
        return RebaseResult(ok=True, message=f"Rebased onto {onto}")
    subprocess.run(
        ["git", "-C", worktree_path, "rebase", "--abort"],
        capture_output=True,
        timeout=10,
        check=False,
    )
    stderr = result.stderr.strip()
    return RebaseResult(ok=False, message=stderr or "Rebase failed with conflicts")


def rebase_branch(repo_path: str, branch: str, onto: str) -> RebaseResult:
    worktrees = discover_worktrees(repo_path)
    wt_path = next((w.path for w in worktrees if w.branch == branch), None)
    if not wt_path:
        return RebaseResult(ok=False, message=f"No worktree found for branch {branch}")
    return rebase_worktree(wt_path, onto)


def _is_ancestor(repo_path: str, maybe_ancestor: str, descendant: str) -> bool:
    result = subprocess.run(
        ["git", "-C", repo_path, "merge-base", "--is-ancestor", maybe_ancestor, descendant],
        capture_output=True,
        timeout=30,
        check=False,
    )
    return result.returncode == 0


def detect_stacks(repo_path: str) -> list[list[str]]:
    """Detect branch stacks among worktree branches and local branches.

    Returns chains of branch names where each branch is based on the previous.
    For each worktree branch, walks its history back to find local branch refs
    that point to intermediate commits, identifying stack relationships even
    when intermediate branches have no worktree.
    """
    worktrees = discover_worktrees(repo_path)
    if not worktrees:
        return []

    default_branch = get_default_branch(repo_path)
    wt_branches = [wt.branch for wt in worktrees if wt.branch != default_branch]
    wt_set = set(wt_branches)

    heads: dict[str, str] = {}
    default_sha = _run_git(repo_path, "rev-parse", default_branch)
    for b in wt_branches:
        sha = _run_git(repo_path, "rev-parse", b)
        if sha:
            heads[b] = sha

    # Exclude worktree branches already merged into default
    merged_output = _run_git(repo_path, "branch", "--merged", default_branch, "--format=%(refname:short)")
    merged_branches = set(merged_output.split("\n")) if merged_output else set()
    wt_branches = [b for b in wt_branches if b not in merged_branches]
    wt_set = set(wt_branches)

    sha_to_branches: dict[str, list[str]] = {}
    all_local = get_branches(repo_path)
    for b in all_local:
        if b == default_branch or b in wt_set:
            continue
        sha = _run_git(repo_path, "rev-parse", b)
        if sha:
            sha_to_branches.setdefault(sha, []).append(b)

    # Also map worktree branch HEADs so they can be found in other branches' logs
    wt_sha_to_branch: dict[str, str] = {}
    for b in wt_branches:
        if b in heads:
            wt_sha_to_branch[heads[b]] = b

    extra_parents: set[str] = set()
    branch_positions: dict[str, dict[str, int]] = {}

    for wb in wt_branches:
        if wb not in heads:
            continue
        log = _run_git(repo_path, "log", "--first-parent", "--format=%H",
                       f"{default_branch}..{wb}")
        if not log:
            continue
        shas = [s.strip() for s in log.split("\n") if s.strip()]
        positions: dict[str, int] = {}
        positions[wb] = 0
        for idx, commit_sha in enumerate(shas):
            if commit_sha == heads[wb]:
                continue
            if commit_sha in sha_to_branches:
                for branch_name in sha_to_branches[commit_sha]:
                    if branch_name not in extra_parents:
                        heads[branch_name] = commit_sha
                        extra_parents.add(branch_name)
                    if branch_name not in positions:
                        positions[branch_name] = idx
            if commit_sha in wt_sha_to_branch:
                other_wt = wt_sha_to_branch[commit_sha]
                if other_wt != wb and other_wt not in positions:
                    positions[other_wt] = idx
        branch_positions[wb] = positions

    all_candidates = wt_branches + list(extra_parents)
    cand_set = set(all_candidates)

    # Derive parent_of from log positions: for each candidate, find closest
    # ancestor among other candidates within any log walk.
    parent_of: dict[str, str] = {}
    for wb, positions in branch_positions.items():
        branches_in_log = sorted(
            [(b, pos) for b, pos in positions.items() if b in cand_set],
            key=lambda x: x[1],
        )
        for i, (branch, pos) in enumerate(branches_in_log):
            if i + 1 < len(branches_in_log):
                next_branch, next_pos = branches_in_log[i + 1]
                dist = next_pos - pos
                if branch not in parent_of or dist < parent_of[branch][1]:
                    parent_of[branch] = (next_branch, dist)

    parent_of = {b: parent for b, (parent, _dist) in parent_of.items()}

    # Break cycles in parent_of
    def has_cycle(start: str) -> bool:
        visited: set[str] = set()
        current = start
        while current in parent_of:
            if current in visited:
                return True
            visited.add(current)
            current = parent_of[current]
        return False

    for b in list(parent_of):
        if has_cycle(b):
            del parent_of[b]

    children: dict[str, list[str]] = {}
    roots = []
    for b in all_candidates:
        if b in parent_of:
            children.setdefault(parent_of[b], []).append(b)

    # Branches with many children are shared ancestors (like main), not stack
    # members. Remove them and treat their children as independent roots.
    hubs = {b for b, kids in children.items() if len(kids) > 2}
    for hub in hubs:
        del children[hub]
        for b in list(parent_of):
            if parent_of[b] == hub:
                del parent_of[b]

    for b in all_candidates:
        if b not in parent_of and b in children:
            roots.append(b)

    def build_chain(start: str) -> list[str]:
        chain = [start]
        current = start
        seen: set[str] = {start}
        while current in children:
            kids = [k for k in children[current] if k not in seen]
            if not kids:
                break
            if len(kids) == 1:
                nxt = kids[0]
            else:
                best, best_len = kids[0], 0
                for k in kids:
                    sub = build_chain(k)
                    if len(sub) > best_len:
                        best, best_len = k, len(sub)
                nxt = best
            chain.append(nxt)
            seen.add(nxt)
            current = nxt
        return chain

    chains: list[list[str]] = []
    for root in roots:
        chain = build_chain(root)
        if len(chain) >= 2:
            chains.append(chain)

    return chains, {"parent_of": parent_of, "extra_parents": list(extra_parents), "roots": roots, "children": {k: v for k, v in children.items()}}


def get_diff_files(repo_path: str, base: str, head: str = "HEAD") -> list[dict]:
    resolved_base = _resolve_base_ref(repo_path, base)
    output = _run_git(repo_path, "diff", "--name-status", f"{resolved_base}...{head}")
    files = []
    for line in output.split("\n"):
        if not line.strip():
            continue
        parts = line.split("\t")
        status_code = parts[0][0]
        status_map = {"A": "added", "D": "removed", "M": "modified", "R": "renamed"}
        file_path = parts[-1]
        files.append(
            {
                "path": file_path,
                "status": status_map.get(status_code, "modified"),
            }
        )

    numstat = _run_git(repo_path, "diff", "--numstat", f"{resolved_base}...{head}")
    stat_map: dict[str, tuple[int, int]] = {}
    for line in numstat.split("\n"):
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) >= 3:
            adds = int(parts[0]) if parts[0] != "-" else 0
            dels = int(parts[1]) if parts[1] != "-" else 0
            stat_map[parts[2]] = (adds, dels)

    for f in files:
        adds, dels = stat_map.get(f["path"], (0, 0))
        f["additions"] = adds
        f["deletions"] = dels

    return files


def get_file_diff(repo_path: str, base: str, head: str, file_path: str) -> FileDiff:
    resolved_base = _resolve_base_ref(repo_path, base)
    output = _run_git(repo_path, "diff", f"{resolved_base}...{head}", "--", file_path)
    return parse_unified_diff(output, file_path)


def parse_unified_diff(diff_text: str, file_path: str) -> FileDiff:
    result = FileDiff(file_path=file_path)
    if not diff_text:
        return result

    hunk_header_re = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@(.*)")
    current_hunk: DiffHunk | None = None
    left_num = 0
    right_num = 0

    for line in diff_text.split("\n"):
        match = hunk_header_re.match(line)
        if match:
            current_hunk = DiffHunk(header=line)
            result.hunks.append(current_hunk)
            left_num = int(match.group(1))
            right_num = int(match.group(2))
            continue

        if current_hunk is None:
            if line.startswith("new file"):
                result.status = "added"
            elif line.startswith("deleted file"):
                result.status = "removed"
            elif line.startswith("rename"):
                result.status = "renamed"
            continue

        if line.startswith("-"):
            current_hunk.lines.append(
                DiffLine(
                    left_num=left_num,
                    right_num=None,
                    left_content=line[1:],
                    right_content="",
                    line_type="removed",
                )
            )
            left_num += 1
        elif line.startswith("+"):
            current_hunk.lines.append(
                DiffLine(
                    left_num=None,
                    right_num=right_num,
                    left_content="",
                    right_content=line[1:],
                    line_type="added",
                )
            )
            right_num += 1
        elif line.startswith(" "):
            current_hunk.lines.append(
                DiffLine(
                    left_num=left_num,
                    right_num=right_num,
                    left_content=line[1:],
                    right_content=line[1:],
                    line_type="context",
                )
            )
            left_num += 1
            right_num += 1

    _pair_modifications(result)
    return result


def _pair_modifications(diff: FileDiff) -> None:
    for hunk in diff.hunks:
        i = 0
        new_lines: list[DiffLine] = []
        while i < len(hunk.lines):
            removed_block: list[DiffLine] = []
            added_block: list[DiffLine] = []

            while i < len(hunk.lines) and hunk.lines[i].line_type == "removed":
                removed_block.append(hunk.lines[i])
                i += 1
            while i < len(hunk.lines) and hunk.lines[i].line_type == "added":
                added_block.append(hunk.lines[i])
                i += 1

            if removed_block and added_block:
                pairs = max(len(removed_block), len(added_block))
                for j in range(pairs):
                    left = removed_block[j] if j < len(removed_block) else None
                    right = added_block[j] if j < len(added_block) else None
                    new_lines.append(
                        DiffLine(
                            left_num=left.left_num if left else None,
                            right_num=right.right_num if right else None,
                            left_content=left.left_content if left else "",
                            right_content=right.right_content if right else "",
                            line_type="modified",
                        )
                    )
            else:
                new_lines.extend(removed_block)
                new_lines.extend(added_block)

            if not removed_block and not added_block and i < len(hunk.lines):
                new_lines.append(hunk.lines[i])
                i += 1

        hunk.lines = new_lines
