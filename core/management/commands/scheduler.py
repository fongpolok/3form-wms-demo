"""
Job scheduler for Docker deployments (replaces crontab). Reads scheduler.jobs from
settings.yaml and runs each Django command at its time. One job failing never
stops the others. Run as its own container:  python manage.py scheduler
"""
import logging
import time
import traceback
from datetime import datetime
from zoneinfo import ZoneInfo

from django.core.management import call_command
from django.core.management.base import BaseCommand

from core import config

logger = logging.getLogger("app")


def due(job, now, last):
    key = job["name"]
    if "every_minutes" in job:
        slot = (now.hour * 60 + now.minute) // int(job["every_minutes"])
        mark = (now.date(), slot)
    elif "hourly_at_minute" in job:
        if now.minute != int(job["hourly_at_minute"]):
            return False
        mark = (now.date(), now.hour)
    elif "daily_at" in job:
        if now.strftime("%H:%M") != job["daily_at"]:
            return False
        mark = now.date()
    else:
        return False
    if last.get(key) == mark:
        return False
    last[key] = mark
    return True


class Command(BaseCommand):
    help = "Run scheduled jobs (backup, exports, planner watch, agent, ERP sync)"

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="check once and exit (for tests)")

    def handle(self, *args, **opts):
        tz = ZoneInfo(config.get("site.timezone", "Asia/Hong_Kong"))
        jobs = config.get("scheduler.jobs", [])
        last = {}
        self.stdout.write(f"Scheduler started with {len(jobs)} job(s): {', '.join(j['name'] for j in jobs)}")
        while True:
            now = datetime.now(tz)
            for job in jobs:
                if due(job, now, last):
                    t0 = time.time()
                    try:
                        call_command(job["command"], *job.get("args", []))
                        logger.info("Scheduled job %s done in %.1fs", job["name"], time.time() - t0)
                    except Exception:  # noqa: BLE001 - one bad job must not stop the scheduler
                        logger.error("Scheduled job %s failed:\n%s", job["name"], traceback.format_exc())
            if opts["once"]:
                return
            time.sleep(20)
