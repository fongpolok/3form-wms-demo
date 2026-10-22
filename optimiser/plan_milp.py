"""
Production plan with NVIDIA cuOpt (mixed-integer programme), same inputs and output as aps.engine.schedule.

How it works:
1. Time is measured in WORKING minutes from now (breaks, nights and holidays removed), so the model
   does not need the calendar.
2. cuOpt decides, for every workstation, which batch runs IMMEDIATELY after which (and which station
   when a step has more than one), minimising:
       minutes late x late_minute_cost x urgent / client-priority multipliers
     + changeovers x changeover_cost_minutes x late_minute_cost   (aps.changeover_cost_minutes, Calendar page)
     + finish time x finish_minute_cost.
   Rules in the model: steps of a batch in order; each workstation runs one chain of batches; changeover
   time between different products; running / frozen work stays where it is.
3. Our own calendar grid then places each step in cuOpt's order, so breaks, shifts and worker numbers
   are respected exactly (the same placing code as the built-in planner).
Settings: config/settings.yaml -> optimiser.
"""
import math
from collections import defaultdict

from core import config

from aps.engine import Grid, Result, load_fixed, place, stations_by_step
from . import cuopt


class PlanTooLarge(cuopt.CuoptUnavailable):
    pass


class Model:
    """A small builder for cuOpt's MILP JSON (CSR constraint matrix)."""

    def __init__(self):
        self.names, self.lb, self.ub, self.types, self.obj = [], [], [], [], []
        self.rows = []          # (dict var -> coeff, lower, upper)

    def var(self, name, lb=0.0, ub=1e9, kind="C", cost=0.0):
        self.names.append(name)
        self.lb.append(float(lb))
        self.ub.append(float(ub))
        self.types.append(kind)
        self.obj.append(float(cost))
        return len(self.names) - 1

    def row(self, coeffs, lower=-math.inf, upper=math.inf):
        self.rows.append(({k: v for k, v in coeffs.items() if v}, lower, upper))

    def binaries(self):
        return sum(1 for t in self.types if t == "I")

    def to_cuopt(self, time_limit):
        offsets, indices, values, lows, ups = [0], [], [], [], []
        for coeffs, lo, up in self.rows:
            for k in sorted(coeffs):
                indices.append(k)
                values.append(float(coeffs[k]))
            offsets.append(len(indices))
            lows.append(lo if math.isfinite(lo) else -1e20)
            ups.append(up if math.isfinite(up) else 1e20)
        return {"csr_constraint_matrix": {"offsets": offsets, "indices": indices, "values": values},
                "constraint_bounds": {"lower_bounds": lows, "upper_bounds": ups},
                "objective_data": {"coefficients": self.obj, "scalability_factor": 1.0, "offset": 0.0},
                "variable_bounds": {"lower_bounds": self.lb, "upper_bounds": self.ub},
                "maximize": False, "variable_types": self.types, "variable_names": self.names,
                "solver_config": {"time_limit": time_limit}}


def _working_minutes(grid):
    """cum[i] = working minutes before slot i (cum has n+1 entries)."""
    cum = [0]
    for s in grid.slots:
        cum.append(cum[-1] + (grid.minutes if s.working else 0))
    return cum


def build(grid, jobs, fixed_ready, station_free, by_step, changeover_min, due_slot, changeover_cost=0.0):
    """Returns (model, ops) where ops[i] = {job, step, stations, S var, x vars}."""
    cum = _working_minutes(grid)
    horizon = cum[-1]
    w = config.get("optimiser", {}) or {}
    late_cost = float(w.get("late_minute_cost", 10))
    urgent_mult = float(w.get("urgent_multiplier", 10))
    prio_mult = {int(k): float(v) for k, v in (w.get("priority_multiplier") or {}).items()}
    finish_cost = float(w.get("finish_minute_cost", 0.01))
    total_work = sum(max(1, math.ceil(st["minutes"] / grid.minutes)) * grid.minutes for j in jobs for st in j.steps)
    big_m = horizon + total_work + changeover_min * len(jobs) + 1

    m = Model()
    ops = []
    for j in jobs:
        release = cum[min(max(fixed_ready.get(j.batch_id, 0), grid.index(j.ready_after)), grid.n)]
        prev = None
        for k, st in enumerate(j.steps):
            p = max(1, math.ceil(st["minutes"] / grid.minutes)) * grid.minutes
            stations = sorted(by_step.get(st["step_code"], []))
            if not stations:
                raise cuopt.CuoptUnavailable(f"No workstation for step {st['step_code']} of {j.batch_id}.")
            s = m.var(f"S_{j.batch_id}_{st['step_no']}", lb=release if k == 0 else 0, ub=big_m)
            xs = {}
            if len(stations) > 1:
                for ws in stations:
                    xs[ws] = m.var(f"x_{j.batch_id}_{st['step_no']}_{ws}", 0, 1, "I")
                m.row({x: 1 for x in xs.values()}, 1, 1)
            if prev is not None:      # steps of a batch in order
                m.row({s: 1, prev["S"]: -1}, prev["p"])
            op = {"job": j, "step": st, "p": p, "S": s, "x": xs, "stations": stations}
            ops.append(op)
            prev = op
        last = ops[-1]
        due = cum[min(due_slot(j), grid.n)] if due_slot(j) <= grid.n else horizon + (due_slot(j) - grid.n) * grid.minutes
        weight = late_cost * (urgent_mult if j.urgent else 1) * prio_mult.get(int(j.client_priority), 1.0)
        t = m.var(f"T_{j.batch_id}", 0, big_m, cost=weight)
        m.row({t: 1, last["S"]: -1}, last["p"] - due)            # T >= S_last + p_last - due
        m.obj[last["S"]] += finish_cost

    # Each workstation runs ONE chain: start -> step -> step -> ... -> end. u[a, b] = 1 when b runs
    # immediately after a. Times along the chain stop overlaps (and loops); a changeover between
    # different products costs time and, if aps.changeover_cost_minutes > 0, money in the goal.
    switch_cost = changeover_cost * late_cost
    by_station = defaultdict(list)
    for op in ops:
        for ws in op["stations"]:
            by_station[ws].append(op)

    def on(op, ws):                     # 1 if the step is on ws: a fixed 1, or its station-choice variable
        return op["x"].get(ws)

    for ws, group in by_station.items():
        free_at, before = station_free.get(ws, (0, None))
        free_min = cum[min(free_at, grid.n)]
        succ = {id(o): {} for o in group}
        pred = {id(o): {} for o in group}
        firsts = {}
        for o in group:
            switch = bool(before) and before != o["job"].product_code
            first = m.var(f"first_{o['job'].batch_id}_{o['step']['step_no']}_{ws}", 0, 1, "I",
                          cost=switch_cost if switch else 0.0)
            firsts[id(o)] = first
            # Station is busy until running / frozen work ends (+ changeover if this step comes first):
            #   S >= free_min * (on ws) + changeover * first
            row, lower = {o["S"]: 1}, free_min
            if on(o, ws) is not None:
                row[on(o, ws)], lower = -free_min, 0
            if switch:
                row[first] = -changeover_min
            if free_min or switch:
                m.row(row, lower)
        for a in group:
            for b in group:
                if a is b:
                    continue
                differs = a["job"].product_code != b["job"].product_code
                u = m.var(f"u_{a['job'].batch_id}_{a['step']['step_no']}_{b['job'].batch_id}_{b['step']['step_no']}_{ws}",
                          0, 1, "I", cost=switch_cost if differs else 0.0)
                succ[id(a)][id(b)] = u
                pred[id(b)][id(a)] = u
                setup = changeover_min if differs else 0
                # u = 1:  S_b >= S_a + p_a + setup
                m.row({b["S"]: 1, a["S"]: -1, u: -big_m}, a["p"] + setup - big_m)
        lasts = {id(o): m.var(f"last_{o['job'].batch_id}_{o['step']['step_no']}_{ws}", 0, 1, "I") for o in group}
        for o in group:
            here = on(o, ws)
            # exactly one step before it (or the start) and one after it (or the end) when it is on ws
            row_in = {firsts[id(o)]: 1, **{u: 1 for u in pred[id(o)].values()}}
            row_out = {lasts[id(o)]: 1, **{u: 1 for u in succ[id(o)].values()}}
            if here is None:
                m.row(row_in, 1, 1)
                m.row(row_out, 1, 1)
            else:
                m.row({**row_in, here: -1}, 0, 0)
                m.row({**row_out, here: -1}, 0, 0)
        m.row({f: 1 for f in firsts.values()}, upper=1)
        m.row({v: 1 for v in lasts.values()}, upper=1)
    limit = int(config.get("optimiser.cuopt.max_binary_variables", 20000))
    if m.binaries() > limit:
        raise PlanTooLarge(f"The plan is too big for one cuOpt run ({m.binaries()} choices, limit {limit}). "
                           "Shorten the planning horizon or raise optimiser.cuopt.max_binary_variables.")
    return m, ops


def schedule(slots, workstations, jobs, fixed, slot_minutes, changeover_minutes, workers_per_station, due_slot,
             url, token="", changeover_cost=0.0):
    """Same result shape as aps.engine.schedule. due_slot(job) -> slot index of the job's target finish."""
    res = Result()
    if not slots:
        res.unscheduled = [{"batch_id": j.batch_id, "wo_id": j.wo_id, "reason": "no calendar"} for j in jobs]
        return res
    grid = Grid(slots, workstations, slot_minutes, workers_per_station)
    changeover_slots = math.ceil(changeover_minutes / slot_minutes) if changeover_minutes else 0
    batch_ready = load_fixed(grid, res, fixed)
    station_free = {}
    for f in fixed:
        if f.workstation in grid.busy:
            end = max(grid.index(f.end), grid.index(f.start) + 1)
            if end >= station_free.get(f.workstation, (0, None))[0]:
                station_free[f.workstation] = (end, f.product_code)
    by_step = stations_by_step(workstations)
    if not jobs:
        res.ops.sort(key=lambda o: (o["start"], o["workstation"]))
        return res
    model, ops = build(grid, jobs, batch_ready, station_free, by_step, changeover_slots * slot_minutes, due_slot,
                       changeover_cost)
    answer = cuopt.solve(url, token, model.to_cuopt(float(config.get("optimiser.cuopt.time_limit_seconds", 20))))
    solution = answer.get("solution") or {}
    values = solution.get("primal_solution")
    if not values or len(values) != len(model.names):
        raise cuopt.CuoptUnavailable(f"cuOpt found no plan (status: {answer.get('status', 'unknown')}).")

    # Place steps in cuOpt's order on cuOpt's chosen stations; the grid applies the exact calendar.
    order = sorted(ops, key=lambda o: (values[o["S"]], o["step"]["step_no"]))
    ready = {j.batch_id: max(batch_ready.get(j.batch_id, 0), grid.index(j.ready_after)) for j in jobs}
    stopped = set()
    for op in order:
        j = op["job"]
        if j.batch_id in stopped:
            continue
        chosen = op["stations"]
        if op["x"]:
            chosen = [max(op["x"], key=lambda ws: values[op["x"][ws]])]
        nxt = place(grid, res, j, op["step"], chosen, ready[j.batch_id], changeover_slots, workers_per_station,
                    engine="cuopt")
        if nxt is None:
            stopped.add(j.batch_id)
        else:
            ready[j.batch_id] = nxt
    res.ops.sort(key=lambda o: (o["start"], o["workstation"]))
    return res
