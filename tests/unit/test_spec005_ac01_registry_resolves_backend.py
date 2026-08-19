"""AC-01: registry resolves model_id → backend without if/elif chains."""

from __future__ import annotations

import inspect

import pytest

from shared.backends import resolve_backend_class
from shared.backends.ollama import OllamaBackend
from shared.models.model_catalog import ModelBackend


def test_registry_resolves_ollama_backend() -> None:
    """AC-01: registry returns OllamaBackend for ModelBackend.ollama"""
    cls = resolve_backend_class(ModelBackend.ollama)
    assert cls is OllamaBackend


def test_registry_raises_for_unknown_backend() -> None:
    """AC-01: registry raises KeyError for unregistered enum value"""
    # ModelBackend.vllm is not registered yet — should raise KeyError
    with pytest.raises(KeyError):
        resolve_backend_class(ModelBackend.vllm)


def test_no_if_backend_chain_in_registry() -> None:
    """AC-01 structural: resolve_backend_class has no if/elif string comparisons on backend name"""
    source = inspect.getsource(resolve_backend_class)
    # The forbidden anti-patterns are string-equality checks on backend names
    assert '== "ollama"' not in source
    assert "== 'ollama'" not in source
    assert '== "vllm"' not in source
    assert "== 'vllm'" not in source
    # No elif chain that dispatches by name
    assert "elif backend" not in source


def test_ollama_backend_implements_protocol() -> None:
    """AC-01: OllamaBackend satisfies InferenceBackend protocol (isinstance check)"""
    from shared.backends.protocol import InferenceBackend

    backend = OllamaBackend(base_url="http://localhost:11434")
    assert isinstance(backend, InferenceBackend)


def test_register_backend_collision_raises() -> None:
    """Existing registry raises RuntimeError on duplicate without override=True"""
    from shared.backends import register_backend

    # First registration should succeed
    class _DummyBackend:
        async def generate(self, request: object, cancel_token: object) -> object: ...

        async def abort(self, job_id: str) -> None: ...

        async def health(self) -> bool:
            return True

    register_backend("_collision_test_backend", _DummyBackend)

    with pytest.raises(RuntimeError):
        register_backend("_collision_test_backend", _DummyBackend)
