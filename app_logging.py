"""Application-wide logging configuration."""

from __future__ import annotations

import logging
import os
import sys
import threading
from datetime import datetime
from pathlib import Path


LOG_FILE_NAME = "log.txt"
LOG_FORMAT = (
    "%(asctime)s %(levelname)-8s "
    "[pid=%(process)d thread=%(threadName)s] %(name)s: %(message)s"
)

DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

def log_path() -> Path:
    return Path(__file__).resolve().parent / LOG_FILE_NAME


def configure_logging(level: int = logging.INFO) -> Path:
    """Configure append-only file logging for this process.

    The handler is deliberately a plain FileHandler in append mode. Rotation is
    left manual so existing log history is never removed by the application.
    """
    path = log_path()
    os.makedirs(path.parent, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(level)

    resolved_path = str(path.resolve())
    for handler in root.handlers:
        if isinstance(handler, logging.FileHandler):
            try:
                if os.path.abspath(handler.baseFilename) == resolved_path:
                    return path
            except AttributeError:
                continue

    handler = logging.FileHandler(path, mode="a", encoding="utf-8", delay=False)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    root.addHandler(handler)

    _install_exception_hooks()
    logging.getLogger(__name__).info("Logging initialized: %s", path)
    return path


def _install_exception_hooks() -> None:
    if getattr(_install_exception_hooks, "_installed", False):
        return

    original_excepthook = sys.excepthook

    def excepthook(exc_type, exc_value, exc_traceback):
        logging.getLogger(__name__).critical(
            "Unhandled exception",
            exc_info=(exc_type, exc_value, exc_traceback),
        )
        original_excepthook(exc_type, exc_value, exc_traceback)

    sys.excepthook = excepthook

    if hasattr(threading, "excepthook"):
        original_threading_excepthook = threading.excepthook

        def threading_excepthook(args):
            logging.getLogger(__name__).critical(
                "Unhandled thread exception in %s",
                args.thread.name if args.thread else "<unknown>",
                exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
            )
            original_threading_excepthook(args)

        threading.excepthook = threading_excepthook

    _install_exception_hooks._installed = True
