"""
MES rules: work orders, batches, WIP and shop-floor events.

Data lives in MongoDB. Every worker / gateway action is a `step_events`
document whose event_id is unique, so a replayed offline queue is ignored
the second time. Each action and its side effects run in one transaction.

Plain functions only (no HTTP), so the API, the gateway, management commands
and tests all share the same rules.
"""
import logging
from datetime import datetime, timezone

from pymongo.errors import DuplicateKeyError

from accounts import audit
from core import config, ids, mongo

from .workstations import get_workstation, list_workstations, routing

logger = logging.getLogger("app")

WO_RELEASED, WO_IN_PROGRESS, WO_DONE = "released", "in_progress", "done"
BATCH_WAITING, BATCH_RUNNING, BATCH_DONE = "waiting", "running", "done"
WIP_RUNNING, WIP_DONE = "running", "done"
SHIP_MODES = ("stock", "direct")


class MesError(Exception):
    """Business-rule refusal, shown to the user as-is."""


def _now():
    return datetime.now(timezone.utc)


def _db():
    return mongo.db()


def _reason_codes(kind):
    key = "scrap_reasons" if kind == "scrap" else "downtime_reasons"
    return {r["code"]: r for r in config.industry().get(key, [])}


def _clean(doc):
    if doc is not None:
        doc.pop("_id", None)
    return doc


def _actor_fields(account, device=None):
    return {"account_id": account.pk, "staff_id": account.staff_id, "actor_name": account.display_name,
            "role": account.role, "device_id": device.pk if device else None}


# ----------------------------------------------------------------- work orders
def create_work_order(account, data, source="PIC", request=None):
    """PIC-typed orders are always Special / Urgent. ERP orders come in with source='ERP'."""
    try:
        qty = int(data.get("qty", 0))
        n_batches = max(1, int(data.get("batches", 1)))
    except (TypeError, ValueError):
        raise MesError("Quantity and number of batches must be whole numbers.")
    if qty <= 0:
        raise MesError("Quantity must be more than 0.")
    if n_batches > qty:
        raise MesError("Cannot have more batches than pieces.")
    ship_mode = data.get("ship_mode", "stock")
    if ship_mode not in SHIP_MODES:
        raise MesError("Ship mode must be 'stock' or 'direct'.")
    if not data.get("product_code") or not data.get("due_date"):
        raise MesError("Product code and due date are required.")

    steps = routing(data.get("industry"))
    db = _db()
    wo_id = ids.new_work_order_id(db)
    now = _now()
    wo = {
        "wo_id": wo_id, "tenant_openid": account.tenant_openid,
        "product_code": data["product_code"], "product_name": data.get("product_name", ""),
        "client": data.get("client", ""), "client_priority": int(data.get("client_priority", 3)),
        "qty": qty, "due_date": str(data["due_date"]), "ship_mode": ship_mode,
        "source": source, "special_urgent": source == "PIC" or bool(data.get("special_urgent")),
        "routing": [{"step_no": s["step_no"], "code": s["code"], "name": s["name"],
                     "measurement": s.get("measurement"), "is_qc": bool(s.get("is_qc"))} for s in steps],
        "status": WO_RELEASED, "created_by": account.display_name, "created_at": now,
    }
    batches = []
    base, extra = divmod(qty, n_batches)
    for i in range(n_batches):
        batches.append({
            "batch_id": ids.new_batch_id(db), "wo_id": wo_id, "tenant_openid": account.tenant_openid,
            "qty": base + (1 if i < extra else 0), "current_step_no": 1, "total_steps": len(steps),
            "status": BATCH_WAITING, "good_qty_out": None, "created_at": now,
        })
    with mongo.client().start_session() as s, s.start_transaction():
        db.work_orders.insert_one(wo, session=s)
        db.batches.insert_many(batches, session=s)
    audit.record(account, "work_order.create", "work_order", wo_id,
                 after={"qty": qty, "batches": [b["batch_id"] for b in batches], "special_urgent": wo["special_urgent"]},
                 request=request)
    logger.info("Work order %s created by %s with %d batch(es)", wo_id, account, n_batches)
    return _clean(wo), [_clean(b) for b in batches]


def list_work_orders(tenant_openid, status=None, limit=200):
    q = {"tenant_openid": tenant_openid}
    if status:
        q["status"] = status
    cur = _db().work_orders.find(q, {"_id": 0}).sort([("special_urgent", -1), ("due_date", 1)]).limit(limit)
    return list(cur)


# ------------------------------------------------------------------ events
def _insert_event(db, session, event):
    """Insert once. Returns False if this event_id was already processed.

    Checked with a read first: a duplicate-key error inside a Mongo transaction
    would abort the whole transaction instead of being a harmless no-op.
    """
    if db.step_events.find_one({"event_id": event["event_id"]}, {"_id": 1}, session=session):
        logger.info("Duplicate event ignored: %s", event["event_id"])
        return False
    db.step_events.insert_one(event, session=session)
    return True


def _running_wip(db, workstation, session=None):
    return db.wip.find_one({"workstation": workstation, "status": WIP_RUNNING}, session=session)


def start_step(account, workstation_code, batch_id, event_id, device=None, client_ts=None):
    ws = get_workstation(workstation_code)
    if ws is None:
        raise MesError(f"Unknown workstation {workstation_code}.")
    db = _db()
    with mongo.client().start_session() as s, s.start_transaction():
        if db.step_events.find_one({"event_id": event_id}, session=s):
            return _clean(db.wip.find_one({"start_event_id": event_id}, session=s))
        if _running_wip(db, workstation_code, s):
            raise MesError("This workstation is already running a batch. Finish it first.")
        batch = db.batches.find_one({"batch_id": batch_id, "tenant_openid": account.tenant_openid}, session=s)
        if batch is None:
            raise MesError(f"Batch {batch_id} not found.")
        if batch["status"] == BATCH_DONE:
            raise MesError("This batch is already finished.")
        if batch["current_step_no"] != ws["step_no"]:
            raise MesError(f"This batch is at step {batch['current_step_no']}, not this workstation's step {ws['step_no']}.")
        if batch["status"] == BATCH_RUNNING:
            raise MesError("This batch is already running at another workstation.")
        qty_in = batch["qty"] if ws["step_no"] == 1 else batch.get("last_good_qty", batch["qty"])
        now = _now()
        wip = {
            "wip_id": ids.new_wip_id(batch_id, ws["step_no"], db), "batch_id": batch_id, "wo_id": batch["wo_id"],
            "tenant_openid": account.tenant_openid, "step_no": ws["step_no"], "step_code": ws["step_code"],
            "workstation": workstation_code, "status": WIP_RUNNING, "qty_in": qty_in,
            "good_qty": None, "scrap_qty": 0, "downtime_seconds": 0, "stopped_since": None,
            "started_at": now, "finished_at": None, "started_by": account.staff_id,
            "start_event_id": event_id, "edited_by_pic": False,
        }
        db.wip.insert_one(wip, session=s)
        _insert_event(db, s, {"event_id": event_id, "type": "start", "wip_id": wip["wip_id"], "batch_id": batch_id,
                              "wo_id": batch["wo_id"], "workstation": workstation_code, "step_no": ws["step_no"],
                              "tenant_openid": account.tenant_openid, "ts": now, "client_ts": client_ts,
                              "source": "worker", **_actor_fields(account, device)})
        db.batches.update_one({"batch_id": batch_id}, {"$set": {"status": BATCH_RUNNING}}, session=s)
        db.work_orders.update_one({"wo_id": batch["wo_id"], "status": WO_RELEASED},
                                  {"$set": {"status": WO_IN_PROGRESS}}, session=s)
    logger.info("START %s at %s by %s", wip["wip_id"], workstation_code, account.staff_id)
    return _clean(wip)


def _require_running(db, workstation_code, s):
    wip = _running_wip(db, workstation_code, s)
    if wip is None:
        raise MesError("No batch is running at this workstation. Press START first.")
    return wip


def record_scrap(account, workstation_code, qty, reason_code, event_id, note="", device=None,
                 client_ts=None, source="worker"):
    try:
        qty = int(qty)
    except (TypeError, ValueError):
        raise MesError("Scrap quantity must be a whole number.")
    if qty <= 0:
        raise MesError("Scrap quantity must be more than 0.")
    reasons = _reason_codes("scrap")
    if reason_code not in reasons:
        raise MesError("Please choose a scrap reason.")
    if reasons[reason_code].get("system_only") and source == "worker":
        raise MesError("This reason is recorded automatically by the camera.")
    if reasons[reason_code].get("needs_note") and not note.strip():
        raise MesError("Please add a short note for 'Other'.")
    db = _db()
    with mongo.client().start_session() as s, s.start_transaction():
        wip = _require_running(db, workstation_code, s)
        if not _insert_event(db, s, {"event_id": event_id, "type": "scrap", "wip_id": wip["wip_id"],
                                     "batch_id": wip["batch_id"], "wo_id": wip["wo_id"],
                                     "workstation": workstation_code, "step_no": wip["step_no"],
                                     "tenant_openid": account.tenant_openid, "qty": qty,
                                     "reason_code": reason_code, "note": note, "ts": _now(),
                                     "client_ts": client_ts, "source": source, **_actor_fields(account, device)}):
            return {"duplicate": True}
        db.wip.update_one({"wip_id": wip["wip_id"]}, {"$inc": {"scrap_qty": qty}}, session=s)
    logger.info("SCRAP %d (%s) on %s by %s", qty, reason_code, wip["wip_id"], account.staff_id)
    # Workers never see scrap totals: return only an acknowledgement.
    return {"recorded": True}


def machine_stop(account, workstation_code, reason_code, event_id, note="", device=None, client_ts=None):
    if reason_code not in _reason_codes("downtime"):
        raise MesError("Please choose why the machine stopped.")
    db = _db()
    now = _now()
    with mongo.client().start_session() as s, s.start_transaction():
        wip = _require_running(db, workstation_code, s)
        if wip.get("stopped_since"):
            raise MesError("Machine is already marked as stopped.")
        if not _insert_event(db, s, {"event_id": event_id, "type": "stop", "wip_id": wip["wip_id"],
                                     "batch_id": wip["batch_id"], "wo_id": wip["wo_id"],
                                     "workstation": workstation_code, "step_no": wip["step_no"],
                                     "tenant_openid": account.tenant_openid, "reason_code": reason_code,
                                     "note": note, "ts": now, "client_ts": client_ts, "source": "worker",
                                     **_actor_fields(account, device)}):
            return {"duplicate": True}
        db.wip.update_one({"wip_id": wip["wip_id"]},
                          {"$set": {"stopped_since": now, "stop_reason": reason_code}}, session=s)
    logger.info("STOP %s (%s) by %s", workstation_code, reason_code, account.staff_id)
    return {"stopped": True}


def _close_downtime(db, s, wip, now):
    if not wip.get("stopped_since"):
        return 0
    secs = int((now - wip["stopped_since"]).total_seconds())
    db.wip.update_one({"wip_id": wip["wip_id"]},
                      {"$set": {"stopped_since": None, "stop_reason": None}, "$inc": {"downtime_seconds": secs}},
                      session=s)
    return secs


def machine_resume(account, workstation_code, event_id, device=None, client_ts=None):
    db = _db()
    now = _now()
    with mongo.client().start_session() as s, s.start_transaction():
        wip = _require_running(db, workstation_code, s)
        if not wip.get("stopped_since"):
            raise MesError("Machine is not marked as stopped.")
        if not _insert_event(db, s, {"event_id": event_id, "type": "resume", "wip_id": wip["wip_id"],
                                     "batch_id": wip["batch_id"], "wo_id": wip["wo_id"],
                                     "workstation": workstation_code, "step_no": wip["step_no"],
                                     "tenant_openid": account.tenant_openid, "reason_code": wip.get("stop_reason"),
                                     "ts": now, "client_ts": client_ts, "source": "worker",
                                     **_actor_fields(account, device)}):
            return {"duplicate": True}
        secs = _close_downtime(db, s, wip, now)
    logger.info("RESUME %s after %ss by %s", workstation_code, secs, account.staff_id)
    return {"resumed": True, "downtime_seconds": secs}


def record_measurement(account, workstation_code, value, event_id, device=None, client_ts=None):
    ws = get_workstation(workstation_code)
    if ws is None or not ws.get("measurement"):
        raise MesError("This step has no measurement.")
    try:
        value = float(value)
    except (TypeError, ValueError):
        raise MesError("Measurement must be a number.")
    m = ws["measurement"]
    tol = float(config.get("mes.measurement_tolerance_pct", 5)) / 100.0
    target = m.get("target")
    in_spec = None if target is None else abs(value - target) <= abs(target) * tol
    db = _db()
    with mongo.client().start_session() as s, s.start_transaction():
        wip = _require_running(db, workstation_code, s)
        if not _insert_event(db, s, {"event_id": event_id, "type": "measure", "wip_id": wip["wip_id"],
                                     "batch_id": wip["batch_id"], "wo_id": wip["wo_id"],
                                     "workstation": workstation_code, "step_no": wip["step_no"],
                                     "tenant_openid": account.tenant_openid, "measure_name": m["name"],
                                     "unit": m["unit"], "value": value, "target": target, "in_spec": in_spec,
                                     "ts": _now(), "client_ts": client_ts, "source": "worker",
                                     **_actor_fields(account, device)}):
            return {"duplicate": True}
    logger.info("MEASURE %s %s=%s%s by %s", workstation_code, m["name"], value, m["unit"], account.staff_id)
    return {"recorded": True, "in_spec": in_spec}


def finish_step(account, workstation_code, good_qty, event_id, device=None, client_ts=None):
    try:
        good_qty = int(good_qty)
    except (TypeError, ValueError):
        raise MesError("Good quantity must be a whole number.")
    if good_qty < 0 and not config.get("mes.allow_negative_good_qty", False):
        raise MesError("Good quantity cannot be negative.")
    db = _db()
    now = _now()
    with mongo.client().start_session() as s, s.start_transaction():
        wip = _require_running(db, workstation_code, s)
        if good_qty + wip["scrap_qty"] > wip["qty_in"]:
            raise MesError(f"Good + scrap ({good_qty + wip['scrap_qty']}) is more than the {wip['qty_in']} pieces received.")
        if not _insert_event(db, s, {"event_id": event_id, "type": "finish", "wip_id": wip["wip_id"],
                                     "batch_id": wip["batch_id"], "wo_id": wip["wo_id"],
                                     "workstation": workstation_code, "step_no": wip["step_no"],
                                     "tenant_openid": account.tenant_openid, "qty": good_qty, "ts": now,
                                     "client_ts": client_ts, "source": "worker", **_actor_fields(account, device)}):
            return {"duplicate": True}
        _close_downtime(db, s, wip, now)
        db.wip.update_one({"wip_id": wip["wip_id"]},
                          {"$set": {"status": WIP_DONE, "good_qty": good_qty, "finished_at": now,
                                    "finished_by": account.staff_id}}, session=s)
        batch = db.batches.find_one({"batch_id": wip["batch_id"]}, session=s)
        last_step = wip["step_no"] >= batch["total_steps"]
        update = {"last_good_qty": good_qty, "status": BATCH_DONE if last_step else BATCH_WAITING}
        if last_step:
            update.update({"good_qty_out": good_qty, "finished_at": now})
        else:
            update["current_step_no"] = wip["step_no"] + 1
        db.batches.update_one({"batch_id": batch["batch_id"]}, {"$set": update}, session=s)
        if last_step and not db.batches.find_one({"wo_id": batch["wo_id"], "status": {"$ne": BATCH_DONE}},
                                                 session=s):
            db.work_orders.update_one({"wo_id": batch["wo_id"]}, {"$set": {"status": WO_DONE, "finished_at": now}},
                                      session=s)
    logger.info("FINISH %s good=%d by %s", wip["wip_id"], good_qty, account.staff_id)
    return {"finished": True, "wip_id": wip["wip_id"], "batch_done": last_step}


# --------------------------------------------------------- PIC corrections
EDITABLE_WIP_FIELDS = {"good_qty", "scrap_qty", "qty_in"}
EDITABLE_EVENT_FIELDS = {"qty", "reason_code", "note", "value"}


def pic_edit_wip(account, wip_id, changes, reason, request=None):
    """Only the PIC may correct WIP records. Every change is audited (old + new value)."""
    if not reason.strip():
        raise MesError("A reason is required for every correction.")
    bad = set(changes) - EDITABLE_WIP_FIELDS
    if bad:
        raise MesError(f"These fields cannot be edited: {', '.join(sorted(bad))}")
    db = _db()
    wip = db.wip.find_one({"wip_id": wip_id, "tenant_openid": account.tenant_openid})
    if wip is None:
        raise MesError("WIP not found.")
    clean = {k: int(v) for k, v in changes.items()}
    before = {k: wip.get(k) for k in clean}
    db.wip.update_one({"wip_id": wip_id}, {"$set": {**clean, "edited_by_pic": True}})
    audit.record(account, "wip.edit", "wip", wip_id, before=before, after=clean, reason=reason, request=request)
    return _clean(db.wip.find_one({"wip_id": wip_id}))


def pic_edit_event(account, event_id, changes, reason, request=None):
    if not reason.strip():
        raise MesError("A reason is required for every correction.")
    bad = set(changes) - EDITABLE_EVENT_FIELDS
    if bad:
        raise MesError(f"These fields cannot be edited: {', '.join(sorted(bad))}")
    db = _db()
    ev = db.step_events.find_one({"event_id": event_id, "tenant_openid": account.tenant_openid})
    if ev is None:
        raise MesError("Event not found.")
    if "reason_code" in changes and changes["reason_code"] not in _reason_codes("scrap"):
        raise MesError("Unknown scrap reason.")
    before = {k: ev.get(k) for k in changes}
    with mongo.client().start_session() as s, s.start_transaction():
        db.step_events.update_one({"event_id": event_id}, {"$set": {**changes, "edited_by_pic": True}}, session=s)
        if ev["type"] == "scrap" and "qty" in changes:
            delta = int(changes["qty"]) - int(ev.get("qty", 0))
            db.wip.update_one({"wip_id": ev["wip_id"]}, {"$inc": {"scrap_qty": delta}, "$set": {"edited_by_pic": True}},
                              session=s)
    audit.record(account, "event.edit", ev["type"], event_id, before=before, after=changes, reason=reason,
                 request=request)
    return _clean(db.step_events.find_one({"event_id": event_id}))


# ------------------------------------------------------------- read models
def worker_board(tenant_openid, workstation_code):
    """What the worker screen needs. Deliberately contains no scrap totals."""
    ws = get_workstation(workstation_code)
    if ws is None:
        raise MesError(f"Unknown workstation {workstation_code}.")
    db = _db()
    wip = db.wip.find_one({"workstation": workstation_code, "status": WIP_RUNNING, "tenant_openid": tenant_openid},
                          {"_id": 0, "scrap_qty": 0, "edited_by_pic": 0})
    queue = list(db.batches.find({"tenant_openid": tenant_openid, "current_step_no": ws["step_no"],
                                  "status": BATCH_WAITING}, {"_id": 0, "batch_id": 1, "wo_id": 1, "qty": 1,
                                                             "last_good_qty": 1})
                 .sort("created_at", 1).limit(20))
    wos = {w["wo_id"]: w for w in db.work_orders.find({"wo_id": {"$in": [b["wo_id"] for b in queue]
                                                                 + ([wip["wo_id"]] if wip else [])}},
                                                       {"_id": 0, "wo_id": 1, "product_name": 1, "special_urgent": 1,
                                                        "due_date": 1})}
    for b in queue:
        b["product_name"] = wos.get(b["wo_id"], {}).get("product_name", "")
        b["special_urgent"] = wos.get(b["wo_id"], {}).get("special_urgent", False)
    if wip:
        wip["product_name"] = wos.get(wip["wo_id"], {}).get("product_name", "")
        wip["machine_stopped"] = bool(wip.get("stopped_since"))
    queue.sort(key=lambda b: (not b["special_urgent"],))
    industry = config.industry()
    return {
        "workstation": ws,
        "current": wip,
        "queue": queue,
        "scrap_reasons": [r for r in industry["scrap_reasons"] if not r.get("system_only")],
        "downtime_reasons": industry["downtime_reasons"],
        "health": device_health_for(workstation_code),
    }


def progress_overview(tenant_openid, limit=100):
    """EM / PIC progress bars: Order -> each step -> stock or client."""
    db = _db()
    wos = list(db.work_orders.find({"tenant_openid": tenant_openid}, {"_id": 0})
               .sort([("status", 1), ("special_urgent", -1), ("due_date", 1)]).limit(limit))
    batches = {}
    for b in db.batches.find({"wo_id": {"$in": [w["wo_id"] for w in wos]}}, {"_id": 0}):
        batches.setdefault(b["wo_id"], []).append(b)
    out = []
    for w in wos:
        bs = batches.get(w["wo_id"], [])
        total = sum(b["total_steps"] for b in bs) or 1
        done_steps = sum(b["total_steps"] if b["status"] == BATCH_DONE else b["current_step_no"] - 1 for b in bs)
        out.append({**w, "batches": bs, "progress_pct": round(100.0 * done_steps / total, 1),
                    "final_stage": "To stock" if w["ship_mode"] == "stock" else "Ship to client"})
    return out


# ------------------------------------------------------------ gateway / health
def record_gateway_scan(event_id, device_id, workstation_code, code, ts=None):
    db = _db()
    try:
        db.scans.insert_one({"event_id": event_id, "device_id": device_id, "workstation": workstation_code,
                             "code": code.strip(), "ts": _now(), "device_ts": ts, "source": "gateway"})
    except DuplicateKeyError:
        return {"duplicate": True}
    db.device_health.update_one({"device_id": device_id},
                                {"$set": {"workstation": workstation_code, "last_seen": _now(), "status": "ok"}},
                                upsert=True)
    logging.getLogger("scanner").info("Scan %r from %s at %s", code, device_id, workstation_code)
    return {"recorded": True}


def scans_since(workstation_code, after_ts=None, limit=20):
    q = {"workstation": workstation_code}
    if after_ts:
        q["ts"] = {"$gt": after_ts}
    return list(_db().scans.find(q, {"_id": 0}).sort("ts", -1).limit(limit))


def record_heartbeat(gateway_id, devices):
    db = _db()
    now = _now()
    db.device_health.update_one({"device_id": gateway_id},
                                {"$set": {"kind": "gateway", "last_seen": now, "status": "ok"}}, upsert=True)
    for d in devices:
        update = {"kind": d.get("kind", "scanner"), "workstation": d.get("workstation"), "status": d.get("status")}
        if d.get("status") == "ok":
            update["last_seen"] = now
        db.device_health.update_one({"device_id": d["device_id"]}, {"$set": update}, upsert=True)
    return {"ok": True}


def station_status(tenant_openid):
    """EM / PIC workstation grid: what each station runs now, and whether its devices are alive."""
    db = _db()
    running = {w["workstation"]: w for w in db.wip.find({"tenant_openid": tenant_openid, "status": WIP_RUNNING},
                                                         {"_id": 0})}
    out = []
    for ws in list_workstations():
        wip = running.get(ws["code"])
        out.append({**ws, "running": None if wip is None else {
            "wip_id": wip["wip_id"], "batch_id": wip["batch_id"], "started_by": wip["started_by"],
            "started_at": wip["started_at"], "machine_stopped": bool(wip.get("stopped_since")),
            "stop_reason": wip.get("stop_reason")},
            "devices": [d for d in device_health_for(ws["code"]) if d.get("kind") != "gateway"]})
    return out


def device_health_for(workstation_code):
    timeout = int(config.get("network_alarm.timeout_seconds", 10))
    now = _now()
    out = []
    for d in _db().device_health.find({"$or": [{"workstation": workstation_code}, {"kind": "gateway"}]}, {"_id": 0}):
        age = (now - d["last_seen"]).total_seconds() if d.get("last_seen") else None
        d["ok"] = age is not None and age <= timeout and d.get("status") == "ok"
        d["seconds_since_seen"] = None if age is None else int(age)
        out.append(d)
    return out
