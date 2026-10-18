"""
Inventory ledger (replaces the two legacy GreaterWMS stock tables for all
stock movements from v3.2.0 on).

    StockLot      what is where: item + lot + bin + expiry + quantity
    Movement      append-only log of every quantity change (traceability)
    Reservation   material held for a work order (so two orders can't share it)
    MaterialRequest  shortage raised when an order can't be fully reserved
    BinZone       zone for a legacy bin (raw material, finished goods, ...)
    Product / RecipeLine   shelf life, own step list, materials per piece
    CountTask     cycle count: system qty vs counted qty, PIC approves variance
    Shipment      goods leaving to a client (from stock or direct from QC)
    Alert         shortages, rack-camera mismatches, SPC alarms, ...
    SiteSetting   runtime overrides of settings.yaml (e.g. industry)
"""
from django.db import models


class BinZone(models.Model):
    RAW, FG, QA, HOLD, DAMAGE, GENERAL = "RAW", "FG", "QA", "HOLD", "DAMAGE", "GENERAL"
    ZONES = ((RAW, "Raw material"), (FG, "Finished goods"), (QA, "QA / inspection"), (HOLD, "Hold"),
             (DAMAGE, "Damage"), (GENERAL, "General"))
    tenant_openid = models.CharField(max_length=100, db_index=True)
    bin_name = models.CharField(max_length=64)
    zone = models.CharField(max_length=10, choices=ZONES, default=GENERAL)

    class Meta:
        db_table = "tf_bin_zone"
        unique_together = (("tenant_openid", "bin_name"),)


class StockLot(models.Model):
    tenant_openid = models.CharField(max_length=100, db_index=True)
    goods_code = models.CharField(max_length=64, db_index=True)
    goods_desc = models.CharField(max_length=255, blank=True, default="")
    lot_number = models.CharField(max_length=64, blank=True, default="")
    bin_name = models.CharField(max_length=64)
    expiry_date = models.DateField(null=True, blank=True)
    received_at = models.DateTimeField()
    qty = models.BigIntegerField(default=0)
    source = models.CharField(max_length=20, default="inbound")   # inbound | production | legacy | adjust
    batch_id = models.CharField(max_length=40, blank=True, default="")
    is_demo = models.BooleanField(default=False)

    class Meta:
        db_table = "tf_stock_lot"
        unique_together = (("tenant_openid", "goods_code", "lot_number", "bin_name"),)
        indexes = [models.Index(fields=["tenant_openid", "goods_code", "expiry_date"])]


class Movement(models.Model):
    RECEIVE, ISSUE, PUTAWAY, SHIP, ADJUST, MOVE, LEGACY = (
        "RECEIVE", "ISSUE_PRODUCTION", "PUTAWAY_FG", "SHIP", "ADJUST_COUNT", "MOVE", "LEGACY_IMPORT")
    ts = models.DateTimeField(db_index=True)
    tenant_openid = models.CharField(max_length=100, db_index=True)
    kind = models.CharField(max_length=20, db_index=True)
    goods_code = models.CharField(max_length=64, db_index=True)
    lot_number = models.CharField(max_length=64, blank=True, default="")
    bin_from = models.CharField(max_length=64, blank=True, default="")
    bin_to = models.CharField(max_length=64, blank=True, default="")
    qty = models.BigIntegerField()
    ref = models.CharField(max_length=80, blank=True, default="", db_index=True)   # WO / batch / shipment / count
    actor = models.CharField(max_length=80, blank=True, default="")
    note = models.CharField(max_length=255, blank=True, default="")
    is_demo = models.BooleanField(default=False)

    class Meta:
        db_table = "tf_movement"
        ordering = ["-ts"]

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise PermissionError("Movements are append-only.")
        super().save(*args, **kwargs)


class Reservation(models.Model):
    tenant_openid = models.CharField(max_length=100, db_index=True)
    wo_id = models.CharField(max_length=40, db_index=True)
    goods_code = models.CharField(max_length=64)
    qty_reserved = models.BigIntegerField(default=0)
    qty_consumed = models.BigIntegerField(default=0)
    is_demo = models.BooleanField(default=False)

    class Meta:
        db_table = "tf_reservation"
        unique_together = (("tenant_openid", "wo_id", "goods_code"),)

    @property
    def open_qty(self):
        return self.qty_reserved - self.qty_consumed


class MaterialRequest(models.Model):
    OPEN, CLOSED = "open", "closed"
    tenant_openid = models.CharField(max_length=100, db_index=True)
    wo_id = models.CharField(max_length=40, db_index=True)
    goods_code = models.CharField(max_length=64)
    goods_desc = models.CharField(max_length=255, blank=True, default="")
    qty_short = models.BigIntegerField()
    needed_by = models.CharField(max_length=10, blank=True, default="")
    status = models.CharField(max_length=10, default=OPEN, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "tf_material_request"
        ordering = ["status", "needed_by"]


class Product(models.Model):
    tenant_openid = models.CharField(max_length=100, db_index=True)
    goods_code = models.CharField(max_length=64)
    name = models.CharField(max_length=255)
    shelf_life_days = models.IntegerField(default=730)
    # Optional own step list: codes from the industry routing, in order. Empty = all industry steps.
    routing = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tf_product"
        unique_together = (("tenant_openid", "goods_code"),)
        ordering = ["goods_code"]


class RecipeLine(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="recipe")
    material_code = models.CharField(max_length=64)
    qty_per_piece = models.DecimalField(max_digits=12, decimal_places=4)

    class Meta:
        db_table = "tf_recipe_line"
        unique_together = (("product", "material_code"),)


class CountTask(models.Model):
    PENDING, APPROVED, REJECTED = "pending", "approved", "rejected"
    tenant_openid = models.CharField(max_length=100, db_index=True)
    bin_name = models.CharField(max_length=64)
    goods_code = models.CharField(max_length=64)
    lot_number = models.CharField(max_length=64, blank=True, default="")
    system_qty = models.BigIntegerField()
    counted_qty = models.BigIntegerField()
    counted_by = models.CharField(max_length=80)
    status = models.CharField(max_length=10, default=PENDING)
    decided_by = models.CharField(max_length=80, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "tf_count_task"
        ordering = ["-created_at"]


class Shipment(models.Model):
    tenant_openid = models.CharField(max_length=100, db_index=True)
    shipment_id = models.CharField(max_length=40, unique=True)
    client = models.CharField(max_length=255, blank=True, default="")
    source = models.CharField(max_length=10)   # stock | direct
    ref = models.CharField(max_length=80, blank=True, default="")   # WO / batch
    lines = models.JSONField(default=list)       # [{goods_code, lot_number, bin_name, qty}]
    shipped_at = models.DateTimeField()
    created_by = models.CharField(max_length=80)
    is_demo = models.BooleanField(default=False)

    class Meta:
        db_table = "tf_shipment"
        ordering = ["-shipped_at"]


class Alert(models.Model):
    SHORTAGE, RACK, SPC, VISION, LOW_STOCK, EXPIRY = ("MATERIAL_SHORTAGE", "RACK_MISMATCH", "SPC_OUT_OF_CONTROL",
                                                       "VISION_REJECT", "LOW_STOCK", "EXPIRY")
    tenant_openid = models.CharField(max_length=100, db_index=True)
    kind = models.CharField(max_length=24, db_index=True)
    severity = models.CharField(max_length=8, default="warn")   # info | warn | alarm
    title = models.CharField(max_length=200)
    detail = models.TextField(blank=True, default="")
    ref = models.CharField(max_length=80, blank=True, default="", db_index=True)
    dedupe_key = models.CharField(max_length=160, blank=True, default="", db_index=True)
    is_open = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    acknowledged_by = models.CharField(max_length=80, blank=True, default="")
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    is_demo = models.BooleanField(default=False)

    class Meta:
        db_table = "tf_alert"
        ordering = ["-created_at"]


class SiteSetting(models.Model):
    tenant_openid = models.CharField(max_length=100, db_index=True)
    key = models.CharField(max_length=64)
    value = models.JSONField()
    updated_by = models.CharField(max_length=80, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tf_site_setting"
        unique_together = (("tenant_openid", "key"),)
