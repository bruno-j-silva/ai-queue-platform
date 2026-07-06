import time
from datetime import datetime, timezone
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...
    def monotonic(self) -> float: ...


class SystemClock:
    """Relógio real — usado em produção."""

    def now(self) -> datetime:
        return datetime.now(timezone.utc)

    def monotonic(self) -> float:
        return time.monotonic()


class FakeClock:
    """Relógio controlável para testes.

    Permite avançar o tempo sem sleeps reais, essencial para testar
    timeouts, backoff exponencial, TTL e anti-starvation.
    """

    def __init__(self, start: datetime | None = None) -> None:
        self._now = start or datetime(2024, 1, 1, tzinfo=timezone.utc)
        self._monotonic: float = 0.0

    def now(self) -> datetime:
        return self._now

    def monotonic(self) -> float:
        return self._monotonic

    def advance(self, seconds: float) -> None:
        """Avança o relógio manualmente."""
        from datetime import timedelta
        self._now = self._now + timedelta(seconds=seconds)
        self._monotonic += seconds

    def advance_to(self, dt: datetime) -> None:
        """Salta para um datetime específico."""
        delta = (dt - self._now).total_seconds()
        if delta > 0:
            self.advance(delta)
