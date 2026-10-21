"""Add-on: structured JSON-lines log file (rotating), next to the normal stderr log.

Only metadata is ever logged -- never chunk or chapter text.
"""
from __future__ import annotations

import json
import logging
import logging.handlers
from datetime import datetime, timezone
from pathlib import Path

LOG_FILENAME = "book-archivar.log"
MAX_BYTES = 5_000_000
BACKUP_COUNT = 5

# Everything LogRecord always carries; anything else on the record was passed
# by the caller via logging's `extra=` and belongs in the JSON payload.
_STANDARD_ATTRS = frozenset(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__
) | {"message", "asctime", "taskName"}


class JsonLinesFormatter(logging.Formatter):
    """One JSON object per line, so the log is machine-readable.

    Callers are responsible for never passing book text into a log message.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD_ATTRS and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(log_dir: Path, level: int = logging.INFO) -> None:
    """Send structured JSON-lines logs to `log_dir/book-archivar.log` (rotating).

    Idempotent: calling it twice does not attach a second file handler to the
    same file.
    """
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / LOG_FILENAME

    root = logging.getLogger()
    root.setLevel(level)

    for existing in root.handlers:
        if isinstance(existing, logging.handlers.RotatingFileHandler) and Path(
            existing.baseFilename
        ) == log_path.resolve():
            return

    handler = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
    )
    handler.setLevel(level)
    handler.setFormatter(JsonLinesFormatter())
    root.addHandler(handler)
