import pytest
from alembic import command
from alembic.config import Config
from testcontainers.postgres import PostgresContainer


@pytest.fixture(scope="module")
def postgres_url():
    with PostgresContainer("postgres:16") as pg:
        yield pg.get_connection_url().replace("psycopg2", "psycopg")


def test_migration_applies(postgres_url: str) -> None:
    """Migração sobe sem erros."""
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", postgres_url)
    command.upgrade(cfg, "head")


def test_migration_reverts(postgres_url: str) -> None:
    """Migração desce sem erros."""
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", postgres_url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
