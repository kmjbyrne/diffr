from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app import deps
from core.models import AVAILABLE_EMOJIS, Reaction

router = APIRouter(prefix="/api/reactions")


@router.post("", response_class=HTMLResponse)
async def toggle_reaction(request: Request):
    templates = request.app.state.templates

    content_type = request.headers.get("content-type", "")
    if "json" in content_type:
        data = await request.json()
    else:
        form = await request.form()
        data = dict(form)

    reaction = Reaction(
        id="",
        target_type=data["target_type"],
        target_id=data["target_id"],
        review_id=data["review_id"],
        emoji=data["emoji"],
    )
    deps.reactions.toggle(reaction)
    counts = deps.reactions.counts_for_target(
        reaction.target_type, reaction.target_id, reaction.review_id
    )

    return templates.TemplateResponse(
        request,
        "partials/reaction_bar.html",
        {
            "target_type": reaction.target_type,
            "target_id": reaction.target_id,
            "review_id": reaction.review_id,
            "counts": counts,
            "emojis": AVAILABLE_EMOJIS,
        },
    )


@router.get("/{target_type}/{target_id}", response_class=HTMLResponse)
async def get_reactions(
    request: Request, target_type: str, target_id: str, review_id: str
):
    templates = request.app.state.templates
    counts = deps.reactions.counts_for_target(target_type, target_id, review_id)

    return templates.TemplateResponse(
        request,
        "partials/reaction_bar.html",
        {
            "target_type": target_type,
            "target_id": target_id,
            "review_id": review_id,
            "counts": counts,
            "emojis": AVAILABLE_EMOJIS,
        },
    )
