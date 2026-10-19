"""Phase 5: scheduler timing and MongoDB backup / restore round trip."""
from datetime import datetime

import pytest
from django.core.management import call_command

from core import mongo
from core.management.commands.scheduler import due
from reports.management.commands.backup_databases import dump_mongo


def test_scheduler_timing():
    last = {}
    t = datetime(2026, 11, 2, 2, 0)
    assert due({"name": "b", "daily_at": "02:00"}, t, last) is True
    assert due({"name": "b", "daily_at": "02:00"}, t, last) is False             # once per day
    assert due({"name": "h", "hourly_at_minute": 7}, t.replace(minute=7), last) is True
    assert due({"name": "h", "hourly_at_minute": 7}, t.replace(minute=8), last) is False
    assert due({"name": "e", "every_minutes": 5}, t.replace(minute=5), last) is True
    assert due({"name": "e", "every_minutes": 5}, t.replace(minute=6), last) is False
    assert due({"name": "e", "every_minutes": 5}, t.replace(minute=10), last) is True


@pytest.mark.django_db
def test_mongo_backup_and_restore(tmp_path):
    db = mongo.db()
    db.work_orders.insert_one({"wo_id": "WO-BACKUP-1", "qty": 5})
    n = dump_mongo(tmp_path / "mongo")
    assert n >= 1 and (tmp_path / "mongo" / "work_orders.bson.gz").exists()
    db.work_orders.delete_many({})
    call_command("restore_mongo", str(tmp_path), "--yes")
    assert db.work_orders.find_one({"wo_id": "WO-BACKUP-1"})["qty"] == 5
