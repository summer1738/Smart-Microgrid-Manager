"""Central logging setup for the backend."""

from __future__ import annotations

import logging
import sys


class _ColorFormatter(logging.Formatter):
    _RESET = "\x1b[0m"
    _COLORS = {
        "DEBUG": "\x1b[36m",  # cyan
        "INFO": "\x1b[32m",  # green
        "WARNING": "\x1b[33m",  # yellow
        "ERROR": "\x1b[31m",  # red
        "CRITICAL": "\x1b[35m",  # magenta
    }

    def __init__(self, *args, color: bool = True, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._color = bool(color)

    def format(self, record: logging.LogRecord) -> str:
        msg = super().format(record)
        if not self._color:
            return msg
        color = self._COLORS.get(record.levelname)
        if not color:
            return msg
        return f"{color}{msg}{self._RESET}"


def setup_logging(level: str = "INFO", color: bool = True) -> None:
    """
    Configure root logging once.
    Uvicorn has its own logging config, but this ensures our app loggers are consistent.
    """
    lvl = getattr(logging, str(level).upper(), logging.INFO)

    fmt = "%(asctime)s %(levelname)s %(name)s: %(message)s"
    datefmt = "%Y-%m-%dT%H:%M:%S%z"
    use_color = bool(color) and bool(getattr(sys.stderr, "isatty", lambda: False)())

    # Configure our application logger(s) even if uvicorn already configured root.
    app_logger = logging.getLogger("app")
    app_logger.setLevel(lvl)
    app_logger.propagate = False
    if not any(isinstance(h, logging.StreamHandler) for h in app_logger.handlers):
        h = logging.StreamHandler()
        h.setLevel(lvl)
        h.setFormatter(_ColorFormatter(fmt=fmt, datefmt=datefmt, color=use_color))
        app_logger.addHandler(h)

    # Reduce noisy third-party loggers a bit.
    for noisy in ("asyncio", "httpx", "sqlalchemy.engine"):
        logging.getLogger(noisy).setLevel(max(lvl, logging.WARNING))

