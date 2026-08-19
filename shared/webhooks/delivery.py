"""Pure webhook payload and retry helpers."""

import json
from typing import Any

RETRY_DELAYS_SECONDS: tuple[int, ...] = (60, 300, 1800, 7200)
MAX_ATTEMPTS = 5


def retry_delay_seconds(failed_attempt: int, *, jitter_factor: float) -> float:
    if not 0.8 <= jitter_factor <= 1.2:
        raise ValueError("jitter_factor must be between 0.8 and 1.2")
    if not 1 <= failed_attempt <= len(RETRY_DELAYS_SECONDS):
        raise ValueError("failed_attempt has no automatic retry")
    return RETRY_DELAYS_SECONDS[failed_attempt - 1] * jitter_factor


def build_webhook_payload(
    delivery_id: str,
    event: str,
    attempt: int,
    job: dict[str, Any],
) -> dict[str, Any]:
    return {
        "event": event,
        "delivery_id": delivery_id,
        "attempt": attempt,
        "job": job,
    }


def canonical_json(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
