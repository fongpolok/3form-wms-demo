"""
APS engine: finite-capacity forward scheduling on a slot grid.

1. SORT batches:  Special/Urgent -> due date -> client priority -> product
   (same-product batches sit together, which saves changeovers, without ever
   jumping a due date) -> time received.
2. FIT each batch's remaining steps, in order, into the first slots where
     * the slot is working time (calendar, shifts, breaks, holidays),
     * the workstation is free,
     * a worker is free (workers used < workers on that shift),
     * the previous step of the same batch has finished.
   A changeover is added when the workstation's previous batch was a different product.
   Work pauses over breaks / nights and continues in the next working slot.
3. Fixed first: batches running now, and published operations inside the frozen window.

Pure Python, no database: inputs are plain dicts, so it is easy to test.
"""
import math
from dataclasses import dataclass, field
from datetime import timedelta


@dataclass
class Job:
    batch_id: str
    wo_id: str
    product_code: str
    urgent: bool
    due_date: str            # YYYY-MM-DD
    client_priority: int
    created_at: str
    steps: list              # [{"step_no", "step_code", "minutes"}] remaining, in order
    ready_after: object = None   # datetime: earliest start of the first remaining step


@dataclass
class Fixed:
    workstation: str
    batch_id: str
    wo_id: str
    product_code: str
    step_no: int
    step_code: str
    start: object
    end: object
    kind: str                # running | frozen


@dataclass
class Result:
    ops: list = field(default_factory=list)
    unscheduled: list = field(default_factory=list)


def priority_key(job):
    return (not job.urgent, job.due_date, job.client_priority, job.product_code, job.created_at, job.batch_id)


class Grid:
    def __init__(self, slots, workstations, slot_minutes, workers_per_station):
        self.slots = slots
        self.n = len(slots)
        self.minutes = slot_minutes
        self.per_station = workers_per_station
        self.busy = {ws: [None] * self.n for ws in workstations}       # slot -> product code
        self.workers = [0] * self.n
        self.t0 = slots[0].start if slots else None

    def index(self, when):
        if when is None or when <= self.t0:
            return 0
        return min(self.n, math.ceil((when - self.t0).total_seconds() / 60 / self.minutes))

    def time(self, i):
        return self.t0 + timedelta(minutes=self.minutes * i)

    def occupy(self, ws, i0, i1, product):
        for i in range(max(i0, 0), min(i1, self.n)):
            self.busy[ws][i] = product
            if self.slots[i].working:
                self.workers[i] += self.per_station

    def previous_product(self, ws, i):
        row = self.busy[ws]
        for j in range(min(i, self.n) - 1, -1, -1):
            if row[j] is not None:
                return row[j]
        return None

    def fit(self, ws, earliest, work_slots, product, changeover_slots):
        """First run of free working slots on `ws` from `earliest`. Returns (taken slot indexes, setup slots)."""
        s = earliest
        while s < self.n:
            while s < self.n and not self.slots[s].working:
                s += 1
            if s >= self.n:
                return None, 0
            prev = self.previous_product(ws, s)
            setup = changeover_slots if prev is not None and prev != product else 0
            need, taken, i, restart = work_slots + setup, [], s, None
            while need > 0:
                if i >= self.n:
                    return None, 0
                slot = self.slots[i]
                if not slot.working:
                    i += 1
                    continue
                if self.busy[ws][i] is not None or self.workers[i] + self.per_station > slot.workers:
                    restart = i + 1
                    break
                taken.append(i)
                need -= 1
                i += 1
            if restart is None:
                return taken, setup
            s = restart
        return None, 0


def load_fixed(grid, res, fixed):
    """Put running / frozen operations on the grid first. Returns {batch_id: first free slot after them}."""
    batch_ready = {}
    for f in fixed:
        if f.workstation not in grid.busy:
            continue
        i0, i1 = grid.index(f.start), max(grid.index(f.end), grid.index(f.start) + 1)
        grid.occupy(f.workstation, i0, i1, f.product_code)
        res.ops.append({"workstation": f.workstation, "batch_id": f.batch_id, "wo_id": f.wo_id,
                        "product_code": f.product_code, "step_no": f.step_no, "step_code": f.step_code,
                        "start": f.start, "end": max(f.end, grid.time(i1)) if f.kind == "frozen" else f.end,
                        "setup_minutes": 0, "kind": f.kind})
        batch_ready[f.batch_id] = max(batch_ready.get(f.batch_id, 0), i1)
    return batch_ready


def place(grid, res, job, st, stations, ready, changeover_slots, workers_per_station, engine="builtin"):
    """Fit one step on the best of `stations` (earliest finish) from slot `ready`.
    Returns the first slot after it, or None (and records why) when it does not fit."""
    work_slots = max(1, math.ceil(st["minutes"] / grid.minutes))
    best = None
    for ws in sorted(stations):
        taken, setup = grid.fit(ws, ready, work_slots, job.product_code, changeover_slots)
        if taken and (best is None or taken[-1] < best[1][-1]):
            best = (ws, taken, setup)
    if best is None:
        res.unscheduled.append({"batch_id": job.batch_id, "wo_id": job.wo_id, "step_code": st["step_code"],
                                "reason": "beyond planning horizon" if stations else "no workstation for this step"})
        return None
    ws, taken, setup = best
    for i in taken:
        grid.busy[ws][i] = job.product_code
        grid.workers[i] += workers_per_station
    res.ops.append({"workstation": ws, "batch_id": job.batch_id, "wo_id": job.wo_id,
                    "product_code": job.product_code, "step_no": st["step_no"], "step_code": st["step_code"],
                    "start": grid.time(taken[setup]) if setup < len(taken) else grid.time(taken[0]),
                    "setup_start": grid.time(taken[0]) if setup else None,
                    "end": grid.time(taken[-1] + 1), "setup_minutes": setup * grid.minutes,
                    "work_minutes": st["minutes"], "kind": "planned", "urgent": job.urgent, "engine": engine})
    return taken[-1] + 1


def stations_by_step(workstations):
    by_step = {}
    for ws, step in workstations.items():
        by_step.setdefault(step, []).append(ws)
    return by_step


def schedule(slots, workstations, jobs, fixed, slot_minutes, changeover_minutes, workers_per_station=1):
    """workstations: {code: step_code}. Returns Result with ops (dicts) in time order."""
    res = Result()
    if not slots:
        res.unscheduled = [{"batch_id": j.batch_id, "wo_id": j.wo_id, "reason": "no calendar"} for j in jobs]
        return res
    grid = Grid(slots, workstations, slot_minutes, workers_per_station)
    changeover_slots = math.ceil(changeover_minutes / slot_minutes) if changeover_minutes else 0
    batch_ready = load_fixed(grid, res, fixed)
    by_step = stations_by_step(workstations)
    for job in sorted(jobs, key=priority_key):
        ready = max(batch_ready.get(job.batch_id, 0), grid.index(job.ready_after))
        for st in job.steps:
            ready = place(grid, res, job, st, by_step.get(st["step_code"], []), ready, changeover_slots,
                          workers_per_station)
            if ready is None:
                break
    res.ops.sort(key=lambda o: (o["start"], o["workstation"]))
    return res
