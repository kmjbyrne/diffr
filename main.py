from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from adapters.db import init_db
from app.routes import comments, pages, reactions, reviews

APP_DIR = Path(__file__).parent / "app"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


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
