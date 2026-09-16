import asyncio
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import app as _app_pkg
from adapters.db import init_db
from adapters.git import discover_repos, refresh_branch_graph
from adapters.git_watcher import watch_refs
from app import deps
from app.routes import comments, pages, reactions, reviews, stack
from config import load_config

APP_DIR = Path(_app_pkg.__file__).parent


async def _warm_branch_cache():
    config = load_config()
    repos = discover_repos(config.get("scan_paths", []), config.get("max_depth", 2))
    for repo in repos:
        try:
            await asyncio.to_thread(refresh_branch_graph, repo.path)
        except asyncio.CancelledError:
            return
        except Exception:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    watcher = asyncio.create_task(watch_refs(deps.events, deps.reviews))
    warmer = asyncio.create_task(_warm_branch_cache())
    yield
    warmer.cancel()
    watcher.cancel()
    for t in (warmer, watcher):
        try:
            await t
        except asyncio.CancelledError:
            pass


def create_app() -> FastAPI:
    app = FastAPI(title="diffr", lifespan=lifespan)

    app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")

    templates = Jinja2Templates(directory=APP_DIR / "templates")

    home = str(Path.home())

    def short_path(path: str) -> str:
        if path.startswith(home):
            path = "~" + path[len(home):]
        path = re.sub(r"/\.claude/worktrees/", "/.../", path)
        return path

    templates.env.filters["short_path"] = short_path
    app.state.templates = templates

    app.include_router(pages.router)
    app.include_router(reviews.router)
    app.include_router(comments.router)
    app.include_router(reactions.router)
    app.include_router(stack.router)

    return app


if __name__ == "__main__":
    import threading
    import time
    import urllib.request
    import webbrowser

    import uvicorn

    PORT = 8787

    def _open_when_ready():
        url = f"http://127.0.0.1:{PORT}"
        for _ in range(30):
            try:
                urllib.request.urlopen(url, timeout=1)
                break
            except (OSError, urllib.error.URLError):
                time.sleep(0.2)
        webbrowser.open(url)

    threading.Thread(target=_open_when_ready, daemon=True).start()

    app = create_app()
    uvicorn.run(app, host="127.0.0.1", port=PORT)
