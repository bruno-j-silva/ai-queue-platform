"""RFC 9457 Problem Details helpers."""

from __future__ import annotations

from fastapi.responses import JSONResponse

_PROBLEM_MEDIA_TYPE = "application/problem+json"


def problem_response(
    status: int,
    title: str,
    detail: str,
    **extra: object,
) -> JSONResponse:
    """Return a JSON response conforming to RFC 9457 (Problem Details).

    Args:
        status: HTTP status code.
        title: Short, human-readable summary of the problem type.
        detail: Human-readable explanation specific to this occurrence.
        **extra: Additional fields to include in the response body.

    Returns:
        A JSONResponse with media_type ``application/problem+json``.
    """
    return JSONResponse(
        status_code=status,
        content={"type": "about:blank", "title": title, "detail": detail, **extra},
        media_type=_PROBLEM_MEDIA_TYPE,
    )
