import asyncio
import subprocess

from ports.events import EventBus
from ports.repository import ReviewRepository


async def watch_refs(
    events: EventBus, reviews: ReviewRepository, interval: float = 2.0
):
    known_refs: dict[str, str] = {}

    while True:
        await asyncio.sleep(interval)
        try:
            active = reviews.active()
        except (OSError, RuntimeError):
            continue

        for review in active:
            try:
                result = await asyncio.to_thread(
                    subprocess.run,
                    ["git", "-C", review.repo_path, "rev-parse", review.branch],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                current_ref = result.stdout.strip()
                if not current_ref:
                    continue

                prev_ref = known_refs.get(review.id)
                known_refs[review.id] = current_ref

                if prev_ref and prev_ref != current_ref:
                    print(
                        f"[diffr] ref changed for review={review.id[:8]} "
                        f"{prev_ref[:8]}..{current_ref[:8]}"
                    )
                    await events.broadcast(review.id, "diff-updated", current_ref[:8])
            except (subprocess.TimeoutExpired, OSError):
                continue
