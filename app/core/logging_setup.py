from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
import sys
from pathlib import Path

from app.core.app_paths import AppPaths


LOG_FILE_NAME = "PipeERP.log"
MAX_LOG_BYTES = 2 * 1024 * 1024
BACKUP_LOG_COUNT = 5


def setup_logging() -> Path:
    log_path = AppPaths.logs_dir() / LOG_FILE_NAME
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    target = str(log_path.resolve())
    exists = any(
        isinstance(handler, RotatingFileHandler)
        and str(Path(handler.baseFilename).resolve()) == target
        for handler in root_logger.handlers
    )
    if not exists:
        handler = RotatingFileHandler(
            log_path,
            maxBytes=MAX_LOG_BYTES,
            backupCount=BACKUP_LOG_COUNT,
            encoding="utf-8",
        )
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        root_logger.addHandler(handler)

    logging.getLogger("pipeerp").info("PipeERP startup")
    return log_path


def install_exception_hook() -> None:
    previous_hook = sys.excepthook

    def handle_exception(exc_type, exc_value, exc_traceback) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            previous_hook(exc_type, exc_value, exc_traceback)
            return
        logging.getLogger("pipeerp").critical(
            "Unhandled exception",
            exc_info=(exc_type, exc_value, exc_traceback),
        )
        previous_hook(exc_type, exc_value, exc_traceback)

    sys.excepthook = handle_exception


__all__ = ["install_exception_hook", "setup_logging"]