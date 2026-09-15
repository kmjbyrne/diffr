from abc import ABC, abstractmethod


class AIPort(ABC):
    @abstractmethod
    def notify(
        self,
        review_id: str,
        repo_path: str,
        branch: str,
        base_branch: str,
        file_path: str,
        line_number: int,
        side: str,
        body: str,
    ) -> None:
        """Notify the AI about a new comment so it can read context and reply."""
        ...
