import os

import pytest

# Provide a stub DATABASE_URL so that shared/db/session.py can be imported
# without a real Postgres instance in unit/contract tests.
# Integration tests that need a real DB must override this via environment or
# a test-specific fixture.
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://stub:stub@localhost/stub")
os.environ.setdefault("RABBITMQ_URL", "amqp://enfila:enfila@localhost:5672/")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault(
    "WEBHOOK_ENCRYPTION_KEY",
    "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=",
)
os.environ.setdefault("ADMIN_API_TOKEN", "test-admin-token")


def pytest_configure(config: pytest.Config) -> None:
    """Registra marcadores customizados."""
    config.addinivalue_line(
        "markers",
        "live_backend: testes que requerem Ollama/vLLM real (rodam apenas no slot noturno)",
    )
    config.addinivalue_line(
        "markers",
        "integration: testes de integração que requerem infraestrutura real (DB, containers)",
    )
