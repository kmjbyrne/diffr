from dataclasses import dataclass, field


@dataclass
class Review:
    id: str
    repo_path: str
    branch: str
    base_branch: str = "main"
    status: str = "in_progress"
    created_at: str = ""
    updated_at: str = ""


@dataclass
class Comment:
    id: str
    review_id: str
    file_path: str
    line_number: int
    side: str = "right"
    body: str = ""
    author: str = "user"
    resolved: bool = False
    processed: bool = False
    parent_id: str | None = None
    created_at: str = ""
    updated_at: str = ""


@dataclass
class Reaction:
    id: str
    target_type: str
    target_id: str
    review_id: str
    emoji: str
    created_at: str = ""


AVAILABLE_EMOJIS = ["thumbsup", "thumbsdown", "eyes", "question", "flag", "fire"]

VALID_REVIEW_STATUSES = ("in_progress", "approved", "changes_requested")


@dataclass
class DiffLine:
    left_num: int | None
    right_num: int | None
    left_content: str
    right_content: str
    line_type: str


@dataclass
class DiffHunk:
    header: str
    lines: list[DiffLine] = field(default_factory=list)


@dataclass
class FileDiff:
    file_path: str
    hunks: list[DiffHunk] = field(default_factory=list)
    status: str = "modified"


@dataclass
class CommitInfo:
    sha: str
    short_sha: str
    subject: str
    author: str
    date: str
