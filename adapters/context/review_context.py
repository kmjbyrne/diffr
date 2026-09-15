from datetime import UTC, datetime
from pathlib import Path

REVIEWS_DIR = Path.home() / ".local" / "share" / "diffr" / "reviews"


def _review_dir(review_id: str) -> Path:
    d = REVIEWS_DIR / review_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def context_path(review_id: str) -> Path:
    return _review_dir(review_id) / "context.md"


def init_context(
    review_id: str, repo_path: str, branch: str, base_branch: str, files: list[dict]
) -> Path:
    path = context_path(review_id)
    lines = [
        f"# Review: {branch} vs {base_branch}",
        "",
        f"- **Repo**: `{repo_path}`",
        f"- **Branch**: `{branch}`",
        f"- **Base**: `{base_branch}`",
        f"- **Review ID**: `{review_id}`",
        "",
        "## Files changed",
        "",
    ]
    for f in files:
        lines.append(f"- `{f['path']}` ({f.get('status', 'modified')})")
    lines.append("")
    lines.append("## Discussion")
    lines.append("")
    path.write_text("\n".join(lines))
    return path


def append_comment(
    review_id: str,
    file_path: str,
    line_number: int,
    side: str,
    body: str,
    author: str = "user",
) -> None:
    path = context_path(review_id)
    if not path.exists():
        return
    ts = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M:%S")
    entry = f"### [{author}] {file_path}:{line_number} ({side}) - {ts}\n\n{body}\n\n"
    with open(path, "a") as f:
        f.write(entry)
