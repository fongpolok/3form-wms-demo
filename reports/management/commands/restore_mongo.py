"""Restore MongoDB from a backup folder written by backup_databases:
    python manage.py restore_mongo backups/20261020-020000 --yes
Each collection is replaced by the backup copy."""
import gzip
from pathlib import Path

import bson
from django.core.management.base import BaseCommand, CommandError

from core import mongo


class Command(BaseCommand):
    help = "Restore MongoDB collections from a backup folder"

    def add_arguments(self, parser):
        parser.add_argument("folder")
        parser.add_argument("--yes", action="store_true", help="confirm: existing collections are replaced")

    def handle(self, *args, **o):
        folder = Path(o["folder"]) / "mongo"
        if not folder.is_dir():
            raise CommandError(f"{folder} not found.")
        if not o["yes"]:
            raise CommandError("Add --yes to confirm: the current MongoDB collections will be replaced.")
        db = mongo.db()
        for f in sorted(folder.glob("*.bson.gz")):
            docs = list(bson.decode_file_iter(gzip.open(f, "rb")))
            name = f.name[:-len(".bson.gz")]
            db[name].delete_many({})
            if docs:
                db[name].insert_many(docs)
            self.stdout.write(f"{name}: {len(docs)}")
        mongo.ensure_indexes()
