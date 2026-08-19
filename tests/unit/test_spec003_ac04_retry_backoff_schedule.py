"""SPEC-003/AC-04: deterministic retry schedule with bounded jitter."""

import pytest

from shared.webhooks.delivery import retry_delay_seconds


@pytest.mark.parametrize(
    ("failed_attempt", "expected"),
    [(1, 60), (2, 300), (3, 1800), (4, 7200)],
)
def test_spec003_ac04_retry_backoff_schedule(failed_attempt: int, expected: int) -> None:
    assert retry_delay_seconds(failed_attempt, jitter_factor=1.0) == expected
    assert retry_delay_seconds(failed_attempt, jitter_factor=0.8) == expected * 0.8
    assert retry_delay_seconds(failed_attempt, jitter_factor=1.2) == expected * 1.2


def test_spec003_ac04_rejects_jitter_outside_twenty_percent() -> None:
    with pytest.raises(ValueError):
        retry_delay_seconds(1, jitter_factor=1.21)


def test_spec003_ac04_rejects_attempt_beyond_schedule() -> None:
    with pytest.raises(ValueError, match="no automatic retry"):
        retry_delay_seconds(5, jitter_factor=1.0)
