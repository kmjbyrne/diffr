import json

from core.models import Stack
from adapters.db.connection import get_connection
from ports.repository import StackRepository


def _row_to_stack(row) -> Stack:
    return Stack(
        id=row["id"],
        name=row["name"],
        repo_path=row["repo_path"],
        branches=json.loads(row["branches"]),
        sidecars=json.loads(row["sidecars"]) if row["sidecars"] else {},
        created_at=row["created_at"],
    )


class SqliteStackRepository(StackRepository):
    def create(self, stack: Stack) -> Stack:
        conn = get_connection()
        conn.execute(
            "INSERT INTO stacks (id, name, repo_path, branches, sidecars) VALUES (?, ?, ?, ?, ?)",
            (stack.id, stack.name, stack.repo_path, json.dumps(stack.branches), json.dumps(stack.sidecars)),
        )
        conn.commit()
        conn.close()
        return stack

    def get(self, stack_id: str) -> Stack | None:
        conn = get_connection()
        row = conn.execute("SELECT * FROM stacks WHERE id = ?", (stack_id,)).fetchone()
        conn.close()
        return _row_to_stack(row) if row else None

    def for_repo(self, repo_path: str) -> list[Stack]:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM stacks WHERE repo_path = ? ORDER BY created_at",
            (repo_path,),
        ).fetchall()
        conn.close()
        return [_row_to_stack(r) for r in rows]

    def update(self, stack_id: str, name: str | None = None, branches: list[str] | None = None, sidecars: dict[str, list[str]] | None = None) -> Stack | None:
        conn = get_connection()
        if name is not None:
            conn.execute("UPDATE stacks SET name = ? WHERE id = ?", (name, stack_id))
        if branches is not None:
            conn.execute("UPDATE stacks SET branches = ? WHERE id = ?", (json.dumps(branches), stack_id))
        if sidecars is not None:
            conn.execute("UPDATE stacks SET sidecars = ? WHERE id = ?", (json.dumps(sidecars), stack_id))
        conn.commit()
        row = conn.execute("SELECT * FROM stacks WHERE id = ?", (stack_id,)).fetchone()
        conn.close()
        return _row_to_stack(row) if row else None

    def delete(self, stack_id: str) -> None:
        conn = get_connection()
        conn.execute("DELETE FROM stacks WHERE id = ?", (stack_id,))
        conn.commit()
        conn.close()
