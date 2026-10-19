"""Pull ERP orders / push results / import Workday staff (cron: every 5 minutes; each connection
follows erp.poll_minutes and erp.workday_daily_hour).  --force runs everything now."""
from django.core.management.base import BaseCommand

from integrations.erp_sync import sync_all


class Command(BaseCommand):
    help = "ERP sync: orders in, results out, staff import"

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true")

    def handle(self, *args, **opts):
        for name, res in sync_all(force=opts["force"]):
            self.stdout.write(f"{name}: {res}")
