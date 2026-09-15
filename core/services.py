from core.models import VALID_REVIEW_STATUSES


def validate_review_status(status: str) -> str | None:
    if status not in VALID_REVIEW_STATUSES:
        return f"Invalid status: {status}. Must be one of {VALID_REVIEW_STATUSES}"
    return None
