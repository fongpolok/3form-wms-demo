"""
Benchmark: Built-in planner vs cuOpt on sample factories of growing size.

    python manage.py shell < tools/benchmark_engines.py            (uses the pretend cuOpt server)
    CUOPT_URL=http://gpu-box:5000 python manage.py shell < tools/benchmark_engines.py   (a real cuOpt)

Writes docs/plan/engine-benchmark.json. Each sample factory: 6 workstations in a line, 2 shifts,
orders of 3 products with due dates spread over 2 weeks (fixed random seed, so runs are repeatable).
Measured per engine: when all work is done (hours from the start), total hours late, changeovers,
planning time, and the problem size (steps to place, decisions cuOpt weighs).
"""
import json
import os
import random
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from aps import calendar as cal
from aps import engine
from core import config
from optimiser import plan_milp
from optimiser.cuopt import CuoptUnavailable

SIZES = [int(x) for x in os.environ.get("SIZES", "5,10,15,20,30,40").split(",")]
HKT = ZoneInfo("Asia/Hong_Kong")
START = datetime(2026, 11, 2, 8, tzinfo=HKT)          # a Monday morning
STEPS = ["MIX", "FILL", "CAP", "LABEL", "PACK", "QC"]
STATIONS = {f"WS-{i + 1:02d}": s for i, s in enumerate(STEPS)}
SHIFTS = [{"code": "A", "start": "08:00", "end": "16:00", "break_start": "12:00", "break_minutes": 45, "workers": 6},
          {"code": "B", "start": "16:00", "end": "24:00", "break_start": "20:00", "break_minutes": 45, "workers": 6}]
CHANGEOVER = 20


def factory(n, seed=2026):
    rnd = random.Random(seed + n)
    jobs = []
    for i in range(n):
        due = START.date() + timedelta(days=rnd.randint(2, 14))
        minutes = rnd.choice([40, 60, 90, 120])
        jobs.append(engine.Job(f"B{i:03d}", f"WO{i:03d}", rnd.choice(["HC-50", "SR-30", "LT-200"]),
                               rnd.random() < 0.1, due.isoformat(), rnd.randint(1, 5), f"2026-11-01T{i:04d}",
                               [{"step_no": k + 1, "step_code": c, "minutes": minutes * rnd.uniform(0.6, 1.2)}
                                for k, c in enumerate(STEPS)]))
    return jobs


def measure(res, jobs, slot0):
    finish = {}
    for o in res.ops:
        finish[o["batch_id"]] = max(finish.get(o["batch_id"], o["end"]), o["end"])
    late = 0.0
    for j in jobs:
        target = cal.day_end(date.fromisoformat(j.due_date), HKT) - timedelta(hours=4)
        if j.batch_id in finish:
            late += max(0.0, (finish[j.batch_id] - target).total_seconds() / 3600)
    by_ws = {}
    for o in sorted(res.ops, key=lambda o: o["start"]):
        by_ws.setdefault(o["workstation"], []).append(o["product_code"])
    switches = sum(sum(a != b for a, b in zip(seq, seq[1:])) for seq in by_ws.values())
    done = max(finish.values()) if finish else None
    return {"all_done_hours": round((done - slot0).total_seconds() / 3600, 1) if done else None,
            "hours_late": round(late, 1), "changeovers": switches, "unplaced": len(res.unscheduled)}


def run():
    url = os.environ.get("CUOPT_URL")
    server = None
    if not url:
        from tools import mock_cuopt
        server = mock_cuopt.serve(port=0)
        url = f"http://127.0.0.1:{server.server_address[1]}"
    slots = cal.build(START, days=21, slot_minutes=5, shifts=SHIFTS, working_days=[0, 1, 2, 3, 4, 5], holidays={},
                      staffing={})
    due_slot = lambda j: int(((cal.day_end(date.fromisoformat(j.due_date), HKT) - timedelta(hours=4)) - START)  # noqa: E731
                             .total_seconds() // 300)
    rows = []
    for n in SIZES:
        jobs = factory(n)
        t0 = time.perf_counter()
        b = engine.schedule(slots, STATIONS, jobs, [], 5, CHANGEOVER, 1, group_days=1)
        b_sec = time.perf_counter() - t0
        row = {"orders": n, "steps": sum(len(j.steps) for j in jobs),
               "builtin": {**measure(b, jobs, START), "seconds": round(b_sec, 3)}}
        t0 = time.perf_counter()
        try:
            c = plan_milp.schedule(slots, STATIONS, jobs, [], 5, CHANGEOVER, 1, due_slot, url, changeover_cost=30)
            row["decisions"] = c.stats["decisions"]
            row["cuopt"] = {**measure(c, jobs, START), "seconds": round(time.perf_counter() - t0, 1)}
        except CuoptUnavailable as exc:
            row["cuopt"] = {"error": str(exc), "seconds": round(time.perf_counter() - t0, 1)}
        rows.append(row)
        print(json.dumps(row), flush=True)
    out = {"run_at": datetime.now(HKT).isoformat(timespec="minutes"),
           "solver": "pretend cuOpt server (HiGHS on CPU)" if server else f"cuOpt at {url}",
           "time_limit_seconds": float(config.get("optimiser.cuopt.time_limit_seconds", 20)),
           "workstations": len(STATIONS), "changeover_minutes": CHANGEOVER, "rows": rows}
    path = Path("docs/plan/engine-benchmark.json")
    path.write_text(json.dumps(out, indent=1))
    print("written", path)
    if server:
        server.shutdown()


run()
