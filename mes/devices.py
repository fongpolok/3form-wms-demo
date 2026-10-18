"""
Results coming from cameras through the site gateway.

  Vision camera (e.g. Cognex In-Sight):  PASS  |  FAIL,<reason>
      FAIL -> 1 piece of scrap, reason VISION, on the batch running at that workstation.
  Rack camera:  SLOT,<bin>,EMPTY | OCCUPIED | <goods code>
      compared with the inventory ledger; a mismatch raises an alert (stock is NOT changed).

The camera does the image processing; we only record its answer.
"""
import logging
from datetime import datetime, timezone
from types import SimpleNamespace

from accounts.models import Device
from core import mongo
from inventory import alerts
from inventory.models import Alert, StockLot
from userprofile.models import Users

from . import services

logger = logging.getLogger("camera")


def site_tenant(workstation=None):
    """The gateway has no login; the company comes from the devices registered on site."""
    qs = Device.objects.filter(is_active=True)
    if workstation:
        d = qs.filter(workstation=workstation).first()
        if d:
            return d.tenant_openid
    d = qs.first()
    if d:
        return d.tenant_openid
    u = Users.objects.filter(is_delete=False).order_by("id").first()
    return u.openid if u else ""


def _system_actor(tenant, name):
    return SimpleNamespace(pk=None, staff_id=name.upper().replace(" ", "_"), display_name=name, role="SYSTEM",
                           tenant_openid=tenant)


def record_vision_result(event_id, device_id, workstation, result, reason=""):
    db = mongo.db()
    if db.vision_results.find_one({"event_id": event_id}):
        return {"duplicate": True}
    tenant = site_tenant(workstation)
    running = db.wip.find_one({"workstation": workstation, "status": services.WIP_RUNNING})
    doc = {"event_id": event_id, "device_id": device_id, "workstation": workstation, "tenant_openid": tenant,
           "result": result.upper(), "reason": reason, "ts": datetime.now(timezone.utc),
           "wip_id": running["wip_id"] if running else None}
    db.vision_results.insert_one(doc)
    if doc["result"] == "FAIL":
        if running is None:
            logger.warning("Vision FAIL at %s but no batch is running there (%s)", workstation, reason)
            return {"recorded": True, "scrap": False}
        services.record_scrap(_system_actor(tenant, "Vision camera"), workstation, 1, "VISION", f"v-{event_id}",
                              note=reason, source="camera")
        logger.info("Vision FAIL -> scrap 1 on %s (%s)", running["wip_id"], reason)
        return {"recorded": True, "scrap": True}
    return {"recorded": True, "scrap": False}


def record_rack_report(event_id, device_id, bin_name, observed):
    db = mongo.db()
    if db.rack_reports.find_one({"event_id": event_id}):
        return {"duplicate": True}
    tenant = site_tenant()
    observed = (observed or "").strip()
    expected = sorted(set(StockLot.objects.filter(tenant_openid=tenant, bin_name=bin_name, qty__gt=0)
                          .values_list("goods_code", flat=True)))
    if observed.upper() == "EMPTY":
        mismatch = bool(expected)
        problem = f"Camera sees {bin_name} EMPTY; system has {', '.join(expected)}" if mismatch else ""
    elif observed.upper() == "OCCUPIED":
        mismatch = not expected
        problem = f"Camera sees something in {bin_name}; system says it is empty" if mismatch else ""
    else:
        mismatch = observed not in expected
        problem = (f"Camera sees {observed} in {bin_name}; system has "
                   f"{', '.join(expected) or 'nothing'}") if mismatch else ""
    db.rack_reports.insert_one({"event_id": event_id, "device_id": device_id, "bin_name": bin_name,
                                "observed": observed, "expected": expected, "mismatch": mismatch,
                                "tenant_openid": tenant, "ts": datetime.now(timezone.utc)})
    key = f"rack:{bin_name}"
    if mismatch:
        alerts.raise_alert(tenant, Alert.RACK, f"Rack check: {bin_name} does not match", problem, ref=bin_name,
                           dedupe_key=key)
        logger.warning("Rack mismatch %s: %s", bin_name, problem)
    else:
        alerts.close_alerts(tenant, key, by="rack camera")
    return {"recorded": True, "mismatch": mismatch}
