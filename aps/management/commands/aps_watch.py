"""Run every few minutes (cron): re-plan when a machine has been stopped too long."""
from django.core.management.base import BaseCommand

from aps.triggers import check_long_stops


class Command(BaseCommand):
    help = "Draft a re-plan for machines stopped longer than aps.replan_on_stop_minutes"

    def handle(self, *args, **opts):
        plans = [p for p in check_long_stops() if p]
        self.stdout.write(f"{len(plans)} re-plan(s) drafted")
