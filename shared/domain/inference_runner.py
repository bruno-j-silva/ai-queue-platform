"""Runs inference with timeout, cancellation, retry, and error classification."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from shared.backends.fake import BackendError
from shared.backends.protocol import (
    CancelToken,
    InferenceBackend,
    InferenceRequest,
    InferenceResult,
)
from shared.clock import Clock

logger = logging.getLogger(__name__)

RETRY_DELAYS: tuple[float, ...] = (1.0, 4.0, 16.0)
MAX_ATTEMPTS: int = 3


@dataclass
class RunnerResult:
    """Outcome of a single run_inference call."""

    succeeded: bool
    result: InferenceResult | None  # set on success
    error_code: str | None  # "timeout", "permanent", "transient_exhausted", "cancelled"
    error_message: str | None
    attempt: int  # final attempt number (1-indexed)


async def run_inference(
    backend: InferenceBackend,
    request: InferenceRequest,
    cancel_token: CancelToken,
    clock: Clock | None = None,
) -> RunnerResult:
    """Run inference with timeout, retry, and error classification.

    - Cancelled: if cancel_token.is_cancelled() before an attempt → error_code="cancelled"
    - Timeout: if request.timeout_seconds exceeded → abort + return error_code="timeout"
    - Transient error (retryable=True): retry up to MAX_ATTEMPTS with RETRY_DELAYS backoff
    - Permanent error (retryable=False): return immediately with error_code="permanent"
    - Success: return RunnerResult(succeeded=True, result=...)
    - After MAX_ATTEMPTS transient failures: error_code="transient_exhausted"
    """
    timeout: float | None = float(request.timeout_seconds) if request.timeout_seconds > 0 else None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        if cancel_token.is_cancelled():
            logger.info("job %s cancelled before attempt %d", request.job_id, attempt)
            return RunnerResult(
                succeeded=False,
                result=None,
                error_code="cancelled",
                error_message="Job was cancelled",
                attempt=attempt,
            )

        try:
            logger.debug("job %s attempt %d / %d", request.job_id, attempt, MAX_ATTEMPTS)
            inference_result = await asyncio.wait_for(
                backend.generate(request, cancel_token),
                timeout=timeout,
            )
        except TimeoutError:
            logger.warning("job %s timed out on attempt %d", request.job_id, attempt)
            await backend.abort(request.job_id)
            return RunnerResult(
                succeeded=False,
                result=None,
                error_code="timeout",
                error_message=f"Inference exceeded timeout of {request.timeout_seconds}s",
                attempt=attempt,
            )
        except BackendError as exc:
            if not exc.retryable:
                logger.error("job %s permanent error: %s", request.job_id, exc)
                return RunnerResult(
                    succeeded=False,
                    result=None,
                    error_code="permanent",
                    error_message=str(exc),
                    attempt=attempt,
                )

            # Transient error — retry with backoff if attempts remain
            logger.warning("job %s transient error on attempt %d: %s", request.job_id, attempt, exc)
            if attempt < MAX_ATTEMPTS:
                delay = RETRY_DELAYS[attempt - 1]
                logger.debug("job %s backing off for %.1fs", request.job_id, delay)
                await asyncio.sleep(delay)
            continue
        else:
            logger.info("job %s succeeded on attempt %d", request.job_id, attempt)
            return RunnerResult(
                succeeded=True,
                result=inference_result,
                error_code=None,
                error_message=None,
                attempt=attempt,
            )

    return RunnerResult(
        succeeded=False,
        result=None,
        error_code="transient_exhausted",
        error_message=f"Inference failed after {MAX_ATTEMPTS} transient attempts",
        attempt=MAX_ATTEMPTS,
    )
