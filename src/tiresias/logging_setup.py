"""Uniform logging setup used by scripts and the API server."""

from __future__ import annotations

import logging
import os

_CONFIGURED = False


def setup_logging(level: str | int | None = None) -> None:
    """Configure root logging once. Level from arg or ``TIRESIAS_LOG_LEVEL``."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    lvl = level or os.environ.get("TIRESIAS_LOG_LEVEL", "INFO")
    logging.basicConfig(
        level=lvl,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(name)
