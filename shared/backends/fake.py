"""FakeBackend — backend determinístico para testes (sem GPU, sem rede).

Todo teste do core usa FakeBackend; Ollama/vLLM reais só nos testes de contrato.
"""
import asyncio
from shared.backends.protocol import (
    CancelToken,
    InferenceBackend,
    InferenceRequest,
    InferenceResult,
)
from shared.clock import Clock, SystemClock


class BackendError(Exception):
    def __init__(self, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


class FakeBackend:
    """Backend configurável para testes."""

    def __init__(
        self,
        latency_seconds: float = 0.0,
        fail_on_attempts: list[int] | None = None,
        permanent_error: bool = False,
        response_text: str = "fake response",
        clock: Clock | None = None,
    ) -> None:
        self._latency = latency_seconds
        self._fail_on_attempts = fail_on_attempts or []
        self._permanent_error = permanent_error
        self._response_text = response_text
        self._clock = clock or SystemClock()
        self._calls: list[InferenceRequest] = []
        self._aborted: list[str] = []
        self._call_count = 0

    async def generate(
        self,
        request: InferenceRequest,
        cancel_token: CancelToken,
    ) -> InferenceResult:
        self._call_count += 1
        self._calls.append(request)

        if self._permanent_error:
            raise BackendError("permanent error", retryable=False)

        if self._call_count in self._fail_on_attempts:
            raise BackendError(f"transient error on attempt {self._call_count}", retryable=True)

        # Simula latência com checagem de cancelamento
        if self._latency > 0:
            step = min(0.01, self._latency)
            elapsed = 0.0
            while elapsed < self._latency:
                if cancel_token.is_cancelled():
                    raise asyncio.CancelledError(f"job {request.job_id} cancelled")
                await asyncio.sleep(step)
                elapsed += step

        if cancel_token.is_cancelled():
            raise asyncio.CancelledError(f"job {request.job_id} cancelled")

        return InferenceResult(
            output=[{"type": "text", "text": self._response_text}],
            usage={
                "input_tokens": 10,
                "output_tokens": 5,
                "duration_ms": int(self._latency * 1000),
                "backend": "fake",
            },
        )

    async def abort(self, job_id: str) -> None:
        self._aborted.append(job_id)

    async def health(self) -> bool:
        return not self._permanent_error

    @property
    def calls(self) -> list[InferenceRequest]:
        return list(self._calls)

    @property
    def aborted_jobs(self) -> list[str]:
        return list(self._aborted)

    @property
    def call_count(self) -> int:
        return self._call_count
