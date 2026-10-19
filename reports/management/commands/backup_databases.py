"""Database backup from inside Docker (PostgreSQL pg_dump + MongoDB as gzipped BSON), kept backup.keep_days.
On the Mac the same job is deploy/backup/backup.sh. The app image includes postgresql-client-16."""
import os
import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core import config


def dump_mongo(folder):
    """Every collection as gzipped BSON (pure Python, no mongodump needed). Restore: manage.py restore_mongo."""
    import gzip

    import bson

    from core import mongo
    folder.mkdir(parents=True, exist_ok=True)
    total = 0
    db = mongo.db()
    for name in db.list_collection_names():
        with gzip.open(folder / f"{name}.bson.gz", "wb") as fh:
            for doc in db[name].find():
                fh.write(bson.encode(doc))
                total += 1
    return total


class Command(BaseCommand):
    help = "Back up PostgreSQL and MongoDB"

    def handle(self, *args, **opts):
        out = Path(settings.BASE_DIR) / config.get("backup.output_dir", "backups") / datetime.now().strftime("%Y%m%d-%H%M%S")
        out.mkdir(parents=True, exist_ok=True)
        env = {**os.environ, "PGPASSWORD": os.environ.get("POSTGRES_PASSWORD", "")}
        if not shutil.which("pg_dump"):
            raise CommandError("pg_dump is not installed in this container.")
        subprocess.run(["pg_dump", "-h", os.environ.get("POSTGRES_HOST", "postgres"), "-p", os.environ.get("POSTGRES_PORT", "5432"),
                        "-U", os.environ["POSTGRES_USER"], "-d", os.environ["POSTGRES_DB"], "-Fc",
                        "-f", str(out / "postgres.dump")], check=True, env=env)
        n = dump_mongo(out / "mongo")
        self.stdout.write(f"MongoDB: {n} documents")
        keep = int(config.get("backup.keep_days", 30))
        for old in out.parent.iterdir():
            if old.is_dir() and datetime.fromtimestamp(old.stat().st_mtime) < datetime.now() - timedelta(days=keep):
                shutil.rmtree(old)
        self.stdout.write(f"Backup written to {out}")
