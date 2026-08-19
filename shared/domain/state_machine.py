"""Máquina de estados pura dos jobs.

Função pura sem efeito colateral, sem I/O, sem dependências de modelos
SQLAlchemy. Opera sobre JobStatus e JobEvent enums tipados.
"""

from __future__ import annotations

import enum
from collections.abc import Mapping
from types import MappingProxyType

from shared.models.job import JobStatus


class JobEvent(enum.StrEnum):
    START = "start"
    COMPLETE = "complete"
    FAIL = "fail"
    CANCEL = "cancel"
    EXPIRE = "expire"


# Grafo de transições: {status_atual: {evento: status_destino}}
_TRANSITIONS: Mapping[JobStatus, Mapping[JobEvent, JobStatus]] = MappingProxyType(
    {
        JobStatus.queued: MappingProxyType(
            {
                JobEvent.START: JobStatus.running,
                JobEvent.CANCEL: JobStatus.cancelled,
                JobEvent.EXPIRE: JobStatus.expired,
            }
        ),
        JobStatus.running: MappingProxyType(
            {
                JobEvent.COMPLETE: JobStatus.succeeded,
                JobEvent.FAIL: JobStatus.failed,
                JobEvent.CANCEL: JobStatus.cancelled,
            }
        ),
    }
)

_TERMINAL_STATUSES: frozenset[JobStatus] = frozenset(
    {
        JobStatus.succeeded,
        JobStatus.failed,
        JobStatus.cancelled,
        JobStatus.expired,
    }
)

_ALL_STATUSES: frozenset[JobStatus] = frozenset(_TRANSITIONS.keys()) | _TERMINAL_STATUSES


class InvalidTransitionError(Exception):
    """Levantada quando a transição de estado é inválida."""

    def __init__(self, from_status: str, event: str) -> None:
        self.from_status = from_status
        self.event = event
        super().__init__(
            f"Invalid transition: cannot apply event '{event}' to status '{from_status}'"
        )


def transition(current_status: JobStatus, event: JobEvent) -> JobStatus:
    """Retorna o novo status após aplicar *event* a *current_status*.

    Args:
        current_status: Status atual do job (JobStatus).
        event: Evento a aplicar (JobEvent).

    Returns:
        Novo status como JobStatus.

    Raises:
        InvalidTransitionError: Se a transição for inválida ou se
            *current_status* / *event* forem desconhecidos.
    """
    if current_status not in _ALL_STATUSES:
        raise InvalidTransitionError(current_status, event)

    if current_status in _TERMINAL_STATUSES:
        raise InvalidTransitionError(current_status, event)

    allowed_events = _TRANSITIONS.get(current_status, {})
    if event not in allowed_events:
        raise InvalidTransitionError(current_status, event)

    return allowed_events[event]
