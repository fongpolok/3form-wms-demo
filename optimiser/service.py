"""Which engine a company uses, pick lists from stock, and the alarm when cuOpt cannot answer."""
import logging
from collections import OrderedDict

from core import config, secrets

from . import pick
from .cuopt import CuoptUnavailable
from .models import OptimiserSetting

logger = logging.getLogger("aps")
ALERT_KIND = "OPTIMISER_UNAVAILABLE"


def settings_for(tenant):
    row = OptimiserSetting.objects.filter(tenant_openid=tenant).first()
    token = secrets.decrypt(row.cuopt_token_enc) if row and row.cuopt_token_enc else ""
    return {"plan_engine": row.plan_engine if row else config.get("optimiser.plan_engine", "builtin"),
            "pick_engine": row.pick_engine if row else config.get("optimiser.pick_engine", "builtin"),
            "cuopt_url": row.cuopt_url if row else "", "cuopt_token": token,
            "has_token": bool(token)}


def raise_unavailable(tenant, what, exc):
    """Red alert. Nothing else changes: the last published plan / the stock pick stay as they were."""
    from inventory import alerts
    logger.error("cuOpt unavailable for %s: %s", what, exc)
    alerts.raise_alert(tenant, ALERT_KIND, f"cuOpt unavailable: {what} not optimised",
                       f"{exc} The last published plan is kept. Fix the cuOpt server or switch the engine to "
                       "Built-in in Settings → Integrations.", severity="alarm", dedupe_key=f"cuopt:{what}")


def close_unavailable(tenant, what):
    from inventory import alerts
    alerts.close_alerts(tenant, f"cuopt:{what}")


# ------------------------------------------------------------ pick lists
def _bin_locations(tenant, bins):
    from inventory.models import BinZone
    return {b.bin_name: (b.aisle, b.position)
            for b in BinZone.objects.filter(tenant_openid=tenant, bin_name__in=list(bins))}


def allocate(tenant, lines):
    """FEFO / FIFO lots for [{goods_code, qty}] WITHOUT moving stock. Returns (stops by bin, shortages)."""
    from inventory import services as inv
    stops, short = OrderedDict(), []
    for line in lines:
        code, remaining = line["goods_code"], int(line["qty"])
        for lot in inv.pickable_lots(tenant, code):
            if remaining <= 0:
                break
            take = min(lot.qty, remaining)
            stops.setdefault(lot.bin_name, []).append(
                {"goods_code": code, "lot_number": lot.lot_number, "qty": take,
                 "expiry_date": lot.expiry_date.isoformat() if lot.expiry_date else None})
            remaining -= take
        if remaining > 0:
            short.append({"goods_code": code, "short_by": remaining})
    return stops, short


def pick_list(tenant, lines, purpose):
    """Ordered pick list for `lines`. Raises CuoptUnavailable (after alerting) when cuOpt is chosen and down."""
    stops_by_bin, short = allocate(tenant, lines)
    where = _bin_locations(tenant, stops_by_bin)
    stops = [{"bin_name": b, "aisle": where.get(b, (None, None))[0], "position": where.get(b, (None, None))[1],
              "lines": ls} for b, ls in stops_by_bin.items()]
    cfg = settings_for(tenant)
    try:
        route = pick.plan_route(stops, cfg["pick_engine"], cfg["cuopt_url"], cfg["cuopt_token"])
    except CuoptUnavailable as exc:
        raise_unavailable(tenant, "pick route", exc)
        raise
    if cfg["pick_engine"] == "cuopt":
        close_unavailable(tenant, "pick route")
    route.update({"purpose": purpose, "shortages": short})
    return route


def order_pick_list(tenant, wo_id):
    """Materials for the batches of a work order that have not started yet (from the product recipe)."""
    from core import mongo
    from inventory import services as inv
    db = mongo.db()
    wo = db.work_orders.find_one({"wo_id": wo_id, "tenant_openid": tenant})
    if wo is None:
        raise ValueError("Work order not found.")
    qty = sum(int(b["qty"]) for b in db.batches.find({"wo_id": wo_id, "status": "waiting", "current_step_no": 1}))
    if not qty:
        raise ValueError("Every batch of this order has started, so there is nothing left to pick.")
    need = inv.requirements(tenant, wo["product_code"], qty)
    if not need:
        raise ValueError("This product has no recipe, so there is nothing to pick.")
    return pick_list(tenant, [{"goods_code": c, "qty": q} for c, q in need.items()], f"materials for {wo_id}")
