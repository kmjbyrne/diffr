from abc import ABC, abstractmethod

from core.models import Comment, Reaction, Review


class ReviewRepository(ABC):
    @abstractmethod
    def create(self, review: Review) -> Review: ...

    @abstractmethod
    def get(self, review_id: str) -> Review | None: ...

    @abstractmethod
    def update_status(self, review_id: str, status: str) -> Review | None: ...

    @abstractmethod
    def search(
        self, repo_path: str | None = None, branch: str | None = None, limit: int = 10
    ) -> list[Review]: ...

    @abstractmethod
    def recent(self, limit: int = 20) -> list[Review]: ...


class CommentRepository(ABC):
    @abstractmethod
    def create(self, comment: Comment) -> Comment: ...

    @abstractmethod
    def get(self, comment_id: str) -> Comment | None: ...

    @abstractmethod
    def update(
        self, comment_id: str, body: str | None = None, resolved: bool | None = None
    ) -> Comment | None: ...

    @abstractmethod
    def delete(self, comment_id: str) -> None: ...

    @abstractmethod
    def for_review(self, review_id: str) -> list[Comment]: ...

    @abstractmethod
    def for_file(self, review_id: str, file_path: str) -> list[Comment]: ...

    @abstractmethod
    def unprocessed(self, review_id: str | None = None) -> list[dict]: ...

    @abstractmethod
    def pending_count(self, review_id: str | None = None) -> int: ...

    @abstractmethod
    def claude_replies_since(self, review_id: str, since: str) -> int: ...

    @abstractmethod
    def mark_processed(self, comment_ids: list[str]) -> None: ...

    @abstractmethod
    def mark_line_processed(
        self, review_id: str, file_path: str, line_number: int, side: str
    ) -> None: ...

    @abstractmethod
    def comment_counts_by_file(self, review_id: str) -> dict[str, dict]: ...


class ReactionRepository(ABC):
    @abstractmethod
    def toggle(self, reaction: Reaction) -> None: ...

    @abstractmethod
    def counts_for_target(
        self, target_type: str, target_id: str, review_id: str
    ) -> dict[str, int]: ...

    @abstractmethod
    def for_review(self, review_id: str) -> list[Reaction]: ...
