import json
import os
from dataclasses import dataclass, field
from pathlib import Path

CLAUDE_DIR = Path.home() / ".claude"
PROJECTS_DIR = CLAUDE_DIR / "projects"
JOBS_DIR = CLAUDE_DIR / "jobs"
DAEMON_ROSTER = CLAUDE_DIR / "daemon" / "roster.json"


@dataclass
class ClaudeSession:
    session_id: str
    title: str = ""
    project_dir: str = ""
    cwd: str = ""
    state: str = "unknown"
    detail: str = ""
    intent: str = ""
    model: str = ""
    tokens: int = 0
    is_job: bool = False


def _decode_project_path(encoded: str) -> str:
    return encoded.replace("-", "/")


def get_active_workers() -> dict[str, dict]:
    if not DAEMON_ROSTER.exists():
        return {}
    try:
        with open(DAEMON_ROSTER) as f:
            data = json.load(f)
        return data.get("workers", {})
    except (json.JSONDecodeError, OSError):
        return {}


def get_jobs(limit: int = 30) -> list[ClaudeSession]:
    sessions: list[ClaudeSession] = []
    if not JOBS_DIR.is_dir():
        return sessions

    job_dirs = sorted(
        JOBS_DIR.iterdir(),
        key=lambda d: d.stat().st_mtime if d.is_dir() else 0,
        reverse=True,
    )

    for job_dir in job_dirs[:limit]:
        if not job_dir.is_dir():
            continue
        state_file = job_dir / "state.json"
        if not state_file.exists():
            continue
        try:
            with open(state_file) as f:
                data = json.load(f)
            sessions.append(
                ClaudeSession(
                    session_id=data.get("sessionId", job_dir.name),
                    title=data.get("name", ""),
                    cwd=data.get("cwd", ""),
                    state=data.get("state", "unknown"),
                    detail=data.get("detail", ""),
                    intent=data.get("intent", ""),
                    model=data.get("providerEnv", {}).get("ANTHROPIC_MODEL", ""),
                    tokens=data.get("tokens", 0),
                    is_job=True,
                )
            )
        except (json.JSONDecodeError, OSError):
            continue

    return sessions


def get_recent_sessions(limit: int = 30) -> list[ClaudeSession]:
    sessions: list[ClaudeSession] = []
    if not PROJECTS_DIR.is_dir():
        return sessions

    session_files: list[tuple[float, Path, str]] = []

    for project_dir in PROJECTS_DIR.iterdir():
        if not project_dir.is_dir():
            continue
        project_path = _decode_project_path(project_dir.name)
        for jsonl_file in project_dir.glob("*.jsonl"):
            try:
                mtime = jsonl_file.stat().st_mtime
                session_files.append((mtime, jsonl_file, project_path))
            except OSError:
                continue

    session_files.sort(key=lambda x: x[0], reverse=True)

    for mtime, jsonl_file, project_path in session_files[:limit]:
        session_id = jsonl_file.stem
        title = ""
        try:
            with open(jsonl_file) as f:
                for raw_line in f:
                    line = raw_line.strip()
                    if not line:
                        continue
                    obj = json.loads(line)
                    if obj.get("type") == "ai-title":
                        title = obj.get("aiTitle", "")
                        break
        except (json.JSONDecodeError, OSError):
            continue

        sessions.append(
            ClaudeSession(
                session_id=session_id,
                title=title,
                project_dir=project_path,
                cwd=project_path,
                state="completed",
            )
        )

    return sessions


def get_all_sessions(limit: int = 50) -> list[ClaudeSession]:
    active_workers = get_active_workers()
    jobs = get_jobs(limit)
    recent = get_recent_sessions(limit)

    for worker_id, info in active_workers.items():
        sid = info.get("sessionId", worker_id)
        already = any(s.session_id == sid for s in jobs)
        if not already:
            jobs.append(
                ClaudeSession(
                    session_id=sid,
                    cwd=info.get("cwd", ""),
                    state="active",
                    is_job=True,
                )
            )

    job_ids = {s.session_id for s in jobs}
    combined = jobs + [s for s in recent if s.session_id not in job_ids]
    return combined[:limit]
