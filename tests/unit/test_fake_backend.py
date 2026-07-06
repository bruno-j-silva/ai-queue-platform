import asyncio
import pytest
from shared.backends.fake import FakeBackend, BackendError
from shared.backends.protocol import InferenceRequest, CancelToken


def make_request(job_id: str = "j_test") -> InferenceRequest:
    return InferenceRequest(
        job_id=job_id,
        model_id="test-model",
        messages=[{"role": "user", "content": "hello"}],
        params={},
        timeout_seconds=30,
    )


@pytest.mark.asyncio
async def test_fake_backend_returns_result() -> None:
    backend = FakeBackend(response_text="hello world")
    result = await backend.generate(make_request(), CancelToken())
    assert result.output[0]["text"] == "hello world"
    assert result.usage["backend"] == "fake"


@pytest.mark.asyncio
async def test_fake_backend_records_calls() -> None:
    backend = FakeBackend()
    req = make_request("j_1")
    await backend.generate(req, CancelToken())
    assert len(backend.calls) == 1
    assert backend.calls[0].job_id == "j_1"


@pytest.mark.asyncio
async def test_fake_backend_permanent_error() -> None:
    backend = FakeBackend(permanent_error=True)
    with pytest.raises(BackendError) as exc_info:
        await backend.generate(make_request(), CancelToken())
    assert not exc_info.value.retryable


@pytest.mark.asyncio
async def test_fake_backend_transient_error_on_attempt() -> None:
    backend = FakeBackend(fail_on_attempts=[1])
    with pytest.raises(BackendError) as exc_info:
        await backend.generate(make_request(), CancelToken())
    assert exc_info.value.retryable
    # segunda tentativa passa
    result = await backend.generate(make_request(), CancelToken())
    assert result.output[0]["type"] == "text"


@pytest.mark.asyncio
async def test_fake_backend_respects_cancel_token() -> None:
    backend = FakeBackend(latency_seconds=10.0)
    token = CancelToken()
    token.cancel()
    with pytest.raises(asyncio.CancelledError):
        await backend.generate(make_request(), token)


@pytest.mark.asyncio
async def test_fake_backend_abort_records_job_id() -> None:
    backend = FakeBackend()
    await backend.abort("j_abc")
    assert "j_abc" in backend.aborted_jobs


@pytest.mark.asyncio
async def test_fake_backend_health_true_by_default() -> None:
    backend = FakeBackend()
    assert await backend.health() is True


@pytest.mark.asyncio
async def test_fake_backend_health_false_on_permanent_error() -> None:
    backend = FakeBackend(permanent_error=True)
    assert await backend.health() is False
