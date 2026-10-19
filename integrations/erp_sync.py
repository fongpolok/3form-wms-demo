"""
ERP <-> MES sync.

  Orders in   every erp.poll_minutes: pull released orders from each enabled SAP / Oracle
              connection. Valid orders become work orders (source ERP, erp_ref kept);
              anything that does not fit (unknown product, bad quantity / date) waits in
              the ERP inbox for the PIC to fix or reject. Never imported twice.
  Results out when an ERP order is done, its result (good, scrap by reason, batch IDs,
              shipments, finish time) goes into the outbox; sending is retried until the
              ERP accepts it. Alert if something waits longer than erp.outbox_alert_minutes.
  Staff       daily from Workday: create / rename / disable WORKER accounts only.
"""
import logging
import math
from datetime import date, datetime, timedelta, timezone

from django.utils import timezone as dj_tz

from accounts import audit
from accounts.models import Account
from core import config, mongo
from goods.models import ListModel as Goods
from inventory import alerts

from .connectors import ErpError, for_connection
from .models import ErpConnection

logger = logging.getLogger("app")


def _now():
    return datetime.now(timezone.utc)


def system_account(tenant):
    acct, _ = Account.objects.get_or_create(
        tenant_openid=tenant, staff_id="SYSTEM-ERP",
        defaults={"display_name": "ERP connector", "role": Account.ROLE_AGENT, "source": "system"})
    return acct


# ------------------------------------------------------------------ orders in
def validate(tenant, o):
    problems = []
    if not o["erp_ref"]:
        problems.append("No ERP order number.")
    if not Goods.objects.filter(openid=tenant, goods_code=o["product_code"], is_delete=False).exists():
        problems.append(f"Product {o['product_code'] or '(blank)'} is not in the goods list.")
    try:
        if int(float(o["qty"])) <= 0:
            problems.append("Quantity must be more than 0.")
    except (TypeError, ValueError):
        problems.append(f"Quantity '{o['qty']}' is not a number.")
    try:
        date.fromisoformat(str(o["due_date"])[:10])
    except ValueError:
        problems.append(f"Due date '{o['due_date']}' is not a date.")
    return problems


def _import(tenant, conn, o, actor):
    from mes import services as mes
    qty = int(float(o["qty"]))
    size = int(config.get("erp.default_batch_size", 1000))
    try:
        prio = max(1, min(5, int(o.get("priority") or 3)))
    except (TypeError, ValueError):
        prio = 3
    wo, _ = mes.create_work_order(actor, {"product_code": o["product_code"], "qty": qty,
                                          "batches": max(1, math.ceil(qty / size)), "due_date": str(o["due_date"])[:10],
                                          "client": o.get("client", ""), "client_priority": prio,
                                          "ship_mode": o.get("ship_mode", "stock")}, source="ERP")
    mongo.db().work_orders.update_one({"wo_id": wo["wo_id"]}, {"$set": {"erp_ref": o["erp_ref"], "erp_conn": conn.pk,
                                                                        "erp_system": conn.system}})
    return wo["wo_id"]


def pull_orders(conn):
    t = conn.tenant_openid
    db = mongo.db()
    rows = for_connection(conn).fetch_released_orders()
    actor = system_account(t)
    out = {"received": len(rows), "imported": [], "inbox": [], "skipped": 0}
    for o in rows:
        if db.work_orders.find_one({"tenant_openid": t, "erp_ref": o["erp_ref"], "erp_conn": conn.pk}) or \
                db.erp_inbox.find_one({"tenant_openid": t, "erp_ref": o["erp_ref"], "conn_id": conn.pk,
                                       "status": {"$in": ["pending", "rejected"]}}):
            out["skipped"] += 1
            continue
        problems = validate(t, o)
        if problems:
            db.erp_inbox.insert_one({"tenant_openid": t, "conn_id": conn.pk, "system": conn.system, "erp_ref": o["erp_ref"],
                                     "order": {k: v for k, v in o.items() if k != "raw"}, "raw": o["raw"],
                                     "problems": problems, "status": "pending", "received_at": _now()})
            out["inbox"].append(o["erp_ref"])
        else:
            out["imported"].append(_import(t, conn, o, actor))
    if out["inbox"]:
        alerts.raise_alert(t, "ERP_INBOX", f"{len(out['inbox'])} ERP order(s) need the PIC",
                           "Unknown product, bad quantity or date: see the ERP inbox.", ref=conn.name,
                           dedupe_key=f"erp-inbox:{conn.pk}")
    logger.info("ERP pull %s: %s", conn.name, {k: v if isinstance(v, int) else len(v) for k, v in out.items()})
    return out


def inbox_decide(account, erp_ref, conn_id, approve, edits=None):
    db = mongo.db()
    item = db.erp_inbox.find_one({"tenant_openid": account.tenant_openid, "erp_ref": erp_ref, "conn_id": int(conn_id),
                                  "status": "pending"})
    if not item:
        raise ErpError("Inbox item not found.")
    if not approve:
        db.erp_inbox.update_one({"_id": item["_id"]}, {"$set": {"status": "rejected", "decided_by": account.display_name,
                                                                 "decided_at": _now()}})
        audit.record(account, "erp.inbox.reject", "erp_order", erp_ref, before=item["order"])
        return None
    order = {**item["order"], **{k: v for k, v in (edits or {}).items() if k in
                                 ("product_code", "qty", "due_date", "client", "ship_mode")}}
    problems = validate(account.tenant_openid, order)
    if problems:
        raise ErpError(" ".join(problems))
    conn = ErpConnection.objects.get(pk=item["conn_id"])
    wo_id = _import(account.tenant_openid, conn, order, account)
    db.erp_inbox.update_one({"_id": item["_id"]}, {"$set": {"status": "imported", "wo_id": wo_id,
                                                             "decided_by": account.display_name, "decided_at": _now()}})
    audit.record(account, "erp.inbox.approve", "erp_order", erp_ref, before=item["order"], after=order)
    return wo_id


# ------------------------------------------------------------------ results out
def enqueue_result(db, session, wo_id):
    """Called when a work order is done (inside the MES transaction)."""
    wo = db.work_orders.find_one({"wo_id": wo_id}, session=session)
    if not wo or not wo.get("erp_ref") or db.erp_outbox.find_one({"wo_id": wo_id}, session=session):
        return
    batches = list(db.batches.find({"wo_id": wo_id}, session=session))
    scrap = {}
    for e in db.step_events.find({"wo_id": wo_id, "type": "scrap"}, session=session):
        scrap[e["reason_code"]] = scrap.get(e["reason_code"], 0) + int(e.get("qty", 0))
    good = sum(b.get("good_qty_out") or 0 for b in batches)
    finished = wo.get("finished_at") or _now()
    result = {"erp_ref": wo["erp_ref"], "wo_id": wo_id, "good_qty": good, "scrap_qty": sum(scrap.values()),
              "scrap_by_reason": scrap, "batch_ids": [b["batch_id"] for b in batches],
              "shipment_ids": [b["shipment_id"] for b in batches if b.get("shipment_id")],
              "finished_at": finished.isoformat(), "text": f"3Form {wo_id}: good {good}, scrap {sum(scrap.values())}"}
    db.erp_outbox.insert_one({"tenant_openid": wo["tenant_openid"], "wo_id": wo_id, "conn_id": wo["erp_conn"],
                              "result": result, "status": "pending", "attempts": 0, "created_at": _now()},
                             session=session)


def push_outbox(tenant):
    db = mongo.db()
    sent = failed = 0
    for item in db.erp_outbox.find({"tenant_openid": tenant, "status": "pending"}).sort("created_at", 1).limit(100):
        conn = ErpConnection.objects.filter(pk=item["conn_id"], enabled=True).first()
        if conn is None:
            continue
        try:
            ref = for_connection(conn).push_result(item["result"])
            db.erp_outbox.update_one({"_id": item["_id"]}, {"$set": {"status": "sent", "sent_at": _now(), "erp_confirmation": ref}})
            sent += 1
        except ErpError as exc:
            db.erp_outbox.update_one({"_id": item["_id"]}, {"$inc": {"attempts": 1}, "$set": {"last_error": str(exc),
                                                                                             "last_try": _now()}})
            failed += 1
    oldest = db.erp_outbox.find_one({"tenant_openid": tenant, "status": "pending"}, sort=[("created_at", 1)])
    limit = timedelta(minutes=float(config.get("erp.outbox_alert_minutes", 60)))
    if oldest and _now() - oldest["created_at"].replace(tzinfo=timezone.utc) > limit:
        alerts.raise_alert(tenant, "ERP_OUTBOX", "ERP results not delivered",
                           f"Oldest waiting: {oldest['wo_id']} since {oldest['created_at']:%Y-%m-%d %H:%M} UTC. "
                           f"Last error: {oldest.get('last_error', '-')}", ref=oldest["wo_id"], severity="alarm",
                           dedupe_key="erp-outbox")
    elif not oldest:
        alerts.close_alerts(tenant, "erp-outbox")
    return {"sent": sent, "failed": failed}


# ------------------------------------------------------------------ staff
def import_staff(conn):
    t = conn.tenant_openid
    staff = for_connection(conn).fetch_staff()
    created = renamed = disabled = 0
    seen = set()
    for s in staff:
        seen.add(s["staff_id"])
        acct = Account.objects.filter(tenant_openid=t, staff_id=s["staff_id"]).first()
        if acct is None:
            if s["active"]:
                Account.objects.create(tenant_openid=t, staff_id=s["staff_id"], display_name=s["name"] or s["staff_id"],
                                       role=Account.ROLE_WORKER, source="workday")
                created += 1
            continue
        if acct.role != Account.ROLE_WORKER:
            continue                      # PIC / EM accounts are never changed by the import
        if s["name"] and acct.display_name != s["name"]:
            acct.display_name = s["name"]; renamed += 1
        if not s["active"] and acct.is_active:
            acct.is_active = False; disabled += 1
        acct.save()
    # Workday-created workers missing from the report have left.
    for acct in Account.objects.filter(tenant_openid=t, source="workday", role=Account.ROLE_WORKER, is_active=True):
        if acct.staff_id not in seen:
            acct.is_active = False; acct.save(); disabled += 1
    res = {"in_report": len(staff), "created": created, "renamed": renamed, "disabled": disabled}
    audit.record(system_account(t), "workday.import", "staff", conn.name, after=res, tenant_openid=t)
    return res


# ------------------------------------------------------------------ schedule
def _due(conn, kind, minutes):
    state = mongo.db().erp_state.find_one({"_id": f"{conn.pk}:{kind}"}) or {}
    last = state.get("at")
    return last is None or _now() - last.replace(tzinfo=timezone.utc) >= timedelta(minutes=minutes)


def _mark(conn, kind, result):
    mongo.db().erp_state.update_one({"_id": f"{conn.pk}:{kind}"}, {"$set": {"at": _now(), "result": result}}, upsert=True)
    conn.last_test_at = dj_tz.now()
    conn.last_test_result = f"{kind}: {result}"[:200]
    conn.save(update_fields=["last_test_at", "last_test_result"])


def sync_all(force=False):
    out = []
    for conn in ErpConnection.objects.filter(enabled=True):
        try:
            if conn.system == "WORKDAY":
                hour = int(config.get("erp.workday_daily_hour", 3))
                if force or (datetime.now().hour == hour and _due(conn, "staff", 120)):
                    r = import_staff(conn); _mark(conn, "staff", r); out.append((conn.name, r))
            else:
                if force or _due(conn, "orders", float(config.get("erp.poll_minutes", 15))):
                    r = pull_orders(conn)
                    _mark(conn, "orders", {k: v if isinstance(v, int) else len(v) for k, v in r.items()})
                    out.append((conn.name, r))
        except ErpError as exc:
            logger.warning("ERP sync %s failed: %s", conn.name, exc)
            _mark(conn, "error", str(exc))
            alerts.raise_alert(conn.tenant_openid, "ERP_ERROR", f"ERP connection {conn.name} failed", str(exc),
                               ref=conn.name, dedupe_key=f"erp-error:{conn.pk}")
            out.append((conn.name, {"error": str(exc)}))
            continue
        alerts.close_alerts(conn.tenant_openid, f"erp-error:{conn.pk}")
    for t in ErpConnection.objects.filter(enabled=True).values_list("tenant_openid", flat=True).distinct():
        out.append(("outbox", push_outbox(t)))
    return out
