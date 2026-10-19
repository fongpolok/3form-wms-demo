"""Events that ask the APS for a new plan. A planner problem must never block
production, so every trigger catches and logs its own errors."""
import logging
from datetime import datetime, timedelta, timezone

from core import config, mongo

logger = logging.getLogger("aps")


def _enabled():
    return bool(config.get("aps.auto_replan", True))


def replan_safely(tenant, reason, actor="system", urgent=False):
    if not _enabled():
        return None
    try:
        from .service import request_replan
        return request_replan(tenant, reason, actor, urgent=urgent)
    except Exception:  # noqa: BLE001 - planning must not break MES/WMS actions
        logger.exception("Re-plan failed (%s)", reason)
        return None


def on_new_order(tenant, wo):
    if wo.get("status") == "waiting_material":
        return None          # cannot be planned until material is there
    return replan_safely(tenant, f"new order {wo['wo_id']}", wo.get("created_by", "system"),
                         urgent=bool(wo.get("special_urgent")))


def on_material_released(tenant, wo_ids):
    if not wo_ids:
        return None
    urgent = bool(mongo.db().work_orders.find_one({"wo_id": {"$in": wo_ids}, "special_urgent": True}))
    return replan_safely(tenant, f"material released for {', '.join(wo_ids)}", urgent=urgent)


def check_long_stops(now=None):
    """Machines stopped longer than aps.replan_on_stop_minutes -> one draft re-plan per stop."""
    now = now or datetime.now(timezone.utc)
    limit = now - timedelta(minutes=float(config.get("aps.replan_on_stop_minutes", 30)))
    db = mongo.db()
    plans = []
    for w in db.wip.find({"status": "running", "stopped_since": {"$ne": None, "$lte": limit},
                          "replan_for_stop": {"$ne": True}}):
        db.wip.update_one({"_id": w["_id"]}, {"$set": {"replan_for_stop": True}})
        plans.append(replan_safely(w["tenant_openid"], f"{w['workstation']} stopped > "
                                   f"{config.get('aps.replan_on_stop_minutes', 30)} min ({w.get('stop_reason')})"))
    return plans
