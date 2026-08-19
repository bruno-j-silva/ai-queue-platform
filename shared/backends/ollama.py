"""OllamaBackend — InferenceBackend implementation for Ollama (ADR-003)."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import httpx

from shared.backends.fake import BackendError
from shared.backends.protocol import CancelToken, InferenceRequest, InferenceResult


class OllamaBackend:
    """Backend that routes inference requests to a local Ollama server.

    Args:
        base_url: Base URL of the Ollama server, e.g. "http://ollama:11434".
    """

    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")

    async def generate(
        self,
        request: InferenceRequest,
        cancel_token: CancelToken,
    ) -> InferenceResult:
        """POST /api/chat with stream=True and parse SSE chunks.

        Raises:
            asyncio.CancelledError: If cancel_token is cancelled during streaming.
            BackendError(retryable=False): On HTTP 4xx responses.
            BackendError(retryable=True): On HTTP 5xx or connection errors.
        """
        payload: dict[str, Any] = {
            "model": request.model_id,
            "messages": request.messages,
            "stream": True,
            **request.params,
        }

        start_ms = int(time.monotonic() * 1000)
        accumulated_text = ""
        input_tokens = 0
        output_tokens = 0
        total_duration_ns = 0

        try:
            async with httpx.AsyncClient(base_url=self._base_url) as client:
                async with client.stream(
                    "POST",
                    "/api/chat",
                    json=payload,
                    timeout=request.timeout_seconds,
                ) as response:
                    if response.status_code >= 500:
                        body = await response.aread()
                        raise BackendError(
                            f"Ollama server error {response.status_code}: {body.decode()}",
                            retryable=True,
                        )
                    if response.status_code >= 400:
                        body = await response.aread()
                        raise BackendError(
                            f"Ollama client error {response.status_code}: {body.decode()}",
                            retryable=False,
                        )

                    async for line in response.aiter_lines():
                        if cancel_token.is_cancelled():
                            raise asyncio.CancelledError(f"job {request.job_id} cancelled")

                        if not line.strip():
                            continue

                        chunk: dict[str, Any] = json.loads(line)

                        # Accumulate assistant message content
                        message = chunk.get("message", {})
                        content = message.get("content", "")
                        if content:
                            accumulated_text += content

                        # Final chunk contains usage stats
                        if chunk.get("done"):
                            input_tokens = chunk.get("prompt_eval_count", 0)
                            output_tokens = chunk.get("eval_count", 0)
                            total_duration_ns = chunk.get("total_duration", 0)

        except httpx.ConnectError as exc:
            raise BackendError(
                f"Cannot connect to Ollama at {self._base_url}: {exc}",
                retryable=True,
            ) from exc
        except httpx.TimeoutException as exc:
            raise BackendError(
                f"Timeout connecting to Ollama at {self._base_url}: {exc}",
                retryable=True,
            ) from exc

        end_ms = int(time.monotonic() * 1000)
        duration_ms = total_duration_ns // 1_000_000 if total_duration_ns else end_ms - start_ms

        return InferenceResult(
            output=[{"type": "text", "text": accumulated_text}],
            usage={
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "duration_ms": duration_ms,
                "backend": "ollama",
            },
        )

    async def abort(self, job_id: str) -> None:
        """Ollama does not support mid-inference abort; no-op."""

    async def health(self) -> bool:
        """Return True if GET /api/tags returns 200, False otherwise."""
        try:
            async with httpx.AsyncClient(base_url=self._base_url) as client:
                response = await client.get("/api/tags", timeout=5.0)
                return response.status_code == 200
        except httpx.HTTPError:
            return False
