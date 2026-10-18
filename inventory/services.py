"""
Inventory ledger rules. Every quantity change goes through here and writes
one append-only Movement row, so any lot can be traced from receipt to
production to the client.

Stock-out rule per industry (config/industries/*.yaml `stock_rule`):
  fefo  earliest expiry first; lots without expiry follow, oldest first
  fifo  oldest received first
"""
import logging
import math
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from accounts import audit
from binset.models import ListModel as LegacyBin
from core import config, ids
from goods.models import ListModel as Goods

from .models import BinZone, CountTask, Movement, Product, Reservation, Shipment, StockLot

logger = logging.getLogger("app")
NOT_PICKABLE_ZONES = (BinZone.QA, BinZone.HOLD, BinZone.DAMAGE)
LEGACY_ZONE = {"Normal": BinZone.GENERAL, "Inspection": BinZone.QA, "Holding": BinZone.HOLD, "Damage": BinZone.DAMAGE}


class InventoryError(Exception):
    """Business-rule refusal, shown to the user as-is."""


def _actor(account):
    return getattr(account, "display_name", None) or str(account or "system")


def _move(tenant, kind, goods_code, qty, lot="", bin_from="", bin_to="", ref="", actor="", note="", ts=None,
          is_demo=False):
    return Movement.objects.create(ts=ts or timezone.now(), tenant_openid=tenant, kind=kind, goods_code=goods_code,
                                   lot_number=lot, bin_from=bin_from, bin_to=bin_to, qty=qty, ref=ref, actor=actor,
                                   note=note, is_demo=is_demo)


def goods_desc(tenant, code):
    g = Goods.objects.filter(openid=tenant, goods_code=code, is_delete=False).first()
    return g.goods_desc if g else ""


# ------------------------------------------------------------------- bins
def bin_exists(tenant, bin_name):
    return LegacyBin.objects.filter(openid=tenant, bin_name=bin_name, is_delete=False).exists()


def resolve_bin(tenant, scanned):
    """A scanned bin label may carry the bin name or its legacy bar code."""
    b = LegacyBin.objects.filter(openid=tenant, is_delete=False).filter(bin_name=scanned).first() or \
        LegacyBin.objects.filter(openid=tenant, is_delete=False, bar_code=scanned).first()
    return b.bin_name if b else None


def zone_of(tenant, bin_name):
    z = BinZone.objects.filter(tenant_openid=tenant, bin_name=bin_name).first()
    if z:
        return z.zone
    legacy = LegacyBin.objects.filter(openid=tenant, bin_name=bin_name, is_delete=False).first()
    return LEGACY_ZONE.get(legacy.bin_property if legacy else "", BinZone.GENERAL)


def list_bins(tenant):
    zones = dict(BinZone.objects.filter(tenant_openid=tenant).values_list("bin_name", "zone"))
    contents = defaultdict(list)
    for lot in StockLot.objects.filter(tenant_openid=tenant, qty__gt=0).order_by("goods_code"):
        contents[lot.bin_name].append({"goods_code": lot.goods_code, "lot_number": lot.lot_number, "qty": lot.qty,
                                       "expiry_date": lot.expiry_date})
    out = []
    for b in LegacyBin.objects.filter(openid=tenant, is_delete=False).order_by("bin_name"):
        out.append({"bin_name": b.bin_name, "bar_code": b.bar_code, "size": b.bin_size,
                    "zone": zones.get(b.bin_name) or LEGACY_ZONE.get(b.bin_property, BinZone.GENERAL),
                    "contents": contents.get(b.bin_name, [])})
    return out


@transaction.atomic
def create_bin(account, bin_name, zone, size="Floor", request=None):
    tenant = account.tenant_openid
    if zone not in dict(BinZone.ZONES):
        raise InventoryError("Unknown zone.")
    if bin_exists(tenant, bin_name):
        raise InventoryError(f"Bin {bin_name} already exists.")
    legacy_prop = {BinZone.QA: "Inspection", BinZone.HOLD: "Holding", BinZone.DAMAGE: "Damage"}.get(zone, "Normal")
    LegacyBin.objects.create(bin_name=bin_name, bin_size=size, bin_property=legacy_prop, empty_label=True,
                             creater=_actor(account), bar_code=bin_name, openid=tenant)
    BinZone.objects.update_or_create(tenant_openid=tenant, bin_name=bin_name, defaults={"zone": zone})
    audit.record(account, "bin.create", "bin", bin_name, after={"zone": zone, "size": size}, request=request)


@transaction.atomic
def set_zone(account, bin_name, zone, request=None):
    if zone not in dict(BinZone.ZONES):
        raise InventoryError("Unknown zone.")
    before = zone_of(account.tenant_openid, bin_name)
    BinZone.objects.update_or_create(tenant_openid=account.tenant_openid, bin_name=bin_name, defaults={"zone": zone})
    audit.record(account, "bin.zone", "bin", bin_name, before={"zone": before}, after={"zone": zone}, request=request)


def suggest_fg_bin(tenant):
    """First empty bin in the finished-goods zone (by name)."""
    fg_bins = list(BinZone.objects.filter(tenant_openid=tenant, zone=BinZone.FG).order_by("bin_name")
                   .values_list("bin_name", flat=True))
    occupied = set(StockLot.objects.filter(tenant_openid=tenant, bin_name__in=fg_bins, qty__gt=0)
                   .values_list("bin_name", flat=True))
    for name in fg_bins:
        if name not in occupied:
            return name
    return fg_bins[0] if fg_bins else None


# ------------------------------------------------------------ availability
def pickable_lots(tenant, goods_code, rule=None, lock=False):
    rule = rule or config.industry().get("stock_rule", "fifo")
    bad_bins = set(BinZone.objects.filter(tenant_openid=tenant, zone__in=NOT_PICKABLE_ZONES)
                   .values_list("bin_name", flat=True))
    qs = StockLot.objects.filter(tenant_openid=tenant, goods_code=goods_code, qty__gt=0).exclude(bin_name__in=bad_bins)
    if config.get("inventory.block_expired", True):
        qs = qs.exclude(expiry_date__lt=date.today())   # never pick expired material
    if lock:
        qs = qs.select_for_update()
    lots = list(qs)
    if rule == "fefo":
        lots.sort(key=lambda l: (l.expiry_date is None, l.expiry_date or date.max, l.received_at))
    else:
        lots.sort(key=lambda l: l.received_at)
    return lots


def on_hand(tenant, goods_code):
    return sum(l.qty for l in pickable_lots(tenant, goods_code))


def reserved(tenant, goods_code, exclude_wo=None):
    qs = Reservation.objects.filter(tenant_openid=tenant, goods_code=goods_code)
    if exclude_wo:
        qs = qs.exclude(wo_id=exclude_wo)
    return sum(r.open_qty for r in qs)


def available(tenant, goods_code):
    return on_hand(tenant, goods_code) - reserved(tenant, goods_code)


def stock_summary(tenant):
    """Per item: on hand, reserved, available, lots."""
    rows = {}
    for lot in StockLot.objects.filter(tenant_openid=tenant, qty__gt=0).order_by("goods_code", "expiry_date"):
        r = rows.setdefault(lot.goods_code, {"goods_code": lot.goods_code, "goods_desc": lot.goods_desc,
                                             "on_hand": 0, "lots": []})
        r["on_hand"] += lot.qty
        r["lots"].append({"lot_number": lot.lot_number, "bin_name": lot.bin_name, "qty": lot.qty,
                          "expiry_date": lot.expiry_date, "zone": zone_of(tenant, lot.bin_name),
                          "batch_id": lot.batch_id})
    for code, r in rows.items():
        r["reserved"] = reserved(tenant, code)
        r["available"] = available(tenant, code)
    return sorted(rows.values(), key=lambda r: r["goods_code"])


# ------------------------------------------------------------- movements
@transaction.atomic
def receive(account, goods_code, qty, bin_name, lot_number="", expiry_date=None, ref="", request=None):
    tenant = account.tenant_openid
    qty = int(qty)
    if qty <= 0:
        raise InventoryError("Quantity must be more than 0.")
    if not Goods.objects.filter(openid=tenant, goods_code=goods_code, is_delete=False).exists():
        raise InventoryError(f"Unknown item {goods_code}. Add it to the goods list first.")
    if not bin_exists(tenant, bin_name):
        raise InventoryError(f"Unknown bin {bin_name}.")
    lot, _ = StockLot.objects.select_for_update().get_or_create(
        tenant_openid=tenant, goods_code=goods_code, lot_number=lot_number or "", bin_name=bin_name,
        defaults={"goods_desc": goods_desc(tenant, goods_code), "expiry_date": expiry_date or None,
                  "received_at": timezone.now(), "source": "inbound"})
    if lot.expiry_date is None and expiry_date:
        lot.expiry_date = expiry_date
    lot.qty += qty
    lot.save()
    ref = ref or ids.new_event_id()[:12].upper()
    _move(tenant, Movement.RECEIVE, goods_code, qty, lot=lot.lot_number, bin_to=bin_name, ref=ref,
          actor=_actor(account))
    audit.record(account, "stock.receive", "stock", f"{goods_code}/{lot.lot_number}/{bin_name}",
                 after={"qty": qty, "expiry_date": str(expiry_date or "")}, request=request)
    logger.info("RECEIVE %s x%d lot=%r into %s by %s", goods_code, qty, lot.lot_number, bin_name, _actor(account))
    return lot


def issue(tenant, goods_code, qty, ref, actor, kind=Movement.ISSUE, ts=None, is_demo=False):
    """Take `qty` out by the stock rule. Caller must hold a transaction. Returns lots used."""
    remaining = int(qty)
    used = []
    for lot in pickable_lots(tenant, goods_code, lock=True):
        if remaining <= 0:
            break
        take = min(lot.qty, remaining)
        lot.qty -= take
        lot.save(update_fields=["qty"])
        _move(tenant, kind, goods_code, take, lot=lot.lot_number, bin_from=lot.bin_name, ref=ref, actor=actor, ts=ts,
              is_demo=is_demo)
        used.append({"goods_code": goods_code, "lot_number": lot.lot_number, "bin_name": lot.bin_name, "qty": take,
                     "expiry_date": lot.expiry_date.isoformat() if lot.expiry_date else None})
        remaining -= take
    if remaining > 0:
        raise InventoryError(f"Not enough {goods_code} in stock (short by {remaining}).")
    return used


@transaction.atomic
def put_away_finished(tenant, product_code, batch_id, qty, bin_name, actor, shelf_life_days=None, ts=None,
                      is_demo=False):
    if zone_of(tenant, bin_name) in NOT_PICKABLE_ZONES:
        raise InventoryError(f"Bin {bin_name} is a QA / hold / damage bin. Use a finished-goods bin.")
    if shelf_life_days is None:
        p = Product.objects.filter(tenant_openid=tenant, goods_code=product_code).first()
        shelf_life_days = p.shelf_life_days if p else None
    now = ts or timezone.now()
    expiry = (now.date() + timedelta(days=int(shelf_life_days))) if shelf_life_days else None
    lot, _ = StockLot.objects.select_for_update().get_or_create(
        tenant_openid=tenant, goods_code=product_code, lot_number=batch_id, bin_name=bin_name,
        defaults={"goods_desc": goods_desc(tenant, product_code), "expiry_date": expiry, "received_at": now,
                  "source": "production", "batch_id": batch_id, "is_demo": is_demo})
    lot.qty += int(qty)
    lot.save()
    _move(tenant, Movement.PUTAWAY, product_code, int(qty), lot=batch_id, bin_to=bin_name, ref=batch_id, actor=actor,
          ts=ts, is_demo=is_demo)
    logger.info("PUTAWAY %s batch %s x%s -> %s (expiry %s)", product_code, batch_id, qty, bin_name, expiry)
    return lot


def _shipment_id():
    return f"SH-{date.today():%Y%m%d}-{ids.new_event_id()[:6].upper()}"


@transaction.atomic
def ship_from_stock(account, client, lines, request=None):
    """lines: [{goods_code, qty}]. Picks by the stock rule; never takes reserved material."""
    tenant = account.tenant_openid
    sid = _shipment_id()
    picked = []
    for line in lines:
        code, qty = line["goods_code"], int(line["qty"])
        if qty <= 0:
            raise InventoryError("Quantities must be more than 0.")
        if available(tenant, code) < qty:
            raise InventoryError(f"Only {available(tenant, code)} of {code} available (rest is reserved or missing).")
        picked += issue(tenant, code, qty, sid, _actor(account), kind=Movement.SHIP)
    ship = Shipment.objects.create(tenant_openid=tenant, shipment_id=sid, client=client, source="stock",
                                   lines=picked, shipped_at=timezone.now(), created_by=_actor(account))
    audit.record(account, "stock.ship", "shipment", sid, after={"client": client, "lines": picked}, request=request)
    return ship


def ship_direct(tenant, client, batch_id, product_code, qty, actor, ts=None, is_demo=False):
    sid = _shipment_id()
    line = [{"goods_code": product_code, "lot_number": batch_id, "bin_name": "", "qty": int(qty)}]
    ship = Shipment.objects.create(tenant_openid=tenant, shipment_id=sid, client=client, source="direct",
                                   ref=batch_id, lines=line, shipped_at=ts or timezone.now(), created_by=actor,
                                   is_demo=is_demo)
    _move(tenant, Movement.SHIP, product_code, int(qty), lot=batch_id, ref=sid, actor=actor, note="direct from QC",
          ts=ts, is_demo=is_demo)
    return ship


# ------------------------------------------------------------- cycle count
@transaction.atomic
def submit_count(account, bin_name, goods_code, lot_number, counted_qty):
    tenant = account.tenant_openid
    lot = StockLot.objects.filter(tenant_openid=tenant, bin_name=bin_name, goods_code=goods_code,
                                  lot_number=lot_number or "").first()
    system_qty = lot.qty if lot else 0
    task = CountTask.objects.create(tenant_openid=tenant, bin_name=bin_name, goods_code=goods_code,
                                    lot_number=lot_number or "", system_qty=system_qty, counted_qty=int(counted_qty),
                                    counted_by=_actor(account))
    if system_qty == int(counted_qty):
        task.status, task.decided_by, task.decided_at = CountTask.APPROVED, "auto (no variance)", timezone.now()
        task.save()
    return task


@transaction.atomic
def decide_count(account, task_id, approve, request=None):
    """PIC approves (stock is corrected) or rejects (recount needed) a variance."""
    task = CountTask.objects.select_for_update().filter(pk=task_id, tenant_openid=account.tenant_openid).first()
    if task is None or task.status != CountTask.PENDING:
        raise InventoryError("Count task not found or already decided.")
    task.status = CountTask.APPROVED if approve else CountTask.REJECTED
    task.decided_by, task.decided_at = _actor(account), timezone.now()
    task.save()
    if approve:
        delta = task.counted_qty - task.system_qty
        lot, _ = StockLot.objects.select_for_update().get_or_create(
            tenant_openid=task.tenant_openid, goods_code=task.goods_code, lot_number=task.lot_number,
            bin_name=task.bin_name, defaults={"goods_desc": goods_desc(task.tenant_openid, task.goods_code),
                                              "received_at": timezone.now(), "source": "adjust"})
        lot.qty = task.counted_qty
        lot.save()
        _move(task.tenant_openid, Movement.ADJUST, task.goods_code, delta, lot=task.lot_number,
              bin_to=task.bin_name if delta > 0 else "", bin_from=task.bin_name if delta < 0 else "",
              ref=f"COUNT-{task.pk}", actor=_actor(account))
    audit.record(account, "count.approve" if approve else "count.reject", "count", task.pk,
                 before={"system_qty": task.system_qty}, after={"counted_qty": task.counted_qty}, request=request)
    return task


# ------------------------------------------------------------ products
def requirements(tenant, product_code, qty):
    """Materials needed for `qty` pieces: {material_code: whole units, rounded up}."""
    p = Product.objects.filter(tenant_openid=tenant, goods_code=product_code).prefetch_related("recipe").first()
    if p is None:
        return {}
    return {line.material_code: math.ceil(Decimal(qty) * line.qty_per_piece) for line in p.recipe.all()}


def product_payload(p):
    return {"id": p.pk, "goods_code": p.goods_code, "name": p.name, "shelf_life_days": p.shelf_life_days,
            "routing": p.routing, "is_active": p.is_active,
            "recipe": [{"material_code": r.material_code, "qty_per_piece": float(r.qty_per_piece)}
                       for r in p.recipe.all()]}


@transaction.atomic
def save_product(account, data, request=None):
    """Create or update a product + recipe (PIC or EM). Audited."""
    tenant = account.tenant_openid
    code = (data.get("goods_code") or "").strip()
    if not Goods.objects.filter(openid=tenant, goods_code=code, is_delete=False).exists():
        raise InventoryError(f"{code} is not in the goods list.")
    step_codes = [s["code"] for s in config.industry()["steps"]]
    routing = [c for c in (data.get("routing") or []) if c]
    bad = [c for c in routing if c not in step_codes]
    if bad:
        raise InventoryError(f"Unknown step(s) for this industry: {', '.join(bad)}")
    if routing and not config.industry()["steps"][-1]["code"] in routing:
        raise InventoryError("The QC step must stay in the step list.")
    lines = data.get("recipe") or []
    for line in lines:
        if not Goods.objects.filter(openid=tenant, goods_code=line.get("material_code"), is_delete=False).exists():
            raise InventoryError(f"Material {line.get('material_code')} is not in the goods list.")
        if Decimal(str(line.get("qty_per_piece", 0))) <= 0:
            raise InventoryError("Amount per piece must be more than 0.")
    existing = Product.objects.filter(tenant_openid=tenant, goods_code=code).first()
    before = product_payload(existing) if existing else None
    p, _ = Product.objects.update_or_create(
        tenant_openid=tenant, goods_code=code,
        defaults={"name": data.get("name") or goods_desc(tenant, code),
                  "shelf_life_days": int(data.get("shelf_life_days") or 730),
                  "routing": [c for c in step_codes if c in routing] if routing else [],
                  "is_active": bool(data.get("is_active", True))})
    p.recipe.all().delete()
    for line in lines:
        p.recipe.create(material_code=line["material_code"], qty_per_piece=Decimal(str(line["qty_per_piece"])))
    after = product_payload(p)
    audit.record(account, "product.update" if before else "product.create", "product", code, before=before,
                 after=after, request=request)
    return after


def movements(tenant, ref=None, goods_code=None, limit=300):
    qs = Movement.objects.filter(tenant_openid=tenant)
    if ref:
        qs = qs.filter(ref=ref)
    if goods_code:
        qs = qs.filter(goods_code=goods_code)
    return list(qs.values()[:limit])


def total_by_kind(tenant):
    return dict(Movement.objects.filter(tenant_openid=tenant).values_list("kind").annotate(Sum("qty")))


def expiry_alerts(tenant, warn_days=None):
    """Raise alerts for expired lots and lots expiring within inventory.expiry_warn_days."""
    from .alerts import raise_alert
    from .models import Alert
    warn_days = int(warn_days if warn_days is not None else config.get("inventory.expiry_warn_days", 30))
    today = date.today()
    raised = 0
    for lot in StockLot.objects.filter(tenant_openid=tenant, qty__gt=0, expiry_date__isnull=False,
                                       expiry_date__lte=today + timedelta(days=warn_days)):
        expired = lot.expiry_date < today
        a = raise_alert(tenant, Alert.EXPIRY,
                        f"{lot.goods_code} lot {lot.lot_number or '-'} {'EXPIRED' if expired else 'expires soon'}",
                        f"{lot.qty} in {lot.bin_name}, expiry {lot.expiry_date}. "
                        f"{'It will not be picked. Move it to a damage/hold bin.' if expired else ''}",
                        ref=lot.goods_code, severity="alarm" if expired else "warn",
                        dedupe_key=f"expiry:{lot.pk}:{'x' if expired else 'w'}")
        raised += bool(a)
    return raised
