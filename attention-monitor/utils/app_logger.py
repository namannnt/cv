"""
Centralized logging setup for the attention-monitor CV engine.
Uses Python's stdlib logging — no external dependency.

Why rotating file handler:
- CV sessions can run for hours. A single log file would grow unbounded.
- RotatingFileHandler caps each file at 1MB and keeps 3 backups.
- Total max log storage: 4MB.
"""
import logging
import os
from logging.handlers import RotatingFileHandler

LOG_DIR  = os.path.join(os.path.dirname(__file__), '..', 'data', 'logs')
LOG_FILE = os.path.join(LOG_DIR, 'attention_monitor.log')


def get_logger(name: str) -> logging.Logger:
    os.makedirs(LOG_DIR, exist_ok=True)

    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # already configured

    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # console handler — INFO and above
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)

    # file handler — DEBUG and above, rotating
    fh = RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=3)
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)

    logger.addHandler(ch)
    logger.addHandler(fh)
    return logger
