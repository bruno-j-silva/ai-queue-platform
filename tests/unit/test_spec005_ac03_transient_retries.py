"""AC-03: Transient error (retryable=True) → retry with backoff up to MAX_ATTEMPTS."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from shared.backends.fake import FakeBackend
from shared.backends.protocol import CancelToken, InferenceRequest
from shared.domain.inference_runner import MAX_ATTEMPTS, run_inference


def _make_request(job_id: str = "job-retry-1", timeout_seconds: int = 30) -> InferenceRequest:
    return InferenceRequest(
        job_id=job_id,
        model_id="test-model",
        messages=[],
        params={},
        timeout_seconds=timeout_seconds,
    )


async def test_transient_retries_up_to_max() -> None:
    """AC-03: 3 transient failures → error_code='transient_exhausted', attempt=MAX_ATTEMPTS."""
    backend = FakeBackend(fail_on_attempts=[1, 2, 3])

    with patch("asyncio.sleep", new_callable=AsyncMock):
        result = await run_inference(backend, _make_request(), CancelToken())

    assert not result.succeeded
    assert result.error_code == "transient_exhausted"
    assert result.attempt == MAX_ATTEMPTS
    assert backend.call_count == MAX_ATTEMPTS


async def test_transient_retries_uses_backoff_delays() -> None:
    """AC-03: backoff sleeps are called between retries with the correct delay values."""
    backend = FakeBackend(fail_on_attempts=[1, 2, 3])

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        await run_inference(backend, _make_request(), CancelToken())

    # Two sleeps expected: after attempt 1 and after attempt 2 (no sleep after final attempt)
    assert mock_sleep.call_count == MAX_ATTEMPTS - 1
    calls = [c.args[0] for c in mock_sleep.call_args_list]
    assert calls == [1.0, 4.0]


async def test_transient_then_success() -> None:
    """AC-03: 2 transient failures then success → succeeded=True, call_count=3."""
    backend = FakeBackend(fail_on_attempts=[1, 2])

    with patch("asyncio.sleep", new_callable=AsyncMock):
        result = await run_inference(backend, _make_request(), CancelToken())

    assert result.succeeded
    assert result.result is not None
    assert backend.call_count == 3


async def test_single_transient_then_success() -> None:
    """AC-03: 1 transient failure then success → succeeded=True on attempt 2."""
    backend = FakeBackend(fail_on_attempts=[1])

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        result = await run_inference(backend, _make_request(), CancelToken())

    assert result.succeeded
    assert result.attempt == 2
    assert backend.call_count == 2
    assert mock_sleep.call_count == 1
    assert mock_sleep.call_args.args[0] == 1.0


async def test_no_transient_errors_no_sleep() -> None:
    """AC-03: immediate success → no sleep called, call_count=1."""
    backend = FakeBackend()

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        result = await run_inference(backend, _make_request(), CancelToken())

    assert result.succeeded
    assert backend.call_count == 1
    mock_sleep.assert_not_called()
