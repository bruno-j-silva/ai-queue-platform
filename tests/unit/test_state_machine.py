"""Testes da máquina de estados pura dos jobs (TDD — RED first)."""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from shared.domain.state_machine import (
    _TERMINAL_STATUSES,
    InvalidTransitionError,
    JobEvent,
    transition,
)
from shared.models.job import JobStatus

# ---------------------------------------------------------------------------
# Transições válidas
# ---------------------------------------------------------------------------

VALID_TRANSITIONS = [
    (JobStatus.queued, JobEvent.START, JobStatus.running),
    (JobStatus.queued, JobEvent.CANCEL, JobStatus.cancelled),
    (JobStatus.queued, JobEvent.EXPIRE, JobStatus.expired),
    (JobStatus.running, JobEvent.COMPLETE, JobStatus.succeeded),
    (JobStatus.running, JobEvent.FAIL, JobStatus.failed),
    (JobStatus.running, JobEvent.CANCEL, JobStatus.cancelled),
]


@pytest.mark.parametrize("current,event,expected", VALID_TRANSITIONS)
def test_valid_transition(current: JobStatus, event: JobEvent, expected: JobStatus) -> None:
    """Cada aresta do grafo de transições retorna o status correto."""
    assert transition(current, event) == expected


# ---------------------------------------------------------------------------
# Transições inválidas — evento errado para estado não-terminal
# ---------------------------------------------------------------------------

INVALID_NON_TERMINAL_TRANSITIONS = [
    # queued não aceita complete, fail
    (JobStatus.queued, JobEvent.COMPLETE),
    (JobStatus.queued, JobEvent.FAIL),
    # running não aceita start, expire
    (JobStatus.running, JobEvent.START),
    (JobStatus.running, JobEvent.EXPIRE),
]


@pytest.mark.parametrize("current,event", INVALID_NON_TERMINAL_TRANSITIONS)
def test_invalid_transition_non_terminal(current: JobStatus, event: JobEvent) -> None:
    """Eventos ilegais em estados não-terminais levantam InvalidTransitionError."""
    with pytest.raises(InvalidTransitionError):
        transition(current, event)


# ---------------------------------------------------------------------------
# Invariante I1 — estados terminais rejeitam todos os eventos (Hypothesis)
# ---------------------------------------------------------------------------


@given(
    status=st.sampled_from(list(_TERMINAL_STATUSES)),
    event=st.sampled_from(list(JobEvent)),
)
@settings(max_examples=200)
def test_terminal_states_reject_all_events(status: JobStatus, event: JobEvent) -> None:
    """I1: estados terminais rejeitam todos os eventos sem exceção."""
    with pytest.raises(InvalidTransitionError):
        transition(status, event)


# ---------------------------------------------------------------------------
# Mensagem de erro contém informação útil
# ---------------------------------------------------------------------------


def test_invalid_transition_error_message() -> None:
    """InvalidTransitionError deve expor from_status e event."""
    err = InvalidTransitionError("queued", "complete")
    assert "queued" in str(err)
    assert "complete" in str(err)


# ---------------------------------------------------------------------------
# Estado desconhecido levanta InvalidTransitionError
# ---------------------------------------------------------------------------


def test_unknown_status_raises() -> None:
    """Status desconhecido deve levantar InvalidTransitionError."""
    with pytest.raises(InvalidTransitionError):
        transition("unknown_status", JobEvent.START)  # type: ignore[arg-type]


def test_unknown_event_raises() -> None:
    """Evento desconhecido deve levantar InvalidTransitionError."""
    with pytest.raises(InvalidTransitionError):
        transition(JobStatus.queued, "unknown_event")  # type: ignore[arg-type]
