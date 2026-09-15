import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from core.models import CommitInfo, DiffHunk, DiffLine, FileDiff


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


def get_commits(repo_path: str, base: str, head: str = "HEAD") -> list[CommitInfo]:
    output = _run_git(
        repo_path,
        "log",
        "--format=%H%n%h%n%s%n%an%n%ai",
        f"{base}...{head}",
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


def discover_repos(scan_paths: list[str], max_depth: int = 2) -> list[DiscoveredRepo]:
    repos: list[DiscoveredRepo] = []
    seen: set[str] = set()

    for scan_path in scan_paths:
        root = Path(scan_path).expanduser().resolve()
        if not root.is_dir():
            continue
        _scan_dir(root, repos, seen, max_depth, 0)

    repos.sort(key=lambda r: r.name.lower())
    return repos


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
            wt_count = len(discover_worktrees(resolved))
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
            files, ins, dels = get_diffstat(wt.path, default_branch, "HEAD")
            wt.files_changed = files
            wt.insertions = ins
            wt.deletions = dels
        except (subprocess.SubprocessError, OSError):
            pass

    return worktrees


def get_diff_files(repo_path: str, base: str, head: str = "HEAD") -> list[dict]:
    output = _run_git(repo_path, "diff", "--name-status", f"{base}...{head}")
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
    return files


def get_file_diff(repo_path: str, base: str, head: str, file_path: str) -> FileDiff:
    output = _run_git(repo_path, "diff", f"{base}...{head}", "--", file_path)
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
