from abc import ABC, abstractmethod


class EventBus(ABC):
    @abstractmethod
    async def broadcast(self, review_id: str, event: str, data: str) -> None: ...

    @abstractmethod
    async def subscribe(self, review_id: str):
        """Return an async generator of SSE events for the given review."""
        ...
