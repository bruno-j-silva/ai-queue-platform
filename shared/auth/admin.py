"""Authentication for operator-only endpoints."""

import hmac
import os
from typing import Annotated

from fastapi import Header, HTTPException


async def require_admin_token(
    token: Annotated[str | None, Header(alias="X-Admin-Token")] = None,
) -> None:
    expected = os.environ.get("ADMIN_API_TOKEN")
    if expected is None or token is None or not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=401, detail="Invalid admin credential.")
