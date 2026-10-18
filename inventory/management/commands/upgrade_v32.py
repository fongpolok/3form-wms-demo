"""
One-time upgrade to v3.2.0 (safe to run again):
  1. copy legacy GreaterWMS stock (stocklist rows with on-hand stock) into the new ledger
  2. give every legacy bin a zone (Normal -> General, Inspection -> QA, ...)
  3. add current_step_code to Phase 1 batches in MongoDB
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from binset.models import ListModel as LegacyBin
from core import mongo
from inventory.models import BinZone, Movement, StockLot
from inventory.services import LEGACY_ZONE
from stock.models import StockListModel


class Command(BaseCommand):
    help = "Upgrade existing data for v3.2.0 (inventory ledger + batch step codes)"

    @transaction.atomic
    def handle(self, *args, **opts):
        zones = 0
        for b in LegacyBin.objects.filter(is_delete=False):
            _, created = BinZone.objects.get_or_create(tenant_openid=b.openid, bin_name=b.bin_name,
                                                       defaults={"zone": LEGACY_ZONE.get(b.bin_property, "GENERAL")})
            zones += created

        imported = 0
        for row in StockListModel.objects.filter(is_void=False, onhand_stock__gt=0):
            if Movement.objects.filter(tenant_openid=row.openid, kind=Movement.LEGACY, ref=f"legacy-{row.pk}").exists():
                continue
            bin_row = LegacyBin.objects.filter(openid=row.openid, bin_property="Normal", is_delete=False) \
                .order_by("bin_name").first()
            if bin_row is None:
                self.stdout.write(self.style.WARNING(f"No 'Normal' bin for company {row.openid[:8]}; skipped {row.goods_code}"))
                continue
            lot, _ = StockLot.objects.get_or_create(
                tenant_openid=row.openid, goods_code=row.goods_code, lot_number=row.lot_number or "",
                bin_name=bin_row.bin_name,
                defaults={"goods_desc": row.goods_desc, "expiry_date": row.expiry_date,
                          "received_at": row.create_time or timezone.now(), "source": "legacy"})
            lot.qty += row.onhand_stock
            lot.save()
            Movement.objects.create(ts=timezone.now(), tenant_openid=row.openid, kind=Movement.LEGACY,
                                    goods_code=row.goods_code, lot_number=row.lot_number or "", bin_to=bin_row.bin_name,
                                    qty=row.onhand_stock, ref=f"legacy-{row.pk}", actor="upgrade_v32",
                                    note="copied from legacy stocklist")
            imported += 1

        db = mongo.db()
        fixed = 0
        for b in db.batches.find({"current_step_code": {"$exists": False}}):
            wo = db.work_orders.find_one({"wo_id": b["wo_id"]})
            if not wo:
                continue
            idx = min(b["current_step_no"], len(wo["routing"])) - 1
            db.batches.update_one({"_id": b["_id"]}, {"$set": {"current_step_code": wo["routing"][idx]["code"]}})
            fixed += 1
        mongo.ensure_indexes()
        self.stdout.write(self.style.SUCCESS(
            f"v3.2.0 upgrade: {zones} bin zones set, {imported} legacy stock rows copied, {fixed} batches updated"))
