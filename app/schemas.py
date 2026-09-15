from pydantic import BaseModel


class CreateReviewRequest(BaseModel):
    repo_path: str
    branch: str
    base_branch: str = "main"


class CreateCommentRequest(BaseModel):
    review_id: str
    file_path: str
    line_number: int
    side: str = "right"
    body: str
    author: str = "user"
