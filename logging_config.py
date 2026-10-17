"""Private rotating log configuration for the wallet application."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


LOG_DIR = Path(__file__).resolve().parent / 'logs'
LOG_FILE = LOG_DIR / 'wallet.log'


def configure_logging():
    """Configure the wallet logger once and return it."""
    logger = logging.getLogger('wallet')
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if not any(isinstance(handler, RotatingFileHandler) for handler in logger.handlers):
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            LOG_FILE,
            maxBytes=1_000_000,
            backupCount=5,
            encoding='utf-8',
        )
        handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s %(name)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
        ))
        logger.addHandler(handler)

    return logger
