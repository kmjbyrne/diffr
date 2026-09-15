import asyncio

from ports.events import EventBus


class SSEEventBus(EventBus):
    def __init__(self):
        self._subscribers: dict[str, list[asyncio.Queue]] = {}

    async def broadcast(self, review_id: str, event: str, data: str) -> None:
        subs = self._subscribers.get(review_id, [])
        print(
            f"[diffr] SSE broadcast event={event} to {len(subs)} subscribers for review={review_id[:8]}"
        )
        for q in subs:
            await q.put({"event": event, "data": data})

    async def subscribe(self, review_id: str, disconnect_check=None):
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.setdefault(review_id, []).append(queue)
        print(
            f"[diffr] SSE client connected for review={review_id[:8]}, total={len(self._subscribers[review_id])}"
        )
        try:
            while True:
                if disconnect_check and await disconnect_check():
                    break
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=30)
                    yield msg
                except TimeoutError:
                    yield {"event": "ping", "data": ""}
        finally:
            self._subscribers[review_id].remove(queue)
