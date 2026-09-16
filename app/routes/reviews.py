import uuid
from dataclasses import asdict

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from adapters.context.review_context import init_context
from adapters.git import get_diff_files, get_file_diff
from app import deps
from app.schemas import CreateReviewRequest
from core.models import Review

router = APIRouter(prefix="/api/reviews")


@router.post("/{review_id}/request-review")
async def request_ai_review(review_id: str):
    review = deps.reviews.get(review_id)
    if not review:
        return {"error": "not found"}

    files = get_diff_files(review.repo_path, review.base_branch, review.branch)
    ai = deps.get_ai()
    ai.review_code(
        review_id=review.id,
        repo_path=review.repo_path,
        branch=review.branch,
        base_branch=review.base_branch,
        files=files,
    )
    return {"ok": True}


@router.get("")
async def search_reviews(
    repo_path: str | None = None, branch: str | None = None, limit: int = 10
):
    reviews = deps.reviews.search(repo_path, branch, limit)
    return [asdict(r) for r in reviews]


@router.post("")
async def create_review(data: CreateReviewRequest):
    review = Review(
        id=str(uuid.uuid4()),
        repo_path=data.repo_path,
        branch=data.branch,
        base_branch=data.base_branch,
    )
    deps.reviews.create(review)

    files = get_diff_files(data.repo_path, data.base_branch, data.branch)
    init_context(review.id, data.repo_path, data.branch, data.base_branch, files)

    return {"id": review.id}


@router.get("/{review_id}")
async def get_review(review_id: str):
    review = deps.reviews.get(review_id)
    if not review:
        return {"error": "not found"}
    return asdict(review)


@router.patch("/{review_id}")
async def update_review(review_id: str, request: Request):
    content_type = request.headers.get("content-type", "")
    if "json" in content_type:
        data = await request.json()
    else:
        form = await request.form()
        data = dict(form)

    updated = deps.reviews.update_status(review_id, data["status"])
    if not updated:
        return {"error": "not found"}
    return asdict(updated)


@router.get("/{review_id}/files", response_class=HTMLResponse)
async def get_review_files(request: Request, review_id: str):
    templates = request.app.state.templates
    review = deps.reviews.get(review_id)
    if not review:
        return HTMLResponse("<p>Review not found</p>")

    files = get_diff_files(review.repo_path, review.base_branch, review.branch)
    comment_counts = deps.comments.comment_counts_by_file(review_id)

    return templates.TemplateResponse(
        request,
        "partials/file_list.html",
        {
            "review": asdict(review),
            "files": files,
            "comment_counts": comment_counts,
        },
    )


@router.get("/{review_id}/comments")
async def get_review_comments(review_id: str):
    review = deps.reviews.get(review_id)
    if not review:
        return {"error": "not found"}

    comments = deps.comments.for_review(review_id)
    return {
        "review": {
            "id": review.id,
            "repo_path": review.repo_path,
            "branch": review.branch,
            "base_branch": review.base_branch,
            "status": review.status,
        },
        "comments": [asdict(c) for c in comments],
    }


@router.get("/{review_id}/diff/{file_path:path}", response_class=HTMLResponse)
async def get_file_diff_view(request: Request, review_id: str, file_path: str):
    templates = request.app.state.templates
    review = deps.reviews.get(review_id)
    if not review:
        return HTMLResponse("<p>Review not found</p>")

    diff = get_file_diff(review.repo_path, review.base_branch, review.branch, file_path)

    file_comments = deps.comments.for_file(review_id, file_path)
    reactions = deps.reactions.for_review(review_id)

    comment_map: dict[str, list] = {}
    for c in file_comments:
        key = f"{c.side}:{c.line_number}"
        comment_map.setdefault(key, []).append(asdict(c))

    reaction_map: dict[str, dict[str, int]] = {}
    for r in reactions:
        reaction_map.setdefault(r.target_id, {})
        reaction_map[r.target_id][r.emoji] = (
            reaction_map[r.target_id].get(r.emoji, 0) + 1
        )

    return templates.TemplateResponse(
        request,
        "partials/diff_file.html",
        {
            "review": asdict(review),
            "diff": diff,
            "file_path": file_path,
            "comment_map": comment_map,
            "reaction_map": reaction_map,
        },
    )
