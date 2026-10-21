"""
Public website demo: wipe ALL data and re-create the demo factory (90 days of history).
Only runs when PUBLIC_DEMO=1, because it empties both databases.

    python manage.py public_demo_reset              # reset now
    python manage.py public_demo_reset --if-stale   # only if the last reset is older than public_demo.reset_every_hours
"""
import logging
import os
import secrets
import time
from datetime import datetime, timedelta, timezone

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from core import config, mongo, public_demo

logger = logging.getLogger("app")
STATE_ID = "public_demo"
KEEP = {"llm_usage"}      # the AI day counter survives a reset, so a reset never lifts the daily cap
LOCK_MINUTES = 30         # a reset still "running" after this is treated as crashed


class Command(BaseCommand):
    help = "Public demo only: wipe all data and re-create the demo factory"

    def add_arguments(self, parser):
        parser.add_argument("--if-stale", action="store_true")

    def handle(self, *args, **opts):
        if not public_demo.enabled():
            raise CommandError("Refused: this wipes every record. It only runs with PUBLIC_DEMO=1.")
        state = mongo.db().demo_state
        now = datetime.now(timezone.utc)
        doc = state.find_one({"_id": STATE_ID}) or {}
        if opts["if_stale"] and doc.get("done_at"):
            age = now - doc["done_at"].replace(tzinfo=timezone.utc)
            if age < timedelta(hours=float(config.get("public_demo.reset_every_hours", 24))):
                self.stdout.write(f"Demo data is fresh ({age}); nothing to do.")
                return
        # One reset at a time (start-up and the scheduler may both ask).
        got = state.find_one_and_update(
            {"_id": STATE_ID, "$or": [{"running_since": None},
                                      {"running_since": {"$lt": now - timedelta(minutes=LOCK_MINUTES)}}]},
            {"$set": {"running_since": now}})
        if got is None:
            if state.count_documents({"_id": STATE_ID}):
                self.stdout.write("Another reset is running; skipped.")
                return
            state.insert_one({"_id": STATE_ID, "running_since": now})
        t0 = time.time()
        try:
            self._reset()
        finally:
            state.update_one({"_id": STATE_ID}, {"$set": {"running_since": None}})
        state.update_one({"_id": STATE_ID}, {"$set": {"done_at": datetime.now(timezone.utc),
                                                      "took_seconds": round(time.time() - t0, 1)}})
        logger.info("Public demo reset done in %.1fs", time.time() - t0)
        self.stdout.write(self.style.SUCCESS(f"Public demo reset done in {time.time() - t0:.0f}s."))

    def _reset(self):
        from accounts import services as account_services
        from integrations.models import AiProvider
        from mes.workstations import list_workstations

        db = mongo.db()
        for name in list(mongo.COLLECTIONS) + ["search_docs"]:
            if name not in KEEP:
                db[name].delete_many({})
        call_command("flush", interactive=False, verbosity=0)
        call_command("load_holidays", verbosity=0)
        # Demo accounts get random passwords nobody knows: visitors use the one-click "Try it" buttons.
        os.environ["DEMO_PIC_PASSWORD"] = secrets.token_urlsafe(24)
        os.environ["DEMO_EM_PASSWORD"] = secrets.token_urlsafe(24)
        call_command("seed_demo", "--no-orders", verbosity=0)
        call_command("seed_history", "--days", str(int(config.get("public_demo.history_days", 90))), verbosity=0)
        tenant = account_services.demo_tenant()
        for ws in list_workstations():
            account_services.ensure_demo_device(tenant, ws["code"])
        AiProvider.objects.update_or_create(
            tenant_openid=tenant, defaults={"daily_call_cap": int(config.get("public_demo.ai_daily_calls", 30)),
                                            "updated_by": "public demo reset"})
        try:
            call_command("search_setup", verbosity=0)
        except Exception as exc:  # noqa: BLE001 - search is optional; the next reset tries again
            logger.warning("Public demo: search setup failed: %s", exc)
