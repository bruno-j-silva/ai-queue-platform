"""Backend contract that runs in every CI build."""

import pytest

from shared.backends.fake import FakeBackend
from shared.backends.protocol import CancelToken, InferenceBackend, InferenceRequest


@pytest.mark.asyncio
async def test_fake_backend_satisfies_inference_contract() -> None:
    backend = FakeBackend(response_text="contract")
    assert isinstance(backend, InferenceBackend)

    result = await backend.generate(
        InferenceRequest(
            job_id="contract-job",
            model_id="fake",
            messages=[{"role": "user", "content": "hello"}],
            params={},
            timeout_seconds=5,
            attempt=1,
        ),
        CancelToken(),
    )

    assert result.output == [{"type": "text", "text": "contract"}]
    assert result.usage["backend"] == "fake"
