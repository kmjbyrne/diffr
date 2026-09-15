import uuid

from adapters.db.connection import get_connection
from core.models import Reaction
from ports.repository import ReactionRepository


class SqliteReactionRepository(ReactionRepository):
    def toggle(self, reaction: Reaction) -> None:
        conn = get_connection()
        existing = conn.execute(
            "SELECT id FROM reactions "
            "WHERE target_type = ? AND target_id = ? AND emoji = ? AND review_id = ?",
            (
                reaction.target_type,
                reaction.target_id,
                reaction.emoji,
                reaction.review_id,
            ),
        ).fetchone()
        if existing:
            conn.execute("DELETE FROM reactions WHERE id = ?", (existing["id"],))
        else:
            conn.execute(
                "INSERT INTO reactions (id, target_type, target_id, review_id, emoji) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    str(uuid.uuid4()),
                    reaction.target_type,
                    reaction.target_id,
                    reaction.review_id,
                    reaction.emoji,
                ),
            )
        conn.commit()
        conn.close()

    def counts_for_target(self, target_type, target_id, review_id) -> dict[str, int]:
        conn = get_connection()
        rows = conn.execute(
            "SELECT emoji, COUNT(*) as cnt FROM reactions "
            "WHERE target_type = ? AND target_id = ? AND review_id = ? GROUP BY emoji",
            (target_type, target_id, review_id),
        ).fetchall()
        conn.close()
        return {row["emoji"]: row["cnt"] for row in rows}

    def for_review(self, review_id: str) -> list[Reaction]:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM reactions WHERE review_id = ?", (review_id,)
        ).fetchall()
        conn.close()
        return [
            Reaction(
                id=r["id"],
                target_type=r["target_type"],
                target_id=r["target_id"],
                review_id=r["review_id"],
                emoji=r["emoji"],
                created_at=r["created_at"],
            )
            for r in rows
        ]
