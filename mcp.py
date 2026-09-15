import json
import uuid
from dataclasses import asdict

from mcp.server.mcpserver import MCPServer

from adapters.db import SqliteCommentRepository, SqliteReviewRepository
from core.models import Comment
from core.services import validate_review_status

mcp = MCPServer("diffr")

_reviews = SqliteReviewRepository()
_comments = SqliteCommentRepository()


@mcp.tool()
def list_reviews(repo_path: str = "", branch: str = "", limit: int = 10) -> str:
    """List reviews, optionally filtered by repo path substring and/or branch name."""
    reviews = _reviews.search(repo_path or None, branch or None, limit)
    return json.dumps([asdict(r) for r in reviews], indent=2)


@mcp.tool()
def get_review_comments(review_id: str) -> str:
    """Get all comments for a specific review, grouped by file."""
    review = _reviews.get(review_id)
    if not review:
        return json.dumps({"error": "Review not found"})

    comments = _comments.for_review(review_id)
    return json.dumps(
        {
            "review": asdict(review),
            "comments": [asdict(c) for c in comments],
        },
        indent=2,
    )


@mcp.tool()
def get_unprocessed_comments() -> str:
    """Get all unprocessed, unresolved user comments across all reviews."""
    return json.dumps(_comments.unprocessed(), indent=2)


@mcp.tool()
def reply_to_comment(
    review_id: str,
    file_path: str,
    line_number: int,
    body: str,
    side: str = "right",
) -> str:
    """Post a reply comment as Claude on a specific line in a review."""
    comment = Comment(
        id=str(uuid.uuid4()),
        review_id=review_id,
        file_path=file_path,
        line_number=line_number,
        side=side,
        body=body,
        author="claude",
        processed=True,
    )
    created = _comments.create(comment)
    return json.dumps(asdict(created), indent=2)


@mcp.tool()
def mark_comments_processed(comment_ids: list[str]) -> str:
    """Mark comments as processed so they won't appear in unprocessed queries."""
    _comments.mark_processed(comment_ids)
    return json.dumps({"processed": len(comment_ids)})


@mcp.tool()
def set_review_status(review_id: str, status: str) -> str:
    """Set a review's status. Valid values: in_progress, approved, changes_requested."""
    error = validate_review_status(status)
    if error:
        return json.dumps({"error": error})
    updated = _reviews.update_status(review_id, status)
    if not updated:
        return json.dumps({"error": "not found"})
    return json.dumps(asdict(updated), indent=2)


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
