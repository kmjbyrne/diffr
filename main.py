import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from adapters.db import init_db
from adapters.git_watcher import watch_refs
from app import deps
from app.routes import comments, pages, reactions, reviews

APP_DIR = Path(__file__).parent / "app"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    watcher = asyncio.create_task(watch_refs(deps.events, deps.reviews))
    yield
    watcher.cancel()


def create_app() -> FastAPI:
    app = FastAPI(title="diffr", lifespan=lifespan)

    app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")

    templates = Jinja2Templates(directory=APP_DIR / "templates")
    app.state.templates = templates

    app.include_router(pages.router)
    app.include_router(reviews.router)
    app.include_router(comments.router)
    app.include_router(reactions.router)

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
