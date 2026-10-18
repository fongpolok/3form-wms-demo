"""
Builds Django's LOGGING dict: one daily-rotated file per channel
(app, scanner, camera, aps, agent, audit), kept for `logging.keep_days`.

Use it with `logging.getLogger("<channel>")`. The existing GreaterWMS loggers
(stock, asn, goods, django) are routed into app.log.
"""
import os
import sys
from pathlib import Path

from core import config

FORMAT = "[%(asctime)s][%(name)s.%(funcName)s():%(lineno)d] [%(levelname)s] %(message)s"
LEGACY_LOGGERS = ["django", "scripts", "stock", "asn", "goods", "dn", "accounts", "mes", "reports"]


def build_logging(base_dir):
    log_dir = Path(base_dir) / config.get("logging.dir", "logs")
    if "pytest" in sys.modules or os.environ.get("THREEFORM_TEST_LOGS"):
        log_dir = log_dir / "test"          # automated tests never write into the real logs
    log_dir.mkdir(parents=True, exist_ok=True)
    keep_days = int(config.get("logging.keep_days", 90))
    level = config.get("logging.level", "INFO")
    channels = config.get("logging.channels", ["app"])

    handlers = {
        "console": {"level": level, "class": "logging.StreamHandler", "formatter": "std"},
        "error": {
            "level": "ERROR",
            "class": "logging.handlers.TimedRotatingFileHandler",
            "filename": str(log_dir / "error.log"),
            "when": "midnight",
            "backupCount": keep_days,
            "formatter": "std",
            "encoding": "utf-8",
        },
    }
    for ch in channels:
        handlers[ch] = {
            "level": level,
            "class": "logging.handlers.TimedRotatingFileHandler",
            "filename": str(log_dir / f"{ch}.log"),
            "when": "midnight",
            "backupCount": keep_days,
            "formatter": "std",
            "encoding": "utf-8",
        }

    loggers = {ch: {"handlers": ["console", "error", ch], "level": level, "propagate": False} for ch in channels}
    for name in LEGACY_LOGGERS:
        loggers[name] = {"handlers": ["console", "error", "app"], "level": level, "propagate": False}
    loggers["django.db.backends"] = {"handlers": [], "level": "INFO", "propagate": True}

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {"std": {"format": FORMAT, "datefmt": "%Y-%m-%d %H:%M:%S"}},
        "handlers": handlers,
        "loggers": loggers,
    }
