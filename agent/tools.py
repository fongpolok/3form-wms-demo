"""
Read-only look-ups the agent may use (scheduled jobs and chat).
Nothing here changes data. Results are compact JSON so prompts stay small;
callers pass them through the Anonymiser before they leave the site.
"""
from datetime import date, datetime, timedelta, timezone

from aps import service as aps
from core import mongo
from inventory import services as inv
from inventory.models import Alert, CountTask, MaterialRequest
from mes import lean


def _iso(v):
    """Times in site-local time with the offset (the AI must not have to convert time zones)."""
    if isinstance(v, datetime):
        from aps.calendar import tz
        return (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).astimezone(tz()).isoformat(timespec="minutes")
    return v.isoformat() if isinstance(v, date) else v


def _stations(step_or_ws):
    """Accept a workstation code (WS-02), a step code (FILL) or a step name (Filling)."""
    from mes.workstations import list_workstations
    if not step_or_ws:
        return None
    v = str(step_or_ws).strip().lower()
    hits = [w["code"] for w in list_workstations()
            if v in (w["code"].lower(), w["step_code"].lower()) or v in {str(n).lower() for n in w["step_name"].values()}]
    return hits or [step_or_ws]


def _clean(obj):
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items() if k not in ("_id", "tenant_openid", "routing", "embedding")}
    if isinstance(obj, list):
        return [_clean(v) for v in obj]
    return _iso(obj)


def list_orders(tenant, status=None):
    q = {"tenant_openid": tenant, "status": {"$in": [status]} if status else {"$ne": "done"}}
    plan = {o["wo_id"]: o for o in (aps.current(tenant) or {}).get("orders", [])}
    out = []
    for w in mongo.db().work_orders.find(q).sort([("special_urgent", -1), ("due_date", 1)]).limit(60):
        p = plan.get(w["wo_id"], {})
        out.append({"wo_id": w["wo_id"], "product_code": w["product_code"], "product_name": w.get("product_name"),
                    "client": w.get("client"), "qty": w["qty"], "due_date": w["due_date"], "status": w["status"],
                    "urgent": w.get("special_urgent", False), "shortages": w.get("shortages", []),
                    "planned_finish": _iso(p.get("planned_finish")), "late_risk": p.get("late_risk")})
    return out


def order_detail(tenant, wo_id):
    db = mongo.db()
    wo = db.work_orders.find_one({"tenant_openid": tenant, "wo_id": wo_id})
    if not wo:
        return {"error": f"{wo_id} not found"}
    batches = list(db.batches.find({"wo_id": wo_id}, {"_id": 0, "batch_id": 1, "qty": 1, "status": 1, "current_step_no": 1,
                                                       "total_steps": 1, "good_qty_out": 1, "materials_used": 1}))
    wips = list(db.wip.find({"wo_id": wo_id}, {"_id": 0, "batch_id": 1, "step_code": 1, "workstation": 1, "qty_in": 1,
                                                "good_qty": 1, "scrap_qty": 1, "downtime_seconds": 1, "status": 1}))
    return _clean({"order": {k: wo.get(k) for k in ("wo_id", "product_code", "product_name", "client", "qty", "due_date",
                                                     "status", "special_urgent", "ship_mode", "shortages")},
                   "batches": batches, "steps": wips})


def production_kpis(tenant, days=30):
    d1 = date.today()
    d0 = d1 - timedelta(days=int(days))
    oee = [{k: r.get(k) for k in ("workstation", "step_code", "oee", "availability", "performance", "quality",
                                    "batches", "downtime_min", "idle_h")} for r in lean.oee(tenant, d0, d1)]
    y = lean.yields(tenant, d0, d1)
    return {"days": days, "oee": oee, "rty": y["rty"], "dpmo": y["dpmo"], "sigma": y["sigma"],
            "fpy": [{"step": s["step_code"], "fpy": s["fpy"]} for s in y["steps"]]}


def scrap_breakdown(tenant, days=7, workstation=None):
    d1 = date.today()
    d0 = d1 - timedelta(days=int(days))
    stations = _stations(workstation)
    par = lean.pareto(tenant, d0, d1, stations)
    start = datetime.now(timezone.utc) - timedelta(days=int(days))
    q = {"tenant_openid": tenant, "type": "scrap", "ts": {"$gte": start}, "note": {"$nin": ["", None]}}
    if stations:
        q["workstation"] = {"$in": stations}
    notes = [e["note"] for e in mongo.db().step_events.find(q, {"note": 1}).sort("ts", -1).limit(10)]
    by_step = {}
    for e in mongo.db().step_events.aggregate([
            {"$match": {"tenant_openid": tenant, "type": "scrap", "ts": {"$gte": start}}},
            {"$group": {"_id": "$step_code", "qty": {"$sum": "$qty"}}}]):
        by_step[e["_id"] or "?"] = e["qty"]
    return {"days": days, "workstations": stations,
            "pareto": [{"reason": p["reason_code"], "qty": p["qty"], "cum_pct": p["cum_pct"]} for p in par],
            "by_step": by_step, "recent_notes": notes}


def scrap_trend(tenant):
    """Scrap % per step: last 7 days vs the 30 days before (rising = DMAIC trigger)."""
    now = datetime.now(timezone.utc)
    out = {}
    for label, a, b in (("last7", now - timedelta(days=7), now), ("prior30", now - timedelta(days=37), now - timedelta(days=7))):
        for r in mongo.db().wip.aggregate([
                {"$match": {"tenant_openid": tenant, "status": "done", "finished_at": {"$gte": a, "$lt": b}}},
                {"$group": {"_id": "$step_code", "in": {"$sum": "$qty_in"}, "scrap": {"$sum": "$scrap_qty"}}}]):
            out.setdefault(r["_id"], {})[label] = round(100.0 * r["scrap"] / r["in"], 2) if r["in"] else None
    return out


def spc_status(tenant, step_code=None):
    s = lean.spc(tenant, step_code)
    if not s:
        return {"note": "no step with a measurement"}
    last = s["points"][-10:] if s.get("points") else []
    return _clean({k: s.get(k) for k in ("step_code", "measure", "unit", "target", "usl", "lsl", "centre", "ucl", "lcl",
                                         "cp", "cpk", "n")} | {"rule_breaks": len(s.get("violations") or []),
                                                               "last_readings": [p["value"] for p in last]})


def stock_status(tenant, goods_code=None):
    rows = inv.stock_summary(tenant)
    if goods_code:
        rows = [r for r in rows if r["goods_code"] == goods_code]
    reqs = list(MaterialRequest.objects.filter(tenant_openid=tenant, status="open")
                .values("wo_id", "goods_code", "qty_short", "needed_by"))
    soon = date.today() + timedelta(days=30)
    return _clean({"items": [{"goods_code": r["goods_code"], "desc": r["goods_desc"], "on_hand": r["on_hand"],
                              "reserved": r["reserved"], "available": r["available"],
                              "expiring_30d": sum(l["qty"] for l in r["lots"] if l["expiry_date"] and l["expiry_date"] <= soon)}
                             for r in rows[:80]], "material_requests": reqs})


def material_outlook(tenant, days=14):
    """Raw material needed by released orders (recipe x qty) vs available."""
    need = {}
    for w in mongo.db().work_orders.find({"tenant_openid": tenant, "status": {"$in": ["released", "waiting_material"]}}):
        for code, q in inv.requirements(tenant, w["product_code"], w["qty"]).items():
            need[code] = need.get(code, 0) + q
    out = []
    for code, q in sorted(need.items()):
        avail = inv.available(tenant, code)
        out.append({"goods_code": code, "needed_by_open_orders": q, "available_unreserved": avail,
                    "on_hand": inv.on_hand(tenant, code)})
    return out


def plan_summary(tenant):
    p = aps.current(tenant)
    if not p:
        return {"note": "no published plan"}
    late = [o for o in p["orders"] if o["late_risk"]]
    load = {}
    for op in p["ops"]:
        load[op["workstation"]] = load.get(op["workstation"], 0) + (op["end"] - op["start"]).total_seconds() / 3600
    return _clean({"plan_id": p["plan_id"], "published_at": p.get("published_at"), "late_orders": late,
                   "blocked_orders": p["blocked"], "planned_hours_by_station": {k: round(v, 1) for k, v in load.items()},
                   "changeover_minutes_total": sum(op.get("setup_minutes", 0) for op in p["ops"])})


def count_variances(tenant, days=30):
    since = datetime.now() - timedelta(days=int(days))
    counts = [{"bin": c.bin_name, "goods_code": c.goods_code, "lot": c.lot_number, "system": c.system_qty,
               "counted": c.counted_qty, "variance": c.counted_qty - c.system_qty, "status": c.status}
              for c in CountTask.objects.filter(tenant_openid=tenant, created_at__gte=since)]
    rack = list(mongo.db().rack_reports.find({"tenant_openid": tenant, "mismatch": True}, {"_id": 0, "bin_name": 1,
                                                                                            "observed": 1, "expected": 1,
                                                                                            "ts": 1}).sort("ts", -1).limit(20))
    return _clean({"counts": [c for c in counts if c["variance"] != 0], "counts_total": len(counts),
                   "rack_mismatches": rack})


def open_alerts(tenant):
    return [{"kind": a.kind, "severity": a.severity, "title": a.title, "detail": a.detail[:200], "ref": a.ref}
            for a in Alert.objects.filter(tenant_openid=tenant, is_open=True)[:30]]


def search_documents(tenant, query):
    from .search import search
    return [{"kind": r["kind"], "title": r["title"], "snippet": r["snippet"], "ref": r.get("ref")}
            for r in search(tenant, query, limit=8)]


# --- tool catalogue for the chat (OpenAI function-calling format) -------------
def _fn(name, desc, props=None, required=None):
    return {"type": "function", "function": {"name": name, "description": desc,
                                             "parameters": {"type": "object", "properties": props or {},
                                                            "required": required or []}}}


TOOLS = {
    "list_orders": (list_orders, _fn("list_orders", "Open work orders with due date, status, shortages and planned finish / late risk.",
                                     {"status": {"type": "string", "enum": ["released", "in_progress", "waiting_material", "done"]}})),
    "order_detail": (order_detail, _fn("order_detail", "One work order: batches, steps, quantities, scrap, materials used.",
                                       {"wo_id": {"type": "string"}}, ["wo_id"])),
    "production_kpis": (production_kpis, _fn("production_kpis", "OEE (A/P/Q) per workstation, rolled yield, DPMO, sigma, FPY.",
                                             {"days": {"type": "integer", "minimum": 1, "maximum": 365}})),
    "scrap_breakdown": (scrap_breakdown, _fn("scrap_breakdown", "Scrap Pareto by reason, scrap by step and recent worker notes.",
                                             {"days": {"type": "integer"}, "workstation": {"type": "string", "description": "workstation code (WS-02), step code (FILL) or step name"}})),
    "scrap_trend": (scrap_trend, _fn("scrap_trend", "Scrap % per step, last 7 days vs the 30 days before.")),
    "spc_status": (spc_status, _fn("spc_status", "SPC control limits, Cp/Cpk and rule breaks for a measured step.",
                                   {"step_code": {"type": "string"}})),
    "stock_status": (stock_status, _fn("stock_status", "Stock on hand / reserved / available, lots expiring in 30 days, open material requests.",
                                       {"goods_code": {"type": "string"}})),
    "material_outlook": (material_outlook, _fn("material_outlook", "Raw material needed by open orders vs available.")),
    "plan_summary": (plan_summary, _fn("plan_summary", "Published APS plan: late-risk orders, blocked orders, hours per station, changeovers.")),
    "count_variances": (count_variances, _fn("count_variances", "Cycle-count differences and rack-camera mismatches.",
                                             {"days": {"type": "integer"}})),
    "open_alerts": (open_alerts, _fn("open_alerts", "Open alerts (shortages, SPC, rack, expiry, plan).")),
    "search_documents": (search_documents, _fn("search_documents", "Keyword search in SOPs, worker notes, work orders and past advice.",
                                               {"query": {"type": "string"}}, ["query"])),
}


def call(tenant, name, args):
    if name not in TOOLS:
        return {"error": f"unknown tool {name}"}
    fn = TOOLS[name][0]
    try:
        return fn(tenant, **(args or {}))
    except TypeError as exc:
        return {"error": f"bad arguments: {exc}"}
