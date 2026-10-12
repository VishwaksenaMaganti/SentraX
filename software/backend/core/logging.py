"""
SentraX Structured Logging Setup
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_FILE = Path(__file__).resolve().parents[3] / "data" / "logs" / "sentrax.log"


def setup_logging():
    handlers = [logging.StreamHandler(sys.stdout)]
    try:
        # A file copy survives the terminal, so a dropped Bluetooth link can be diagnosed later
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(RotatingFileHandler(LOG_FILE, maxBytes=2_000_000, backupCount=3, encoding="utf-8"))
    except OSError:
        pass
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] [%(name)s]: %(message)s",
        handlers=handlers
    )
    # Windows reports why a Bluetooth session closed only at debug level
    logging.getLogger("bleak.backends.winrt.client").setLevel(logging.DEBUG)
