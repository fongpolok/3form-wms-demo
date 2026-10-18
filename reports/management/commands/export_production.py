"""
Nightly (or manual) Excel export for every company.

    python manage.py export_production                 # yesterday
    python manage.py export_production --from 2026-10-01 --to 2026-10-19
"""
import logging
from datetime import date, timedelta
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from accounts.models import Account
from core import config
from reports.excel import build_workbook

logger = logging.getLogger("app")


class Command(BaseCommand):
    help = "Write the production workbook to excel_export.output_dir"

    def add_arguments(self, parser):
        parser.add_argument("--from", dest="d_from")
        parser.add_argument("--to", dest="d_to")

    def handle(self, *args, **opts):
        yesterday = date.today() - timedelta(days=1)
        d_from = date.fromisoformat(opts["d_from"]) if opts["d_from"] else yesterday
        d_to = date.fromisoformat(opts["d_to"]) if opts["d_to"] else d_from
        out_dir = Path(settings.BASE_DIR) / config.get("excel_export.output_dir", "exports")
        out_dir.mkdir(parents=True, exist_ok=True)
        for tenant in Account.objects.order_by().values_list("tenant_openid", flat=True).distinct():
            wb, counts = build_workbook(tenant, d_from, d_to)
            path = out_dir / f"3form_production_{tenant[:8]}_{d_from}_{d_to}.xlsx"
            wb.save(path)
            logger.info("Nightly export written: %s %s", path, counts)
            self.stdout.write(f"Wrote {path} {counts}")
