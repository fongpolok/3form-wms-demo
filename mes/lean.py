"""
Lean / Six Sigma figures (DMAIC "Measure" and "Control").

  OEE          = Availability x Performance x Quality, per workstation
                 Availability = run time / (run time + machine-stopped time) while a batch is open
                 Performance  = std seconds per piece x pieces processed / run time  (capped at 100 %)
                 Quality      = good / (good + scrap)
  FPY          = good out / pieces in, per step;  RTY = product of step FPYs
  Pareto       = scrap pieces by reason, biggest first, with cumulative %
  DPMO / sigma = scrap pieces per million opportunities (lean.opportunities_per_unit),
                 sigma level = Z(1 - DPMO/1e6) + 1.5 (conventional 1.5 shift)
  SPC (I-MR)   = centre = mean; sigma_hat = MRbar / 1.128; limits = mean +/- 3 sigma_hat
                 rules: 1 point beyond a limit; 8 in a row on one side of the centre
                 Cp / Cpk against target +/- mes.measurement_tolerance_pct

Planned time = shift time minus breaks and holidays (APS calendar). Time in a
shift with no batch open is reported as "idle (no orders)" and is not counted
against Availability, so a quiet day does not look like poor machine performance.
"""
import logging
from collections import defaultdict
from datetime import datetime, time, timezone
from statistics import NormalDist, mean
from zoneinfo import ZoneInfo

from core import config, mongo
from inventory import alerts
from inventory.models import Alert

from .workstations import list_workstations, routing

logger = logging.getLogger("app")


def _range(date_from, date_to):
    tz = ZoneInfo(config.get("site.timezone", "Asia/Hong_Kong"))
    return (datetime.combine(date_from, time.min, tzinfo=tz).astimezone(timezone.utc),
            datetime.combine(date_to, time.max, tzinfo=tz).astimezone(timezone.utc))


def _pct(x):
    return None if x is None else round(100.0 * x, 1)


def oee(tenant, date_from, date_to):
    start, end = _range(date_from, date_to)
    std = {s["code"]: float(s.get("std_seconds_per_unit") or 0) for s in routing()}
    rows = defaultdict(lambda: {"open_s": 0.0, "down_s": 0.0, "good": 0, "scrap": 0, "std_work_s": 0.0, "batches": 0})
    for w in mongo.db().wip.find({"tenant_openid": tenant, "status": "done", "finished_at": {"$gte": start, "$lte": end}},
                                 {"_id": 0}):
        r = rows[w["workstation"]]
        open_s = (w["finished_at"] - w["started_at"]).total_seconds()
        r["open_s"] += open_s
        r["down_s"] += min(w.get("downtime_seconds", 0), open_s)
        r["good"] += w.get("good_qty") or 0
        r["scrap"] += w.get("scrap_qty") or 0
        r["std_work_s"] += std.get(w["step_code"], 0) * ((w.get("good_qty") or 0) + (w.get("scrap_qty") or 0))
        r["batches"] += 1
    from aps.calendar import planned_minutes
    planned_s = planned_minutes(date_from, date_to) * 60.0      # shift time minus breaks and holidays
    out = []
    for ws in list_workstations():
        r = rows.get(ws["code"])
        if not r or r["open_s"] <= 0:
            out.append({"workstation": ws["code"], "step_code": ws["step_code"], "step_name": ws["step_name"],
                        "oee": None, "availability": None, "performance": None, "quality": None, "batches": 0,
                        "planned_h": round(planned_s / 3600, 1), "idle_h": round(planned_s / 3600, 1)})
            continue
        run = max(r["open_s"] - r["down_s"], 1.0)
        a = run / r["open_s"]
        p = min(r["std_work_s"] / run, 1.0)
        processed = r["good"] + r["scrap"]
        q = r["good"] / processed if processed else None
        out.append({"workstation": ws["code"], "step_code": ws["step_code"], "step_name": ws["step_name"],
                    "availability": _pct(a), "performance": _pct(p), "quality": _pct(q),
                    "oee": _pct(a * p * q) if q is not None else None, "batches": r["batches"],
                    "good": r["good"], "scrap": r["scrap"], "downtime_min": round(r["down_s"] / 60, 1),
                    # Idle = planned shift time with no batch open (no orders): shown, not counted against OEE.
                    "planned_h": round(planned_s / 3600, 1),
                    "idle_h": round(max(planned_s - r["open_s"], 0) / 3600, 1),
                    "utilisation": _pct(min(r["open_s"] / planned_s, 1.0)) if planned_s else None})
    return out


def yields(tenant, date_from, date_to):
    start, end = _range(date_from, date_to)
    agg = defaultdict(lambda: {"in": 0, "good": 0})
    for w in mongo.db().wip.find({"tenant_openid": tenant, "status": "done", "finished_at": {"$gte": start, "$lte": end}},
                                 {"step_code": 1, "qty_in": 1, "good_qty": 1}):
        agg[w["step_code"]]["in"] += w.get("qty_in") or 0
        agg[w["step_code"]]["good"] += w.get("good_qty") or 0
    steps, rty = [], 1.0
    for s in routing():
        a = agg.get(s["code"])
        fpy = (a["good"] / a["in"]) if a and a["in"] else None
        if fpy is not None:
            rty *= fpy
        steps.append({"step_code": s["code"], "step_name": s["name"], "fpy": _pct(fpy),
                      "qty_in": a["in"] if a else 0, "good": a["good"] if a else 0})
    total_in = sum(a["in"] for a in agg.values())
    defects = sum(a["in"] - a["good"] for a in agg.values())
    opp = float(config.get("lean.opportunities_per_unit", 1))
    dpmo = (defects / (total_in * opp) * 1e6) if total_in else None
    sigma = None
    if dpmo is not None and 0 < dpmo < 1e6:
        sigma = round(NormalDist().inv_cdf(1 - dpmo / 1e6) + 1.5, 2)
    elif dpmo == 0 and total_in:
        sigma = 6.0
    return {"steps": steps, "rty": _pct(rty) if agg else None, "dpmo": round(dpmo) if dpmo is not None else None,
            "sigma": sigma, "units": total_in, "defects": defects}


def pareto(tenant, date_from, date_to, workstation=None):
    start, end = _range(date_from, date_to)
    match = {"tenant_openid": tenant, "type": "scrap", "ts": {"$gte": start, "$lte": end}}
    if workstation:
        match["workstation"] = workstation
    rows = list(mongo.db().step_events.aggregate([
        {"$match": match}, {"$group": {"_id": "$reason_code", "qty": {"$sum": "$qty"}, "events": {"$sum": 1}}},
        {"$sort": {"qty": -1}}]))
    total = sum(r["qty"] for r in rows) or 1
    names = {r["code"]: r for r in config.industry()["scrap_reasons"]}
    out, cum = [], 0
    for r in rows:
        cum += r["qty"]
        out.append({"reason_code": r["_id"], "label": names.get(r["_id"], {"en": r["_id"]}),
                    "qty": r["qty"], "events": r["events"], "cum_pct": round(100.0 * cum / total, 1)})
    return out


def _imr(values):
    mu = mean(values)
    mrs = [abs(b - a) for a, b in zip(values, values[1:])]
    mr_bar = mean(mrs) if mrs else 0.0
    sigma = mr_bar / 1.128 if mr_bar else 0.0
    return mu, sigma


def spc(tenant, step_code=None, points=None):
    """I-MR chart data for the step's measurement (default: first step that has one)."""
    steps = [s for s in routing() if s.get("measurement")]
    if not steps:
        return None
    step = next((s for s in steps if s["code"] == step_code), steps[0])
    m = step["measurement"]
    n = int(points or config.get("spc.points", 50))
    docs = list(mongo.db().step_events.find({"tenant_openid": tenant, "type": "measure", "step_code": step["code"]},
                                            {"_id": 0, "value": 1, "ts": 1, "batch_id": 1, "workstation": 1})
                .sort("ts", -1).limit(n))
    if not docs:   # older events (Phase 1) did not store step_code; fall back to the workstation
        ws = [w["code"] for w in list_workstations() if w["step_code"] == step["code"]]
        docs = list(mongo.db().step_events.find({"tenant_openid": tenant, "type": "measure", "workstation": {"$in": ws}},
                                                {"_id": 0, "value": 1, "ts": 1, "batch_id": 1, "workstation": 1})
                    .sort("ts", -1).limit(n))
    docs.reverse()
    values = [d["value"] for d in docs]
    tol = float(config.get("mes.measurement_tolerance_pct", 5)) / 100.0
    target = m.get("target")
    usl = target * (1 + tol) if target is not None else None
    lsl = target * (1 - tol) if target is not None else None
    result = {"step_code": step["code"], "step_name": step["name"], "measure": m["name"], "unit": m["unit"],
              "target": target, "usl": usl, "lsl": lsl, "points": docs, "n": len(values)}
    if len(values) < int(config.get("spc.min_points", 20)):
        result.update({"centre": mean(values) if values else None, "ucl": None, "lcl": None, "cp": None, "cpk": None,
                       "note": "Not enough readings yet for control limits."})
        return result
    mu, sigma = _imr(values)
    result.update({"centre": round(mu, 3), "ucl": round(mu + 3 * sigma, 3), "lcl": round(mu - 3 * sigma, 3),
                   "sigma": round(sigma, 4)})
    if sigma and usl is not None:
        result["cp"] = round((usl - lsl) / (6 * sigma), 2)
        result["cpk"] = round(min(usl - mu, mu - lsl) / (3 * sigma), 2)
    else:
        result["cp"] = result["cpk"] = None
    result["violations"] = violations(values, mu, sigma)
    return result


def violations(values, mu, sigma, run=8):
    out = []
    for i, v in enumerate(values):
        if sigma and abs(v - mu) > 3 * sigma:
            out.append({"index": i, "rule": "beyond_3_sigma"})
    side, streak = 0, 0
    for i, v in enumerate(values):
        s = 1 if v > mu else -1 if v < mu else 0
        streak = streak + 1 if s == side and s != 0 else 1
        side = s
        if streak == run:
            out.append({"index": i, "rule": f"{run}_on_one_side"})
    return out


def check_new_measurement(tenant, step_code):
    """Called after each reading: raise an SPC alarm if the newest point breaks a rule."""
    data = spc(tenant, step_code)
    if not data or data.get("ucl") is None:
        return None
    last = len(data["points"]) - 1
    hits = [v for v in data.get("violations", []) if v["index"] == last]
    if hits:
        p = data["points"][last]
        alerts.raise_alert(tenant, Alert.SPC, f"SPC alarm: {data['measure']} at {step_code}",
                           f"Reading {p['value']}{data['unit']} (batch {p.get('batch_id')}) broke rule "
                           f"{hits[0]['rule']}. Limits {data['lcl']}–{data['ucl']}.",
                           ref=p.get("batch_id", ""), severity="alarm", dedupe_key=f"spc:{step_code}")
    return hits
