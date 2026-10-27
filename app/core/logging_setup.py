"""Журнал программы: файл с ротацией в UTF-8. Только локально, без отправки куда-либо."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(log_dir: Path, level: int = logging.INFO) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "app.log"
    root = logging.getLogger()
    root.setLevel(level)
    for h in list(root.handlers):
        if getattr(h, "_ads", False):
            root.removeHandler(h)
            h.close()
    handler = RotatingFileHandler(log_file, maxBytes=2 * 1024 * 1024, backupCount=5, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
    handler._ads = True
    root.addHandler(handler)
    if sys.stderr is not None:
        console = logging.StreamHandler()
        console.setLevel(logging.WARNING)
        console._ads = True
        root.addHandler(console)
    return log_file
