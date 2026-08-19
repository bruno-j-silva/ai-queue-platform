import logging
import sys
import time

from pythonjsonlogger.json import JsonFormatter

from shared.context import get_correlation_ids


class CorrelationJsonFormatter(JsonFormatter):
    """Adiciona IDs de correlação a cada log record."""

    def add_fields(
        self,
        log_record: dict[str, object],
        record: logging.LogRecord,
        message_dict: dict[str, object],
    ) -> None:
        super().add_fields(log_record, record, message_dict)
        log_record.update(get_correlation_ids())


def setup_logging(service_name: str, level: str = "INFO") -> None:
    """Configura logging JSON estruturado para o serviço."""
    formatter = CorrelationJsonFormatter(
        fmt="%(asctime)s %(name)s %(levelname)s %(message)s",
        rename_fields={"asctime": "timestamp", "levelname": "level", "name": "logger"},
    )
    formatter.converter = time.gmtime  # UTC timestamps

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        root.addHandler(handler)
    root.setLevel(level)

    # Silenciar libs verbosas
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
