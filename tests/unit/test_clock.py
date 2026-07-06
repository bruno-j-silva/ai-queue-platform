from datetime import datetime, timezone, timedelta
import pytest
from shared.clock import FakeClock, SystemClock


def test_fake_clock_default_start() -> None:
    clock = FakeClock()
    assert clock.now().tzinfo is not None


def test_fake_clock_advance_seconds() -> None:
    clock = FakeClock()
    start = clock.now()
    clock.advance(60)
    assert (clock.now() - start).total_seconds() == 60


def test_fake_clock_monotonic_advances() -> None:
    clock = FakeClock()
    clock.advance(30)
    assert clock.monotonic() == 30.0


def test_fake_clock_advance_to() -> None:
    clock = FakeClock()
    target = datetime(2025, 6, 1, tzinfo=timezone.utc)
    clock.advance_to(target)
    assert clock.now() == target


def test_system_clock_returns_utc_now() -> None:
    clock = SystemClock()
    now = clock.now()
    assert now.tzinfo == timezone.utc
