import json
import logging
import os
import sys
import time
from typing import Any, Dict, Optional


class StreamJsonFormatter(logging.Formatter):
    """
    12-Factor XI compliant formatter.
    Treats logs as unbuffered structured event streams to stdout.
    """

    def format(self, record: logging.LogRecord) -> str:
        log_obj: Dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt or "%Y-%m-%dT%H:%M:%SZ"),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }

        # Include custom extra fields if present
        if hasattr(record, "event"):
            log_obj["event"] = record.event
        if hasattr(record, "details"):
            log_obj["details"] = record.details

        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_obj)


def get_logger(name: str = "wiki_mcp") -> logging.Logger:
    """Configures and returns a logger adhering to 12-factor stdout logging."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        level_name = os.getenv("LOG_LEVEL", "INFO").upper()
        logger.setLevel(getattr(logging, level_name, logging.INFO))

        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(StreamJsonFormatter())
        logger.addHandler(handler)
        logger.propagate = False
    return logger


def log_event(logger: logging.Logger, level: int, event: str, message: str, **kwargs: Any) -> None:
    """Convenience helper to emit structured event logs."""
    record = logger.makeRecord(
        logger.name, level, "(unknown)", 0, message, (), None, None, {"event": event, "details": kwargs}
    )
    logger.handle(record)
