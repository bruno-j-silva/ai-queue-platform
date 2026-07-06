"""Registry de backends de inferência (ADR-003)."""
from shared.backends.protocol import InferenceBackend, InferenceRequest, InferenceResult, CancelToken

_registry: dict[str, type] = {}


def register_backend(name: str, cls: type) -> None:
    _registry[name] = cls


def get_backend_class(name: str) -> type:
    if name not in _registry:
        raise KeyError(f"Backend '{name}' não registrado. Disponíveis: {list(_registry)}")
    return _registry[name]


__all__ = ["InferenceBackend", "InferenceRequest", "InferenceResult", "CancelToken",
           "register_backend", "get_backend_class"]
