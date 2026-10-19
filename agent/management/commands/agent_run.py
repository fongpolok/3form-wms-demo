"""Run the agent's jobs.
    python manage.py agent_run                 # all jobs (cron: hourly)
    python manage.py agent_run --if-pending    # only if an alarm asked for it (cron: every 5 min)
    python manage.py agent_run --job progress
"""
from datetime import datetime, timedelta, timezone

from django.core.management.base import BaseCommand

from accounts.models import Account
from agent import jobs
from core import config, mongo


class Command(BaseCommand):
    help = "Run the advisory agent jobs"

    def add_arguments(self, parser):
        parser.add_argument("--if-pending", action="store_true")
        parser.add_argument("--job", choices=jobs.JOBS)

    def handle(self, *args, **opts):
        stale = timedelta(minutes=float(config.get("agent.stale_minutes_for_rerun", 55)))
        for t in Account.objects.order_by().values_list("tenant_openid", flat=True).distinct():
            state = mongo.db().agent_state.find_one({"_id": t}) or {}
            if opts["if_pending"] and not state.get("pending"):
                continue
            if not opts["if_pending"] and not opts["job"] and state.get("last_run") and \
                    datetime.now(timezone.utc) - state["last_run"].replace(tzinfo=timezone.utc) < stale:
                continue
            trigger = f"alarm: {state.get('pending_reason')}" if opts["if_pending"] else "schedule"
            res = [jobs.run_job(t, opts["job"], trigger)] if opts["job"] else jobs.run_all(t, trigger)
            self.stdout.write(f"{t[:8]}: {res}")
