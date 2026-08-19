"""AC-02: When inference exceeds timeout_seconds, abort + mark failed with error_code='timeout'."""

from __future__ import annotations

from shared.backends.fake import FakeBackend
from shared.backends.protocol import CancelToken, InferenceRequest
from shared.domain.inference_runner import run_inference


def _make_request(job_id: str = "job-timeout-1", timeout_seconds: int = 1) -> InferenceRequest:
    return InferenceRequest(
        job_id=job_id,
        model_id="test-model",
        messages=[],
        params={},
        timeout_seconds=timeout_seconds,
    )


async def test_timeout_returns_error_code_timeout() -> None:
    """AC-02: inference exceeding timeout_seconds → error_code='timeout'.

    Strategy: patch asyncio.sleep so the FakeBackend latency loop never actually
    suspends, but we still force a TimeoutError via asyncio.wait_for with a real
    coroutine that never returns.
    """
    import asyncio

    # Use a backend that blocks forever via an event, bypassing real sleep
    backend = FakeBackend(latency_seconds=0.0)

    async def _blocking(*args: object, **kwargs: object) -> object:  # type: ignore[override]
        await asyncio.Event().wait()  # never resolves

    backend.generate = _blocking  # type: ignore[method-assign]

    request = _make_request(job_id="job-t1", timeout_seconds=1)
    result = await run_inference(backend, request, CancelToken())

    assert not result.succeeded
    assert result.error_code == "timeout"


async def test_timeout_abort_called() -> None:
    """AC-02: abort() is called with the correct job_id on timeout."""
    import asyncio

    backend = FakeBackend(latency_seconds=0.0)
    aborted: list[str] = []

    async def _blocking(*args: object, **kwargs: object) -> object:  # type: ignore[override]
        await asyncio.Event().wait()

    async def _track_abort(job_id: str) -> None:
        aborted.append(job_id)

    backend.generate = _blocking  # type: ignore[method-assign]
    backend.abort = _track_abort  # type: ignore[method-assign]

    job_id = "job-t2"
    request = _make_request(job_id=job_id, timeout_seconds=1)
    result = await run_inference(backend, request, CancelToken())

    assert not result.succeeded
    assert result.error_code == "timeout"
    assert job_id in aborted


async def test_timeout_result_is_none() -> None:
    """AC-02: timed-out result carries no InferenceResult payload."""
    import asyncio

    backend = FakeBackend(latency_seconds=0.0)

    async def _blocking(*args: object, **kwargs: object) -> object:  # type: ignore[override]
        await asyncio.Event().wait()

    backend.generate = _blocking  # type: ignore[method-assign]

    request = _make_request(job_id="job-t3", timeout_seconds=1)
    result = await run_inference(backend, request, CancelToken())

    assert result.result is None
    assert result.error_message is not None


async def test_no_timeout_succeeds() -> None:
    """Sanity: backend with no latency and sufficient timeout → succeeded=True."""
    backend = FakeBackend(latency_seconds=0.0)
    request = _make_request(job_id="job-t4", timeout_seconds=5)

    result = await run_inference(backend, request, CancelToken())

    assert result.succeeded
    assert result.result is not None
    assert result.error_code is None
