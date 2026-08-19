from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass
class InferenceRequest:
    job_id: str
    model_id: str
    messages: list[dict[str, Any]]
    params: dict[str, Any]
    timeout_seconds: int
    attempt: int = 0


@dataclass
class InferenceResult:
    output: list[dict[str, Any]]
    usage: dict[str, Any]  # {input_tokens, output_tokens, duration_ms, backend}


class CancelToken:
    """Token compartilhado para cancelamento cooperativo (ADR-005)."""

    def __init__(self) -> None:
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def is_cancelled(self) -> bool:
        return self._cancelled


@runtime_checkable
class InferenceBackend(Protocol):
    """Interface plugável para backends de inferência (ADR-003).

    Implementações: OllamaBackend (M2), VLLMBackend (M6), FakeBackend (testes).
    """

    async def generate(
        self,
        request: InferenceRequest,
        cancel_token: CancelToken,
    ) -> InferenceResult: ...

    async def abort(self, job_id: str) -> None: ...

    async def health(self) -> bool: ...
