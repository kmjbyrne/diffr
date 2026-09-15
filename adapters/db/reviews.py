from adapters.db.connection import get_connection
from core.models import Review
from ports.repository import ReviewRepository


def _row_to_review(row) -> Review:
    return Review(
        id=row["id"],
        repo_path=row["repo_path"],
        branch=row["branch"],
        base_branch=row["base_branch"],
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class SqliteReviewRepository(ReviewRepository):
    def create(self, review: Review) -> Review:
        conn = get_connection()
        conn.execute(
            "INSERT INTO reviews (id, repo_path, branch, base_branch) VALUES (?, ?, ?, ?)",
            (review.id, review.repo_path, review.branch, review.base_branch),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM reviews WHERE id = ?", (review.id,)
        ).fetchone()
        conn.close()
        return _row_to_review(row)

    def get(self, review_id: str) -> Review | None:
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM reviews WHERE id = ?", (review_id,)
        ).fetchone()
        conn.close()
        return _row_to_review(row) if row else None

    def update_status(self, review_id: str, status: str) -> Review | None:
        conn = get_connection()
        conn.execute(
            "UPDATE reviews SET status = ?, updated_at = datetime('now') WHERE id = ?",
            (status, review_id),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM reviews WHERE id = ?", (review_id,)
        ).fetchone()
        conn.close()
        return _row_to_review(row) if row else None

    def search(self, repo_path=None, branch=None, limit=10) -> list[Review]:
        conn = get_connection()
        query = "SELECT * FROM reviews WHERE 1=1"
        params: list = []
        if repo_path:
            query += " AND repo_path LIKE ?"
            params.append(f"%{repo_path}%")
        if branch:
            query += " AND branch = ?"
            params.append(branch)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        conn.close()
        return [_row_to_review(r) for r in rows]

    def recent(self, limit=20) -> list[Review]:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM reviews ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
        return [_row_to_review(r) for r in rows]
