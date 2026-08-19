"""HTTP contract tests for the Ollama backend without a live model."""

import httpx
import pytest
import respx

from shared.backends.fake import BackendError
from shared.backends.ollama import OllamaBackend
from shared.backends.protocol import CancelToken, InferenceRequest


def _request() -> InferenceRequest:
    return InferenceRequest(
        job_id="job-1",
        model_id="llama3",
        messages=[{"role": "user", "content": "hello"}],
        params={"temperature": 0.2},
        timeout_seconds=5,
        attempt=1,
    )


@pytest.mark.asyncio
@respx.mock
async def test_ollama_streams_text_and_usage() -> None:
    respx.post("http://ollama.test/api/chat").mock(
        return_value=httpx.Response(
            200,
            content=(
                b'{"message":{"content":"hello "},"done":false}\n'
                b'{"message":{"content":"world"},"done":true,'
                b'"prompt_eval_count":4,"eval_count":2,"total_duration":5000000}\n'
            ),
        )
    )

    result = await OllamaBackend("http://ollama.test").generate(_request(), CancelToken())

    assert result.output == [{"type": "text", "text": "hello world"}]
    assert result.usage == {
        "input_tokens": 4,
        "output_tokens": 2,
        "duration_ms": 5,
        "backend": "ollama",
    }


@pytest.mark.asyncio
@respx.mock
@pytest.mark.parametrize(
    ("status_code", "retryable"),
    [(400, False), (503, True)],
)
async def test_ollama_classifies_http_errors(status_code: int, retryable: bool) -> None:
    respx.post("http://ollama.test/api/chat").mock(
        return_value=httpx.Response(status_code, text="backend error")
    )

    with pytest.raises(BackendError) as raised:
        await OllamaBackend("http://ollama.test").generate(_request(), CancelToken())

    assert raised.value.retryable is retryable


@pytest.mark.asyncio
@respx.mock
async def test_ollama_health_reflects_http_status() -> None:
    route = respx.get("http://ollama.test/api/tags").mock(return_value=httpx.Response(200))
    backend = OllamaBackend("http://ollama.test")

    assert await backend.health() is True
    route.mock(return_value=httpx.Response(503))
    assert await backend.health() is False
