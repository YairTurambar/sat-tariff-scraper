"""Application logging configuration with redaction."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import re

REDACTION_PATTERNS = [
    re.compile(r"(?i)(cookie|set-cookie|session(?:id)?|token)\s*[:=]\s*[^;\s]+"),
]


class RedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            message = record.getMessage()
            for pattern in REDACTION_PATTERNS:
                message = pattern.sub(lambda match: match.group(0).split(match.group(1), 1)[0] + match.group(1) + "=[REDACTED]", message) if match := pattern.search(message) else message
            record.msg = message
            record.args = ()
        return True



def configure_logging(logs_dir: str | Path, level: str = "INFO") -> logging.Logger:
    logs_path = Path(logs_dir)
    logs_path.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("sat_tariff")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.handlers.clear()
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    console.addFilter(RedactionFilter())

    file_handler = RotatingFileHandler(logs_path / "sat_tariff.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.addFilter(RedactionFilter())

    logger.addHandler(console)
    logger.addHandler(file_handler)
    return logger
