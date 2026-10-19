"""
The agent's four scheduled jobs (hourly, on request, and after alarms):

  work_orders   materials needed vs available, expected finish vs due date
  progress      late-risk orders, slow stations, scrap rising (DMAIC: Pareto + SOP hint)
  stock_take    cycle-count differences and rack-camera mismatches
  inventory     raw material running short for open orders, lots expiring unused

Each job FIRST computes findings with plain arithmetic (numbers are always right
and the job works with no AI). If an AI provider is available, the anonymised
findings are sent once per job and the AI writes the advice text (EN + 繁中);
real names are restored locally. Advice is advisory only: Accept / Reject is recorded.
"""
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone

from core import config, mongo

from . import llm, tools
from .anonymise import Anonymiser

logger = logging.getLogger("agent")
OPEN, ACCEPTED, REJECTED, EXPIRED = "open", "accepted", "rejected", "expired"
JOBS = ("work_orders", "progress", "stock_take", "inventory")


def _when(iso):
    """'2026-10-20T21:10+08:00' -> '20 Oct 21:10' for advice text."""
    try:
        return datetime.fromisoformat(iso).strftime("%d %b %H:%M")
    except (TypeError, ValueError):
        return iso or "-"


def _f(key, severity, title_en, title_zh, text_en, text_zh, suggest_en, suggest_zh, facts):
    return {"key": key, "severity": severity, "title": title_en, "title_zh": title_zh, "finding": text_en,
            "finding_zh": text_zh, "suggestion": suggest_en, "suggestion_zh": suggest_zh, "facts": facts}


# ------------------------------------------------------------------ findings
def find_work_orders(t):
    out = []
    for o in tools.list_orders(t):
        if o["status"] == "waiting_material":
            short = ", ".join(f"{s['goods_code']} −{s['short']}" for s in o["shortages"])
            out.append(_f(f"wo-short:{o['wo_id']}", "warn", f"{o['wo_id']} cannot start: material short",
                          f"{o['wo_id']} 物料不足,未能開始",
                          f"{o['product_name']} × {o['qty']} for {o['client']}, due {o['due_date']}. Short: {short}.",
                          f"{o['product_name']} × {o['qty']}({o['client']}),到期 {o['due_date']}。短缺:{short}。",
                          "Raise a purchase for the short items, or agree a new due date with the client.",
                          "為短缺物料落單採購,或與客戶協商新到期日。", o))
        elif o.get("late_risk"):
            out.append(_f(f"wo-late:{o['wo_id']}", "alarm", f"{o['wo_id']} is at risk of being late",
                          f"{o['wo_id']} 可能延誤",
                          f"Planned finish {_when(o['planned_finish'])} vs due {o['due_date']} (end of day).",
                          f"預計完成 {_when(o['planned_finish'])},到期 {o['due_date']}(當日結束前)。",
                          "Consider an extra shift, splitting the order, or moving a later-due order behind it.",
                          "可考慮加開班次、分拆工單,或將較遲到期的工單排後。", o))
    return out


def find_progress(t):
    out = []
    trend = tools.scrap_trend(t)
    for step, v in trend.items():
        a, b = v.get("last7"), v.get("prior30")
        if a is not None and b and a > b * 1.3 and a - b > 0.3:
            br = tools.scrap_breakdown(t, 7)
            top = br["pareto"][0]["reason"] if br["pareto"] else "-"
            sop = tools.search_documents(t, f"{step} {top}")[:2]
            out.append(_f(f"scrap-up:{step}", "warn", f"Scrap rising at {step}: {a}% vs {b}%",
                          f"{step} 報廢上升:{a}% 對比 {b}%",
                          f"Last 7 days {a}% scrap at {step} vs {b}% in the 30 days before. Top reason this week: {top}.",
                          f"{step} 最近 7 日報廢率 {a}%,之前 30 日為 {b}%。本週主要原因:{top}。",
                          "DMAIC: check the top reason first (5-Whys at the line), compare with the SOP, then watch the SPC chart.",
                          "DMAIC:先處理主要原因(在產線做 5 個為甚麼),對照 SOP,再監察 SPC 圖。",
                          {"step": step, "last7_pct": a, "prior30_pct": b, "pareto": br["pareto"][:5], "sop_hits": sop}))
    k = tools.production_kpis(t, 7)
    for r in k["oee"]:
        if r["availability"] is not None and r["availability"] < 85 and r["batches"] >= 3:
            out.append(_f(f"avail:{r['workstation']}", "warn", f"{r['workstation']} losing time to stops ({r['availability']}% availability)",
                          f"{r['workstation']} 停機時間偏多(可用率 {r['availability']}%)",
                          f"{r['downtime_min']} min stopped over {r['batches']} batches in 7 days.",
                          f"7 日內 {r['batches']} 個批次共停機 {r['downtime_min']} 分鐘。",
                          "Look at the stop reasons for this station; changeovers can often be shortened (SMED).",
                          "查看此工作站的停機原因;轉換時間通常可縮短(SMED)。", r))
    spc = tools.spc_status(t)
    if spc.get("cpk") is not None and spc["cpk"] < 1.33:
        out.append(_f(f"cpk:{spc['step_code']}", "warn" if spc["cpk"] >= 1 else "alarm",
                      f"{spc['measure']} capability low (Cpk {spc['cpk']})", f"{spc['measure']} 製程能力偏低(Cpk {spc['cpk']})",
                      f"Mean {spc['centre']}{spc['unit']} vs target {spc['target']}, {spc['rule_breaks']} rule break(s) in the last {spc['n']} readings.",
                      f"平均 {spc['centre']}{spc['unit']},目標 {spc['target']},最近 {spc['n']} 個讀數有 {spc['rule_breaks']} 次違規。",
                      "Re-centre the process on target and reduce spread (calibration, nozzle wear) before Cpk reaches 1.33.",
                      "將製程調回目標並減少波動(校準、噴嘴磨損),令 Cpk 達到 1.33。", spc))
    return out


def find_stock_take(t):
    out = []
    v = tools.count_variances(t)
    for c in v["counts"]:
        out.append(_f(f"count:{c['bin']}:{c['goods_code']}:{c['lot']}", "warn" if c["status"] == "pending" else "info",
                      f"Count difference {c['variance']:+} for {c['goods_code']} in {c['bin']}",
                      f"{c['bin']} 的 {c['goods_code']} 盤點差異 {c['variance']:+}",
                      f"System {c['system']}, counted {c['counted']} (status {c['status']}).",
                      f"系統 {c['system']},點算 {c['counted']}(狀態 {c['status']})。",
                      "Check recent issues / put-aways for this lot; a recount before approving avoids double corrections.",
                      "檢查此批號最近的發料 / 上架記錄;批准前重點一次可避免重複更正。", c))
    for r in v["rack_mismatches"][:5]:
        out.append(_f(f"rack:{r['bin_name']}", "warn", f"Rack camera disagrees with stock at {r['bin_name']}",
                      f"貨架鏡頭與 {r['bin_name']} 的庫存不符",
                      f"Camera saw {r['observed']}; system expects {', '.join(r['expected']) or 'empty'}.",
                      f"鏡頭見到 {r['observed']};系統記錄為 {', '.join(r['expected']) or '空置'}。",
                      "Send someone to look and run a cycle count on this bin.", "派人查看並為此貨位做循環盤點。", r))
    return out


def find_inventory(t):
    out = []
    for m in tools.material_outlook(t):
        if m["available_unreserved"] < 0 or m["needed_by_open_orders"] > m["on_hand"]:
            gap = m["needed_by_open_orders"] - m["on_hand"]
            out.append(_f(f"mat:{m['goods_code']}", "warn", f"{m['goods_code']}: open orders need more than is in stock",
                          f"{m['goods_code']}:未完成工單所需多於庫存",
                          f"Needed {m['needed_by_open_orders']}, on hand {m['on_hand']} (gap {gap}).",
                          f"需要 {m['needed_by_open_orders']},現有 {m['on_hand']}(差 {gap})。",
                          f"Order at least {gap} plus your safety stock.", f"至少訂購 {gap},另加安全庫存。", m))
    for it in tools.stock_status(t)["items"]:
        if it["expiring_30d"] and it["expiring_30d"] > 0.2 * max(it["on_hand"], 1):
            out.append(_f(f"exp:{it['goods_code']}", "info", f"{it['goods_code']}: {it['expiring_30d']} expire within 30 days",
                          f"{it['goods_code']}:{it['expiring_30d']} 將於 30 日內到期",
                          f"{it['expiring_30d']} of {it['on_hand']} on hand expire within 30 days.",
                          f"現有 {it['on_hand']} 中有 {it['expiring_30d']} 將於 30 日內到期。",
                          "Plan these lots first (FEFO already prefers them) or stop re-ordering until used.",
                          "優先安排使用這些批號(FEFO 已優先揀選),或暫停補貨。", it))
    return out


FINDERS = {"work_orders": find_work_orders, "progress": find_progress, "stock_take": find_stock_take,
           "inventory": find_inventory}

SYSTEM_PROMPT = (
    "You are the advisory assistant of a factory MES/WMS. You never change data; people decide. "
    "Rewrite each finding as short, practical advice for an engineering manager. Keep every number exactly as given. "
    "Use Lean / Six Sigma language where it helps (DMAIC, Pareto, 5-Whys, SMED, Cpk). Names like 'Client A' or "
    "'Worker 3' are placeholders: keep them unchanged. Answer ONLY with JSON: "
    '{"items":[{"key":"...","title":"...","finding":"...","suggestion":"...",'
    '"title_zh":"...","finding_zh":"...","suggestion_zh":"..."}]} (zh = Traditional Chinese, Hong Kong).')


def _enrich(t, job, findings):
    """One AI call per job. Falls back to the plain text on any problem."""
    if not findings:
        return findings, "rules", None
    ok, why = llm.available(t)
    if not ok:
        return findings, "rules", why
    anon = Anonymiser(t)
    payload = [anon.apply({"key": f["key"], "severity": f["severity"], "title": f["title"], "finding": f["finding"],
                           "suggestion": f["suggestion"], "facts": f["facts"]}) for f in findings]
    try:
        out = llm.chat(t, [{"role": "system", "content": SYSTEM_PROMPT},
                           {"role": "user", "content": json.dumps({"job": job, "findings": payload}, default=str)}],
                       max_tokens=int(config.get("agent.job_max_tokens", 1200)), purpose=f"job:{job}", response_json=True)
        items = {i["key"]: i for i in json.loads(out["content"]).get("items", []) if "key" in i}
    except (llm.LlmUnavailable, ValueError, KeyError, TypeError) as exc:
        logger.warning("AI wording for %s failed, using plain text: %s", job, exc)
        return findings, "rules", str(exc)
    merged = []
    for f in findings:
        ai = items.get(f["key"])
        if ai:
            f = {**f, **{k: anon.restore(ai[k]) for k in ("title", "finding", "suggestion", "title_zh", "finding_zh",
                                                          "suggestion_zh") if ai.get(k)}}
        merged.append(f)
    return merged, "ai", out["model"]


def run_job(t, job, trigger="schedule"):
    findings = FINDERS[job](t)
    findings, source, model = _enrich(t, job, findings)
    db = mongo.db()
    now = datetime.now(timezone.utc)
    keys = set()
    for f in findings:
        keys.add(f["key"])
        existing = db.advice.find_one({"tenant_openid": t, "key": f["key"], "status": OPEN})
        fields = {k: f[k] for k in ("severity", "title", "title_zh", "finding", "finding_zh", "suggestion",
                                    "suggestion_zh")}
        fields.update({"facts": json.loads(json.dumps(f["facts"], default=str)), "source": source, "model": model,
                       "updated_at": now, "job": job})
        if existing:
            db.advice.update_one({"_id": existing["_id"]}, {"$set": fields})
        elif not db.advice.find_one({"tenant_openid": t, "key": f["key"], "status": REJECTED,
                                     "decided_at": {"$gte": now - timedelta(days=3)}}):
            db.advice.insert_one({"advice_id": f"ADV-{uuid.uuid4().hex[:8].upper()}", "tenant_openid": t,
                                  "key": f["key"], "status": OPEN, "created_at": now, "trigger": trigger, **fields})
    # Findings that are no longer true close themselves.
    db.advice.update_many({"tenant_openid": t, "job": job, "status": OPEN, "key": {"$nin": list(keys)}},
                          {"$set": {"status": EXPIRED, "decided_at": now, "decided_by": "agent (no longer true)"}})
    db.agent_runs.insert_one({"tenant_openid": t, "job": job, "trigger": trigger, "ts": now, "findings": len(findings),
                              "source": source, "model": model})
    logger.info("Agent job %s (%s): %d finding(s) via %s", job, trigger, len(findings), source)
    return {"job": job, "findings": len(findings), "source": source, "note": model if source == "rules" else None}


def run_all(t, trigger="schedule"):
    results = [run_job(t, j, trigger) for j in JOBS]
    mongo.db().agent_state.update_one({"_id": t}, {"$set": {"pending": False, "last_run": datetime.now(timezone.utc)}},
                                      upsert=True)
    from .search import sync
    sync(t)
    return results


def mark_pending(t, reason):
    """Alarms call this; the 5-minute cron runs the jobs soon after."""
    mongo.db().agent_state.update_one({"_id": t}, {"$set": {"pending": True, "pending_reason": reason}}, upsert=True)


def decide(account, advice_id, accept, comment=""):
    from accounts import audit
    db = mongo.db()
    a = db.advice.find_one({"advice_id": advice_id, "tenant_openid": account.tenant_openid})
    if not a or a["status"] != OPEN:
        raise ValueError("Only open advice can be accepted or rejected.")
    now = datetime.now(timezone.utc)
    db.advice.update_one({"advice_id": advice_id}, {"$set": {"status": ACCEPTED if accept else REJECTED,
                                                             "decided_by": account.display_name, "decided_at": now,
                                                             "decision_comment": comment}})
    audit.record(account, "advice.accept" if accept else "advice.reject", "advice", advice_id,
                 after={"title": a["title"], "comment": comment})
    from .search import sync
    sync(account.tenant_openid)
    return db.advice.find_one({"advice_id": advice_id}, {"_id": 0})
