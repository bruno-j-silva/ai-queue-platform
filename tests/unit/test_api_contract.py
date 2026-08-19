"""Regression tests for the published v1 jobs contract."""

import pytest
from pydantic import ValidationError

from api.routes.jobs import JobSubmitRequest


def test_spec001_ac01_accepts_documented_request_shape() -> None:
    request = JobSubmitRequest(
        model="llama3",
        input={"messages": [{"role": "user", "content": "hello"}]},
        timeout_seconds=30,
        metadata={"correlation_id": "test-1"},
    )

    assert request.model == "llama3"
    assert request.input.messages[0].role == "user"


def test_spec001_ac03_rejects_empty_messages() -> None:
    with pytest.raises(ValidationError):
        JobSubmitRequest(
            model="llama3",
            input={"messages": []},
            timeout_seconds=30,
        )
