from adapters.db.connection import get_connection
from core.models import Comment
from ports.repository import CommentRepository


def _row_to_comment(row) -> Comment:
    return Comment(
        id=row["id"],
        review_id=row["review_id"],
        file_path=row["file_path"],
        line_number=row["line_number"],
        side=row["side"],
        body=row["body"],
        author=row["author"],
        resolved=bool(row["resolved"]),
        processed=bool(row["processed"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class SqliteCommentRepository(CommentRepository):
    def create(self, comment: Comment) -> Comment:
        conn = get_connection()
        conn.execute(
            "INSERT INTO comments (id, review_id, file_path, line_number, side, body, author, processed) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                comment.id,
                comment.review_id,
                comment.file_path,
                comment.line_number,
                comment.side,
                comment.body,
                comment.author,
                int(comment.processed),
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM comments WHERE id = ?", (comment.id,)
        ).fetchone()
        conn.close()
        return _row_to_comment(row)

    def get(self, comment_id: str) -> Comment | None:
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM comments WHERE id = ?", (comment_id,)
        ).fetchone()
        conn.close()
        return _row_to_comment(row) if row else None

    def update(self, comment_id, body=None, resolved=None) -> Comment | None:
        conn = get_connection()
        if body is not None:
            conn.execute(
                "UPDATE comments SET body = ?, updated_at = datetime('now') WHERE id = ?",
                (body, comment_id),
            )
        if resolved is not None:
            conn.execute(
                "UPDATE comments SET resolved = ?, updated_at = datetime('now') WHERE id = ?",
                (1 if resolved else 0, comment_id),
            )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM comments WHERE id = ?", (comment_id,)
        ).fetchone()
        conn.close()
        return _row_to_comment(row) if row else None

    def delete(self, comment_id: str) -> None:
        conn = get_connection()
        conn.execute("DELETE FROM comments WHERE id = ?", (comment_id,))
        conn.commit()
        conn.close()

    def for_review(self, review_id: str) -> list[Comment]:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM comments WHERE review_id = ? ORDER BY file_path, line_number, created_at",
            (review_id,),
        ).fetchall()
        conn.close()
        return [_row_to_comment(r) for r in rows]

    def for_file(self, review_id: str, file_path: str) -> list[Comment]:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM comments WHERE review_id = ? AND file_path = ? ORDER BY line_number, created_at",
            (review_id, file_path),
        ).fetchall()
        conn.close()
        return [_row_to_comment(r) for r in rows]

    def unprocessed(self, review_id=None) -> list[dict]:
        conn = get_connection()
        rows = conn.execute(
            "SELECT c.*, r.repo_path, r.branch, r.base_branch "
            "FROM comments c JOIN reviews r ON c.review_id = r.id "
            "WHERE c.processed = 0 AND c.resolved = 0 AND c.author = 'user' "
            "ORDER BY c.created_at",
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def pending_count(self, review_id=None) -> int:
        conn = get_connection()
        if review_id:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM comments "
                "WHERE review_id = ? AND processed = 0 AND resolved = 0 AND author = 'user'",
                (review_id,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM comments "
                "WHERE processed = 0 AND resolved = 0 AND author = 'user'",
            ).fetchone()
        conn.close()
        return row["cnt"]

    def claude_replies_since(self, review_id: str, since: str) -> int:
        conn = get_connection()
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM comments "
            "WHERE review_id = ? AND author = 'claude' AND created_at > ?",
            (review_id, since),
        ).fetchone()
        conn.close()
        return row["cnt"]

    def mark_processed(self, comment_ids: list[str]) -> None:
        if not comment_ids:
            return
        conn = get_connection()
        placeholders = ",".join("?" for _ in comment_ids)
        conn.execute(
            f"UPDATE comments SET processed = 1 WHERE id IN ({placeholders})",
            comment_ids,
        )
        conn.commit()
        conn.close()

    def mark_line_processed(self, review_id, file_path, line_number, side) -> None:
        conn = get_connection()
        conn.execute(
            "UPDATE comments SET processed = 1 WHERE review_id = ? AND file_path = ? "
            "AND line_number = ? AND side = ? AND author = 'user' AND processed = 0",
            (review_id, file_path, line_number, side),
        )
        conn.commit()
        conn.close()

    def comment_counts_by_file(self, review_id: str) -> dict[str, dict]:
        conn = get_connection()
        rows = conn.execute(
            "SELECT file_path, COUNT(*) as total, "
            "SUM(CASE WHEN resolved = 0 THEN 1 ELSE 0 END) as unresolved "
            "FROM comments WHERE review_id = ? GROUP BY file_path",
            (review_id,),
        ).fetchall()
        conn.close()
        return {
            row["file_path"]: {"total": row["total"], "unresolved": row["unresolved"]}
            for row in rows
        }
