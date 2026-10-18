"""Create MongoDB collections and indexes (safe to run again)."""
from django.core.management.base import BaseCommand, CommandError

from core import mongo


class Command(BaseCommand):
    help = "Create MongoDB collections and indexes for MES data"

    def handle(self, *args, **opts):
        if not mongo.ping():
            raise CommandError(f"Cannot reach MongoDB at {mongo.mongo_uri()}. Is the Docker container running?")
        mongo.ensure_indexes()
        self.stdout.write(self.style.SUCCESS(f"MongoDB ready: {', '.join(mongo.COLLECTIONS)}"))
