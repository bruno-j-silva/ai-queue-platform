import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect
from testcontainers.postgres import PostgresContainer


@pytest.fixture(scope="function")
def postgres_url():
    with PostgresContainer("postgres:16") as pg:
        url = pg.get_connection_url().replace("psycopg2", "psycopg")
        original = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = url
        try:
            yield url
        finally:
            if original is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = original


def test_migration_applies(postgres_url: str) -> None:
    """Migração sobe sem erros."""
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", postgres_url)
    command.upgrade(cfg, "head")

    engine = create_engine(postgres_url)
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    expected = {"tenants", "jobs", "outbox", "webhook_endpoints", "job_events"}
    assert expected.issubset(set(tables)), f"Tabelas ausentes: {expected - set(tables)}"
    engine.dispose()


def test_migration_reverts(postgres_url: str) -> None:
    """Migração desce sem erros."""
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", postgres_url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")

    engine = create_engine(postgres_url)
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    application_tables = set(tables) - {"alembic_version"}
    assert not application_tables, f"Tabelas residuais após downgrade: {tables}"
    engine.dispose()
