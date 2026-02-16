from __future__ import annotations

import logging
import os
import sys
from pathlib import Path


def setup_logging(log_file: str = "", log_level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger("tame")
    if logger.handlers:
        return logger
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.WARNING)
    stderr_handler.setFormatter(fmt)
    logger.addHandler(stderr_handler)

    if log_file:
        expanded = os.path.expanduser(log_file)
        Path(expanded).parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(expanded)
        file_handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)

    return logger
