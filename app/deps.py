from adapters.ai.claude import ClaudeAdapter
from adapters.ai.noop import NoOpAI
from adapters.db import (
    SqliteCommentRepository,
    SqliteReactionRepository,
    SqliteReviewRepository,
    SqliteStackRepository,
)
from adapters.sse import SSEEventBus
from config import load_config
from ports.ai import AIPort

reviews = SqliteReviewRepository()
comments = SqliteCommentRepository()
reactions = SqliteReactionRepository()
stacks = SqliteStackRepository()
events = SSEEventBus()

_AI_PROVIDERS: dict[str, type[AIPort]] = {
    "claude": ClaudeAdapter,
}


def get_ai() -> AIPort:
    config = load_config()
    provider = config.get("ai_provider", "claude")
    cls = _AI_PROVIDERS.get(provider)
    if cls is None:
        return NoOpAI()
    return cls()
