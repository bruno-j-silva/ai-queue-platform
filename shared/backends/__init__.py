"""Registry de backends de inferência (ADR-003)."""

from __future__ import annotations

from typing import Any

from shared.backends.protocol import (
    CancelToken,
    InferenceBackend,
    InferenceRequest,
    InferenceResult,
)
from shared.models.model_catalog import ModelBackend

# ── String-keyed registry (legacy / test use) ─────────────────────────────────
_registry: dict[str, type[Any]] = {}


def register_backend(name: str, cls: type, override: bool = False) -> None:
    if name in _registry and not override:
        raise RuntimeError(f"Backend '{name}' já registrado. Use override=True para sobrescrever.")
    _registry[name] = cls


def get_backend_class(name: str) -> type[Any]:
    if name not in _registry:
        raise KeyError(f"Backend '{name}' não registrado. Disponíveis: {list(_registry)}")
    return _registry[name]


# ── Enum-keyed registry (production: model_id → backend class) ────────────────
_BACKEND_MAP: dict[ModelBackend, type[Any]] = {}


def register_model_backend(enum_value: ModelBackend, cls: type[Any]) -> None:
    """Map a ModelBackend enum value to a backend class."""
    _BACKEND_MAP[enum_value] = cls


def resolve_backend_class(backend_type: ModelBackend) -> type[Any]:
    """Return the backend class registered for *backend_type*.

    Raises:
        KeyError: If no class has been registered for this enum value.
    """
    if backend_type not in _BACKEND_MAP:
        raise KeyError(
            f"No backend class for {backend_type!r}. Register with register_model_backend()."
        )
    return _BACKEND_MAP[backend_type]


# ── Auto-registration ─────────────────────────────────────────────────────────
from shared.backends.ollama import OllamaBackend  # noqa: E402

register_model_backend(ModelBackend.ollama, OllamaBackend)


__all__ = [
    "CancelToken",
    "InferenceBackend",
    "InferenceRequest",
    "InferenceResult",
    "OllamaBackend",
    "get_backend_class",
    "register_backend",
    "register_model_backend",
    "resolve_backend_class",
]
