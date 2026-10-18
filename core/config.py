"""
Loads tunable settings from config/settings.yaml and industry presets from
config/industries/*.yaml.

Every module reads settings through `get(...)` so the YAML file stays the one
place to tune behaviour. Secrets come from environment variables (.env).
"""
import copy
import logging
import os
from functools import lru_cache
from pathlib import Path

import yaml

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
SETTINGS_FILE = Path(os.environ.get("THREEFORM_SETTINGS_FILE", CONFIG_DIR / "settings.yaml"))

logger = logging.getLogger("app")


@lru_cache(maxsize=1)
def _load_settings():
    with open(SETTINGS_FILE, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    logger.info("Loaded settings from %s", SETTINGS_FILE)
    return data


def get(path, default=None):
    """Read a dotted setting, e.g. get("network_alarm.timeout_seconds")."""
    node = _load_settings()
    for key in path.split("."):
        if not isinstance(node, dict) or key not in node:
            return default
        node = node[key]
    return copy.deepcopy(node)


def all_settings():
    return copy.deepcopy(_load_settings())


def list_industries():
    return sorted(p.stem for p in (CONFIG_DIR / "industries").glob("*.yaml"))


@lru_cache(maxsize=16)
def _load_industry(code):
    path = CONFIG_DIR / "industries" / f"{code}.yaml"
    if not path.exists():
        raise ValueError(f"Unknown industry preset '{code}'. Available: {list_industries()}")
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def industry(code=None):
    """Industry preset (steps, scrap reasons, sign-off rule). Defaults to site.industry."""
    return copy.deepcopy(_load_industry(code or get("site.industry", "general")))


def reload():
    """Drop cached YAML so the next read sees file changes (used by tests)."""
    _load_settings.cache_clear()
    _load_industry.cache_clear()
