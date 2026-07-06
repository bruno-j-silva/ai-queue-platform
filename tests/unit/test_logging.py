import logging

from shared.context import get_correlation_ids, set_correlation_ids
from shared.logging_config import get_logger


def test_get_logger_returns_logger() -> None:
    logger = get_logger("test")
    assert isinstance(logger, logging.Logger)
    assert logger.name == "test"


def test_correlation_ids_default_none() -> None:
    ids = get_correlation_ids()
    assert ids["job_id"] is None
    assert ids["tenant_id"] is None
    assert ids["delivery_id"] is None


def test_set_correlation_ids() -> None:
    set_correlation_ids(job_id="j_123", tenant_id="t_abc")
    ids = get_correlation_ids()
    assert ids["job_id"] == "j_123"
    assert ids["tenant_id"] == "t_abc"
