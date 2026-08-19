"""AC-04: Permanent error (retryable=False) → failed immediately, no retry."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from shared.backends.fake import FakeBackend
from shared.backends.protocol import CancelToken, InferenceRequest
from shared.domain.inference_runner import run_inference


def _make_request(job_id: str = "job-perm-1", timeout_seconds: int = 30) -> InferenceRequest:
    return InferenceRequest(
        job_id=job_id,
        model_id="test-model",
        messages=[],
        params={},
        timeout_seconds=timeout_seconds,
    )


async def test_permanent_error_no_retry() -> None:
    """AC-04: permanent error → failed immediately, call_count=1."""
    backend = FakeBackend(permanent_error=True)

    result = await run_inference(backend, _make_request(), CancelToken())

    assert not result.succeeded
    assert result.error_code == "permanent"
    assert backend.call_count == 1


async def test_permanent_error_no_sleep() -> None:
    """AC-04: permanent error does not trigger any backoff sleep."""
    backend = FakeBackend(permanent_error=True)

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        result = await run_inference(backend, _make_request(), CancelToken())

    assert not result.succeeded
    assert result.error_code == "permanent"
    mock_sleep.assert_not_called()


async def test_permanent_error_result_is_none() -> None:
    """AC-04: permanent error carries no InferenceResult payload."""
    backend = FakeBackend(permanent_error=True)

    result = await run_inference(backend, _make_request(), CancelToken())

    assert result.result is None
    assert result.error_message is not None


async def test_permanent_error_attempt_is_one() -> None:
    """AC-04: permanent error fails on first attempt, attempt=1."""
    backend = FakeBackend(permanent_error=True)

    result = await run_inference(backend, _make_request(), CancelToken())

    assert result.attempt == 1


async def test_permanent_error_different_from_transient() -> None:
    """AC-04: a permanent error after transient errors still stops immediately."""
    # Backend raises permanent error on every call regardless of attempt number
    backend = FakeBackend(permanent_error=True)

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        result = await run_inference(backend, _make_request(), CancelToken())

    # Exactly one call — no retries attempted
    assert backend.call_count == 1
    assert result.error_code == "permanent"
    mock_sleep.assert_not_called()


async def test_cancelled_before_first_attempt() -> None:
    """Bonus: cancelled token before any attempt → error_code='cancelled', call_count=0."""
    backend = FakeBackend()
    token = CancelToken()
    token.cancel()

    result = await run_inference(backend, _make_request(), token)

    assert not result.succeeded
    assert result.error_code == "cancelled"
    assert backend.call_count == 0
