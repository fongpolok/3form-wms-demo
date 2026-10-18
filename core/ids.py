"""
Unique, human-readable IDs, printed as barcodes:

    WO-20261019-0001             work order
    B-20261019-0001              batch
    WIP-B-20261019-0001-S03-001  WIP (batch, step 3, unit 1)

Sequences are kept in Mongo `counters` and incremented atomically, so two
workstations can never get the same number. Formats live in settings.yaml (ids.*).
"""
import logging
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from pymongo import ReturnDocument

from core import config, mongo

logger = logging.getLogger("app")


def _today():
    return datetime.now(ZoneInfo(config.get("site.timezone", "Asia/Hong_Kong"))).strftime("%Y%m%d")


def _next_seq(counter_key, database=None):
    database = database if database is not None else mongo.db()
    doc = database["counters"].find_one_and_update(
        {"_id": counter_key},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return doc["seq"]


def new_work_order_id(database=None):
    date = _today()
    seq = _next_seq(f"wo:{date}", database)
    value = config.get("ids.work_order", "WO-{date}-{seq:04d}").format(date=date, seq=seq)
    logger.info("New work order ID %s", value)
    return value


def new_batch_id(database=None):
    date = _today()
    seq = _next_seq(f"batch:{date}", database)
    value = config.get("ids.batch", "B-{date}-{seq:04d}").format(date=date, seq=seq)
    logger.info("New batch ID %s", value)
    return value


def new_wip_id(batch_id, step_no, database=None):
    seq = _next_seq(f"wip:{batch_id}:{step_no}", database)
    value = config.get("ids.wip", "WIP-{batch}-S{step:02d}-{seq:03d}").format(
        batch=batch_id, step=int(step_no), seq=seq)
    logger.info("New WIP ID %s", value)
    return value


def new_event_id():
    """Hidden random ID for one scan / button press (de-duplication key)."""
    return uuid.uuid4().hex
