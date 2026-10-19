"""
Material gate between MES (orders in MongoDB) and the inventory ledger.

  * New order       -> reserve all materials (recipe x qty), or hold the WHOLE
                       order as "waiting_material" + material requests + alert.
  * Stock arrives   -> recheck_waiting(): waiting orders, most urgent first,
                       are reserved and released as soon as everything is there.
  * Batch starts    -> consume_for_batch(): issue the batch's share from stock
                       (FEFO/FIFO) against the order's reservation.
"""
import logging

from django.db import transaction
from django.utils import timezone

from core import mongo
from inventory import alerts
from inventory.models import Alert, MaterialRequest, Reservation
from inventory.services import available, goods_desc, issue, pickable_lots, requirements

logger = logging.getLogger("app")
WAITING, RELEASED = "waiting_material", "released"


def _short_key(wo_id):
    return f"shortage:{wo_id}"


@transaction.atomic
def try_reserve(tenant, wo):
    """All or nothing. Returns list of shortages ([] = fully reserved)."""
    needs = requirements(tenant, wo["product_code"], wo["qty"])
    if not needs:
        return []
    for code in needs:                     # lock the lots we are about to count
        pickable_lots(tenant, code, lock=True)
    shortages = []
    for code, qty in needs.items():
        free = available(tenant, code) + sum(r.open_qty for r in Reservation.objects.filter(
            tenant_openid=tenant, wo_id=wo["wo_id"], goods_code=code))
        if free < qty:
            shortages.append({"goods_code": code, "goods_desc": goods_desc(tenant, code), "needed": qty,
                              "available": max(free, 0), "short": qty - max(free, 0)})
    if shortages:
        return shortages
    for code, qty in needs.items():
        Reservation.objects.update_or_create(tenant_openid=tenant, wo_id=wo["wo_id"], goods_code=code,
                                             defaults={"qty_reserved": qty})
    return []


def _apply(tenant, wo, shortages):
    db = mongo.db()
    now = timezone.now()
    if shortages:
        db.work_orders.update_one({"wo_id": wo["wo_id"]}, {"$set": {"status": WAITING, "shortages": shortages}})
        MaterialRequest.objects.filter(tenant_openid=tenant, wo_id=wo["wo_id"], status=MaterialRequest.OPEN).delete()
        for sh in shortages:
            MaterialRequest.objects.create(tenant_openid=tenant, wo_id=wo["wo_id"], goods_code=sh["goods_code"],
                                           goods_desc=sh["goods_desc"], qty_short=sh["short"],
                                           needed_by=wo["due_date"])
        alerts.raise_alert(tenant, Alert.SHORTAGE, f"{wo['wo_id']} is waiting for material",
                           "; ".join(f"{s['goods_code']} short {s['short']}" for s in shortages),
                           ref=wo["wo_id"], severity="alarm" if wo.get("special_urgent") else "warn",
                           dedupe_key=_short_key(wo["wo_id"]))
        logger.warning("Order %s held: %s", wo["wo_id"], shortages)
    else:
        db.work_orders.update_one({"wo_id": wo["wo_id"], "status": {"$in": [WAITING, RELEASED]}},
                                  {"$set": {"status": RELEASED, "shortages": [], "materials_reserved_at": now}})
        MaterialRequest.objects.filter(tenant_openid=tenant, wo_id=wo["wo_id"], status=MaterialRequest.OPEN).update(
            status=MaterialRequest.CLOSED, closed_at=now)
        alerts.close_alerts(tenant, _short_key(wo["wo_id"]))
        logger.info("Order %s materials reserved", wo["wo_id"])


def gate_new_order(tenant, wo_id):
    wo = mongo.db().work_orders.find_one({"wo_id": wo_id})
    _apply(tenant, wo, try_reserve(tenant, wo))


def recheck_waiting(tenant):
    """Call after stock arrives or is corrected. Most urgent / earliest due first."""
    released = []
    waiting = mongo.db().work_orders.find({"tenant_openid": tenant, "status": WAITING}).sort(
        [("special_urgent", -1), ("due_date", 1), ("client_priority", 1), ("created_at", 1)])
    for wo in waiting:
        shortages = try_reserve(tenant, wo)
        _apply(tenant, wo, shortages)
        if not shortages:
            released.append(wo["wo_id"])
    if released:
        from aps.triggers import on_material_released
        on_material_released(tenant, released)
    return released


def consume_for_batch(tenant, wo, batch, actor):
    """Issue this batch's share of the order's reserved materials. Caller holds a DB transaction."""
    needs = requirements(tenant, wo["product_code"], batch["qty"])
    used = []
    for code, need in needs.items():
        res = Reservation.objects.select_for_update().filter(tenant_openid=tenant, wo_id=wo["wo_id"],
                                                             goods_code=code).first()
        if res is None:
            continue
        others_open = mongo.db().batches.count_documents({"wo_id": wo["wo_id"], "current_step_no": 1,
                                                          "status": "waiting", "batch_id": {"$ne": batch["batch_id"]}})
        take = res.open_qty if others_open == 0 else min(need, res.open_qty)   # last batch takes the rounding rest
        if take <= 0:
            continue
        used += issue(tenant, code, take, batch["batch_id"], actor)
        res.qty_consumed += take
        res.save(update_fields=["qty_consumed"])
    logger.info("Batch %s consumed %s", batch["batch_id"], used)
    return used
