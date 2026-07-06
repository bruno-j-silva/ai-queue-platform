import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Registra marcadores customizados."""
    config.addinivalue_line(
        "markers", "live_backend: testes que requerem Ollama/vLLM real (rodam apenas no slot noturno)"
    )
