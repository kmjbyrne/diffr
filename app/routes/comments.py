import uuid

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from sse_starlette.sse import EventSourceResponse

from adapters.context.review_context import append_comment
from app import deps
from app.schemas import CreateCommentRequest
from core.models import Comment

router = APIRouter(prefix="/api/comments")


@router.get("/stream")
async def comment_stream(request: Request, review_id: str):
    async def generator():
        async for msg in deps.events.subscribe(
            review_id, disconnect_check=request.is_disconnected
        ):
            yield msg

    return EventSourceResponse(generator())


@router.get("/pending-count")
async def pending_count(review_id: str | None = None):
    return {"count": deps.comments.pending_count(review_id)}


@router.get("/claude-replies")
async def claude_replies(review_id: str, since: str):
    return {"count": deps.comments.claude_replies_since(review_id, since)}


@router.get("/unprocessed")
async def get_unprocessed_comments():
    return deps.comments.unprocessed()


@router.post("/json")
async def create_comment_json(data: CreateCommentRequest):
    comment = Comment(
        id=str(uuid.uuid4()),
        review_id=data.review_id,
        file_path=data.file_path,
        line_number=data.line_number,
        side=data.side,
        body=data.body,
        author="claude",
        processed=True,
    )
    created = deps.comments.create(comment)
    deps.comments.mark_line_processed(
        data.review_id, data.file_path, data.line_number, data.side
    )

    append_comment(
        data.review_id, data.file_path, data.line_number, data.side, data.body, "claude"
    )
    await deps.events.broadcast(
        data.review_id, "claude-reply", f"{data.file_path}:{data.line_number}"
    )

    return _comment_dict(created)


@router.post("/mark-processed")
async def mark_processed(request: Request):
    data = await request.json()
    deps.comments.mark_processed(data.get("ids", []))
    return {"ok": True}


@router.post("", response_class=HTMLResponse)
async def create_comment(
    request: Request,
    review_id: str = Form(...),
    file_path: str = Form(...),
    line_number: int = Form(...),
    side: str = Form("right"),
    body: str = Form(...),
):
    templates = request.app.state.templates

    comment = Comment(
        id=str(uuid.uuid4()),
        review_id=review_id,
        file_path=file_path,
        line_number=line_number,
        side=side,
        body=body,
        author="user",
    )
    created = deps.comments.create(comment)
    review = deps.reviews.get(review_id)

    append_comment(review_id, file_path, line_number, side, body, "user")

    if review:
        ai = deps.get_ai()
        ai.notify(
            review_id=review_id,
            repo_path=review.repo_path,
            branch=review.branch,
            base_branch=review.base_branch,
            file_path=file_path,
            line_number=line_number,
            side=side,
            body=body,
        )

    return templates.TemplateResponse(
        request,
        "partials/comment.html",
        {
            "comment": _comment_dict(created),
        },
    )


@router.patch("/{comment_id}", response_class=HTMLResponse)
async def update_comment(request: Request, comment_id: str):
    templates = request.app.state.templates

    content_type = request.headers.get("content-type", "")
    if "json" in content_type:
        data = await request.json()
    else:
        form = await request.form()
        data = dict(form)

    body = data.get("body")
    resolved = data.get("resolved")
    if resolved is not None and isinstance(resolved, str):
        resolved = resolved.lower() == "true"

    updated = deps.comments.update(comment_id, body=body, resolved=resolved)
    if not updated:
        return HTMLResponse("<p>Comment not found</p>")

    return templates.TemplateResponse(
        request,
        "partials/comment.html",
        {
            "comment": _comment_dict(updated),
        },
    )


@router.delete("/{comment_id}", response_class=HTMLResponse)
async def delete_comment(comment_id: str):
    deps.comments.delete(comment_id)
    return HTMLResponse("")


@router.get("/form", response_class=HTMLResponse)
async def comment_form(
    request: Request,
    review_id: str,
    file_path: str,
    line_number: int,
    side: str = "right",
):
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "partials/comment_form.html",
        {
            "review_id": review_id,
            "file_path": file_path,
            "line_number": line_number,
            "side": side,
        },
    )


def _comment_dict(c: Comment) -> dict:
    return {
        "id": c.id,
        "review_id": c.review_id,
        "file_path": c.file_path,
        "line_number": c.line_number,
        "side": c.side,
        "body": c.body,
        "author": c.author,
        "resolved": int(c.resolved),
        "processed": int(c.processed),
        "created_at": c.created_at,
        "updated_at": c.updated_at,
    }
