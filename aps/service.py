"""
APS service: collect open work from MES, run the engine, store plans.

Plan lifecycle (MongoDB `plans`):
    draft      -> EM / PIC accepts -> published  (previous published -> superseded)
               -> EM / PIC rejects -> rejected
    Special / Urgent orders publish immediately (status published, auto=True) and
    alert the EM with the orders that were pushed later.
Only one draft is open at a time; a newer draft supersedes the older one.
"""
import logging
import math
import time
import uuid
from datetime import datetime, timedelta, timezone

from accounts import audit
from core import config, mongo
from inventory import alerts
from mes.workstations import list_workstations, routing
from optimiser import plan_milp
from optimiser import service as optimiser
from optimiser.cuopt import CuoptUnavailable

from . import calendar as cal
from . import rules as aps_rules
from .engine import Fixed, Job, schedule

logger = logging.getLogger("aps")
DRAFT, PUBLISHED, REJECTED, SUPERSEDED = "draft", "published", "rejected", "superseded"
PLAN_DRAFT, PLAN_CHANGED = "PLAN_DRAFT", "PLAN_CHANGED"   # alert kinds


def _now():
    return datetime.now(timezone.utc)


def _std_minutes():
    return {s["code"]: float(s.get("std_seconds_per_unit") or 0) / 60.0 for s in routing()}


def _aware(dt):
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def collect(tenant, now, published=None):
    """Open work -> (jobs, fixed, blocked orders)."""
    db = mongo.db()
    std = _std_minutes()
    slot = int(config.get("aps.slot_minutes", 5))
    frozen_until = now + timedelta(hours=float(config.get("aps.frozen_hours", 4)))
    wos = {w["wo_id"]: w for w in db.work_orders.find({"tenant_openid": tenant,
                                                         "status": {"$in": ["released", "in_progress",
                                                                            "waiting_material"]}})}
    blocked = [{"wo_id": w["wo_id"], "product_code": w["product_code"], "due_date": w["due_date"],
                "shortages": w.get("shortages", [])} for w in wos.values() if w["status"] == "waiting_material"]
    running = {w["batch_id"]: w for w in db.wip.find({"tenant_openid": tenant, "status": "running"})}
    frozen_ops = {}
    if published:
        for op in published.get("ops", []):
            start, end = _aware(op["start"]), _aware(op["end"])
            if op.get("kind") == "planned" and start < frozen_until and end > now:   # not finished, starts soon
                frozen_ops.setdefault(op["batch_id"], []).append(op)
    jobs, fixed = [], []
    for b in db.batches.find({"wo_id": {"$in": list(wos)}, "status": {"$in": ["waiting", "running"]}}):
        wo = wos[b["wo_id"]]
        if wo["status"] == "waiting_material":
            continue
        routing_steps = wo["routing"]
        qty = b.get("last_good_qty") or b["qty"]
        current = b["current_step_no"]
        ready_after = None
        remaining = routing_steps[current - 1:]
        if b["status"] == "running" and b["batch_id"] in running:
            w = running[b["batch_id"]]
            started = _aware(w["started_at"])
            work = timedelta(minutes=std.get(w["step_code"], 0) * w["qty_in"])
            est_end = max(started + work + timedelta(seconds=w.get("downtime_seconds", 0)), now + timedelta(minutes=slot))
            if w.get("stopped_since"):
                est_end += now - _aware(w["stopped_since"])
            fixed.append(Fixed(w["workstation"], b["batch_id"], b["wo_id"], wo["product_code"], current,
                               w["step_code"], started, est_end, "running"))
            ready_after = est_end
            remaining = routing_steps[current:]
        else:
            # Keep the published op for the batch's next step if it starts inside the frozen window.
            fz = [op for op in frozen_ops.get(b["batch_id"], []) if op["step_no"] == current]
            if fz:
                op = fz[0]
                fixed.append(Fixed(op["workstation"], b["batch_id"], b["wo_id"], wo["product_code"], current,
                                   op["step_code"], _aware(op["start"]), _aware(op["end"]), "frozen"))
                ready_after = _aware(op["end"])
                remaining = routing_steps[current:]
        steps = [{"step_no": s["step_no"], "step_code": s["code"], "minutes": std.get(s["code"], 0) * qty}
                 for s in remaining]
        if steps:
            jobs.append(Job(b["batch_id"], b["wo_id"], wo["product_code"], bool(wo.get("special_urgent")),
                            wo["due_date"], int(wo.get("client_priority", 3)), str(wo.get("created_at")), steps,
                            ready_after))
    return wos, jobs, fixed, blocked


def compute(tenant, reason="manual", actor="system", now=None, engine_name=None):
    now = now or _now()
    db = mongo.db()
    published = db.plans.find_one({"tenant_openid": tenant, "status": PUBLISHED}, sort=[("published_at", -1)])
    wos, jobs, fixed, blocked = collect(tenant, now, published)
    slot = int(config.get("aps.slot_minutes", 5))
    slots = cal.build(now)
    stations = {w["code"]: w["step_code"] for w in list_workstations()}
    buffer = timedelta(hours=float(config.get("aps.late_buffer_hours", 4)))
    engine = optimiser.settings_for(tenant)
    if engine_name:                      # comparison: run this engine regardless of the setting
        engine["plan_engine"] = engine_name
    args = (slots, stations, jobs, fixed, slot, float(config.get("aps.changeover_minutes", 20)),
            int(config.get("aps.workers_per_station", 1)))
    rules = aps_rules.editable()
    started = time.perf_counter()
    if engine["plan_engine"] == "cuopt":
        t0 = slots[0].start if slots else now

        def due_slot(job):   # target finish = end of due date minus the late buffer, as a slot index
            target = cal.day_end(cal.parse_date(job.due_date)) - buffer
            return max(0, math.floor((target - t0).total_seconds() / 60 / slot))
        res = plan_milp.schedule(*args, due_slot=due_slot, url=engine["cuopt_url"], token=engine["cuopt_token"],
                                 changeover_cost=float(rules["changeover_cost_minutes"]))
    else:
        res = schedule(*args, group_days=int(rules["group_same_product_days"]))
    stats = {"seconds": round(time.perf_counter() - started, 3), "orders": len({j.wo_id for j in jobs}),
             "batches": len(jobs), "steps": sum(len(j.steps) for j in jobs), "workstations": len(stations), **res.stats}
    finish = {}
    for op in res.ops:
        finish[op["wo_id"]] = max(finish.get(op["wo_id"], op["end"]), op["end"])
    unscheduled_wos = {u["wo_id"] for u in res.unscheduled}
    orders = []
    for wo_id, wo in wos.items():
        if wo["status"] == "waiting_material":
            continue
        due = cal.day_end(cal.parse_date(wo["due_date"]))
        f = finish.get(wo_id)
        late = wo_id in unscheduled_wos or (f is not None and f > due - buffer)
        orders.append({"wo_id": wo_id, "product_code": wo["product_code"], "product_name": wo.get("product_name", ""),
                       "client": wo.get("client", ""), "due_date": wo["due_date"],
                       "urgent": bool(wo.get("special_urgent")), "planned_finish": f,
                       "late_risk": late, "beyond_horizon": wo_id in unscheduled_wos,
                       "slack_hours": None if f is None else round((due - f).total_seconds() / 3600, 1)})
    orders.sort(key=lambda o: (not o["late_risk"], o["planned_finish"] or now))
    plan = {"plan_id": f"PLAN-{now.astimezone(cal.tz()):%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:4].upper()}",
            "tenant_openid": tenant, "status": DRAFT, "created_at": now, "created_by": actor, "reason": reason,
            "horizon_start": slots[0].start if slots else now, "horizon_days": int(config.get("aps.horizon_days", 14)),
            "frozen_until": now + timedelta(hours=float(config.get("aps.frozen_hours", 4))),
            "engine": engine["plan_engine"], "engine_stats": stats, "ops": res.ops, "orders": orders, "blocked": blocked, "unscheduled": res.unscheduled,
            "stations": [{"code": c, "step_code": s} for c, s in stations.items()],
            "working": working_windows(slots, slot)}
    plan["diff"] = diff(published, plan)
    logger.info("Plan %s computed (%s): %d ops, %d late, %d blocked", plan["plan_id"], reason, len(res.ops),
                sum(o["late_risk"] for o in orders), len(blocked))
    return plan


def summary(plan):
    """Headline numbers for comparing two plans of the same moment."""
    planned = [o for o in plan["ops"] if o["kind"] == "planned"]
    setups = [o for o in planned if o.get("setup_minutes")]
    return {"engine": plan["engine"], "late_orders": sum(o["late_risk"] for o in plan["orders"]),
            "hours_late": round(sum(max(0.0, -(o["slack_hours"] or 0)) for o in plan["orders"]), 1),
            "changeovers": len(setups), "changeover_minutes": sum(o["setup_minutes"] for o in setups),
            "all_done_by": max((o["end"] for o in plan["ops"]), default=None),
            "unscheduled": len(plan["unscheduled"]), "size": plan.get("engine_stats", {})}


def compare(tenant, now=None):
    """Plan the same open work with both engines (nothing is saved). Raises CuoptUnavailable if cuOpt is down."""
    now = now or _now()
    plans = {e: compute(tenant, "comparison", now=now, engine_name=e) for e in ("builtin", "cuopt")}
    a, b = plans["builtin"], plans["cuopt"]
    fa = {o["wo_id"]: o for o in a["orders"]}
    orders = []
    for o in b["orders"]:
        old = fa.get(o["wo_id"])
        if not old or not old["planned_finish"] or not o["planned_finish"]:
            continue
        delta = round((o["planned_finish"] - old["planned_finish"]).total_seconds() / 3600, 1)
        if abs(delta) >= 0.1:
            orders.append({"wo_id": o["wo_id"], "product_name": o["product_name"] or o["product_code"],
                           "client": o["client"], "due_date": o["due_date"], "urgent": o["urgent"],
                           "builtin_finish": old["planned_finish"], "cuopt_finish": o["planned_finish"],
                           "delta_hours": delta, "builtin_late": old["late_risk"], "cuopt_late": o["late_risk"]})
    orders.sort(key=lambda o: o["delta_hours"])
    # Every order, for the chart: when each engine finishes it, and its target (due date minus the late buffer).
    buffer = timedelta(hours=float(config.get("aps.late_buffer_hours", 4)))
    chart = []
    for o in b["orders"]:
        old = fa.get(o["wo_id"])
        if old:
            chart.append({"wo_id": o["wo_id"], "product_name": o["product_name"] or o["product_code"],
                          "urgent": o["urgent"], "due_date": o["due_date"],
                          "target": cal.day_end(cal.parse_date(o["due_date"])) - buffer,
                          "builtin_finish": old["planned_finish"], "cuopt_finish": o["planned_finish"],
                          "builtin_late": old["late_risk"], "cuopt_late": o["late_risk"]})
    chart.sort(key=lambda o: (o["due_date"], o["wo_id"]))
    return {"computed_at": now, "builtin": summary(a), "cuopt": summary(b), "orders": orders, "chart": chart}


def working_windows(slots, slot_minutes):
    """Merge working slots into [{start, end, shift}] windows (for shading the Gantt chart)."""
    out = []
    for sl in slots:
        if not sl.working:
            continue
        end = sl.start + timedelta(minutes=slot_minutes)
        if out and out[-1]["end"] == sl.start and out[-1]["shift"] == sl.shift:
            out[-1]["end"] = end
        else:
            out.append({"start": sl.start, "end": end, "shift": sl.shift, "workers": sl.workers})
    return out


def diff(old, new):
    """Per order: finish before -> after; ops that moved workstation or by more than 15 minutes."""
    if not old:
        return {"orders": [], "moved_ops": 0, "first_plan": True}
    old_finish = {o["wo_id"]: _aware(o.get("planned_finish")) for o in old.get("orders", [])}
    out = []
    for o in new["orders"]:
        before, after = old_finish.get(o["wo_id"]), o["planned_finish"]
        if before is None and after is not None:
            out.append({"wo_id": o["wo_id"], "change": "new", "before": None, "after": after, "delta_hours": None})
        elif before and after and abs((after - before).total_seconds()) > 15 * 60:
            out.append({"wo_id": o["wo_id"], "change": "later" if after > before else "earlier", "before": before,
                        "after": after, "delta_hours": round((after - before).total_seconds() / 3600, 1)})
    old_ops = {(op["batch_id"], op["step_no"]): op for op in old.get("ops", [])}
    moved = 0
    for op in new["ops"]:
        prev = old_ops.get((op["batch_id"], op["step_no"]))
        if prev and (prev["workstation"] != op["workstation"]
                     or abs((_aware(prev["start"]) - op["start"]).total_seconds()) > 15 * 60):
            moved += 1
    return {"orders": out, "moved_ops": moved, "first_plan": False}


def _store(plan):
    db = mongo.db()
    db.plans.update_many({"tenant_openid": plan["tenant_openid"], "status": DRAFT}, {"$set": {"status": SUPERSEDED}})
    db.plans.insert_one(dict(plan))
    return plan


def _publish(tenant, plan_id, by):
    db = mongo.db()
    now = _now()
    db.plans.update_many({"tenant_openid": tenant, "status": PUBLISHED}, {"$set": {"status": SUPERSEDED}})
    db.plans.update_one({"plan_id": plan_id}, {"$set": {"status": PUBLISHED, "published_at": now, "published_by": by}})
    alerts.close_alerts(tenant, "plan:draft", by=by)


def request_replan(tenant, reason, actor="system", urgent=False):
    """Make a new plan. Urgent: publish now and tell the EM what moved. Otherwise: draft for approval.
    If the chosen optimiser (cuOpt) cannot answer: red alert, NO new plan, the published plan stays."""
    try:
        plan = compute(tenant, reason, actor)
    except CuoptUnavailable as exc:
        optimiser.raise_unavailable(tenant, "production plan", exc)
        raise
    if plan.get("engine") == "cuopt":
        optimiser.close_unavailable(tenant, "production plan")
    _store(plan)
    if urgent:
        _publish(tenant, plan["plan_id"], f"auto (urgent: {reason})")
        later = [d for d in plan["diff"]["orders"] if d["change"] == "later"]
        alerts.raise_alert(tenant, PLAN_CHANGED, f"Urgent re-plan published ({reason})",
                           ("Pushed later: " + ", ".join(f"{d['wo_id']} +{d['delta_hours']} h" for d in later))
                           if later else "No other order was delayed.", ref=plan["plan_id"],
                           severity="warn" if later else "info", dedupe_key=f"plan:urgent:{plan['plan_id']}")
    else:
        alerts.close_alerts(tenant, "plan:draft")   # one notice for the newest draft only
        alerts.raise_alert(tenant, PLAN_DRAFT, "New draft plan waiting for approval", f"Reason: {reason}",
                           ref=plan["plan_id"], severity="info", dedupe_key="plan:draft")
    return plan


def decide(account, plan_id, accept, request=None):
    db = mongo.db()
    plan = db.plans.find_one({"plan_id": plan_id, "tenant_openid": account.tenant_openid})
    if plan is None or plan["status"] != DRAFT:
        raise ValueError("Only an open draft plan can be accepted or rejected.")
    if accept:
        _publish(account.tenant_openid, plan_id, account.display_name)
    else:
        db.plans.update_one({"plan_id": plan_id}, {"$set": {"status": REJECTED, "rejected_by": account.display_name,
                                                            "rejected_at": _now()}})
        alerts.close_alerts(account.tenant_openid, "plan:draft", by=account.display_name)
    audit.record(account, "plan.accept" if accept else "plan.reject", "plan", plan_id,
                 after={"late_orders": [o["wo_id"] for o in plan["orders"] if o["late_risk"]],
                        "moved_ops": plan["diff"]["moved_ops"]}, request=request)
    return db.plans.find_one({"plan_id": plan_id}, {"_id": 0})


def current(tenant, status=PUBLISHED):
    return mongo.db().plans.find_one({"tenant_openid": tenant, "status": status}, {"_id": 0},
                                     sort=[("created_at", -1)])


def planned_queue(tenant, workstation):
    """batch_id -> planned start at this workstation, from the published plan."""
    plan = current(tenant)
    if not plan:
        return {}
    return {op["batch_id"]: op["start"] for op in plan["ops"] if op["workstation"] == workstation
            and op["kind"] in ("planned", "frozen")}
