import threading
import time
from datetime import UTC, datetime, timedelta
from typing import Protocol, runtime_checkable


@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime: ...
    def monotonic(self) -> float: ...


class SystemClock:
    """Relógio real — usado em produção."""

    def now(self) -> datetime:
        return datetime.now(UTC)

    def monotonic(self) -> float:
        return time.monotonic()


class FakeClock:
    """Relógio controlável para testes.

    Permite avançar o tempo sem sleeps reais, essencial para testar
    timeouts, backoff exponencial, TTL e anti-starvation.
    """

    def __init__(self, start: datetime | None = None) -> None:
        self._now = start or datetime(2024, 1, 1, tzinfo=UTC)
        self._monotonic: float = 0.0
        self._lock = threading.Lock()

    def now(self) -> datetime:
        with self._lock:
            return self._now

    def monotonic(self) -> float:
        with self._lock:
            return self._monotonic

    def advance(self, seconds: float) -> None:
        """Avança o relógio manualmente."""
        if seconds < 0:
            raise ValueError(f"advance() requer seconds >= 0, recebeu {seconds}")
        with self._lock:
            self._now = self._now + timedelta(seconds=seconds)
            self._monotonic += seconds

    def advance_to(self, dt: datetime) -> None:
        """Salta para um datetime específico."""
        with self._lock:
            delta = dt - self._now
            if delta.total_seconds() <= 0:
                raise ValueError(f"advance_to() requer dt > now(), recebeu {dt} <= {self._now}")
            self._now += delta
            self._monotonic += delta.total_seconds()
