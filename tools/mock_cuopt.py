"""
Pretend NVIDIA cuOpt server, for testing without a GPU. Same REST interface as the real one:

    python tools/mock_cuopt.py --port 5000

    POST   /cuopt/request            -> {"reqId"}  (answer is ready on the first poll)
    GET    /cuopt/solution/{reqId}   -> {"response": {"solver_response": ...}, "reqId"}
    DELETE /cuopt/solution/{reqId}
    GET    /cuopt/health             -> {"status": "RUNNING", "version": "mock"}

MILP problems are really solved (HiGHS on the CPU), so the planning model is checked for real.
Routing problems (one vehicle) are solved exactly for up to 8 stops, otherwise nearest-neighbour + 2-opt.
Then in Settings -> Integrations -> Optimiser set the address to http://127.0.0.1:5000.
"""
import argparse
import itertools
import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SOLUTIONS = {}
LOCK = threading.Lock()


def solve_milp(p):
    import highspy
    import numpy as np
    h = highspy.Highs()
    h.setOptionValue("output_flag", False)
    h.setOptionValue("time_limit", float(p.get("solver_config", {}).get("time_limit", 30)))
    lp = highspy.HighsLp()
    n = len(p["objective_data"]["coefficients"])
    csr = p["csr_constraint_matrix"]
    lp.num_col_, lp.num_row_ = n, len(csr["offsets"]) - 1
    lp.col_cost_ = np.array(p["objective_data"]["coefficients"], dtype=float)
    lp.col_lower_ = np.array(p["variable_bounds"]["lower_bounds"], dtype=float)
    lp.col_upper_ = np.array(p["variable_bounds"]["upper_bounds"], dtype=float)
    inf = highspy.kHighsInf
    lp.row_lower_ = np.array([-inf if v <= -1e19 else v for v in p["constraint_bounds"]["lower_bounds"]], dtype=float)
    lp.row_upper_ = np.array([inf if v >= 1e19 else v for v in p["constraint_bounds"]["upper_bounds"]], dtype=float)
    lp.a_matrix_.format_ = highspy.MatrixFormat.kRowwise
    lp.a_matrix_.start_ = np.array(csr["offsets"], dtype=np.int32)
    lp.a_matrix_.index_ = np.array(csr["indices"], dtype=np.int32)
    lp.a_matrix_.value_ = np.array(csr["values"], dtype=float)
    lp.integrality_ = [highspy.HighsVarType.kInteger if t == "I" else highspy.HighsVarType.kContinuous
                       for t in p["variable_types"]]
    lp.sense_ = highspy.ObjSense.kMaximize if p.get("maximize") else highspy.ObjSense.kMinimize
    h.passModel(lp)
    h.run()
    status = h.modelStatusToString(h.getModelStatus())
    sol = list(h.getSolution().col_value)
    if not sol or status in ("Infeasible", "Unbounded"):
        return {"status": status, "solution": {"problem_category": "MIP"}}
    return {"status": "Optimal" if status == "Optimal" else "FeasibleFound",
            "solution": {"problem_category": "MIP", "primal_solution": sol,
                         "primal_objective": h.getInfo().objective_function_value, "solver_time": h.getRunTime()}}


def solve_route(p):
    cost = next(iter(p["cost_matrix_data"]["data"].values()))
    tasks = list(p["task_data"]["task_locations"])
    start, end = p["fleet_data"]["vehicle_locations"][0]

    def length(order):
        path = [start] + list(order) + [end]
        return sum(cost[path[i]][path[i + 1]] for i in range(len(path) - 1))

    if len(tasks) <= 8:
        best = min(itertools.permutations(tasks), key=length)
    else:
        best, here, todo = [], start, set(tasks)
        while todo:
            here = min(todo, key=lambda j: cost[here][j])
            best.append(here)
            todo.remove(here)
        improved = True
        while improved:
            improved = False
            for i in range(len(best) - 1):
                for k in range(i + 1, len(best)):
                    new = best[:i] + best[i:k + 1][::-1] + best[k + 1:]
                    if length(new) < length(best) - 1e-9:
                        best, improved = new, True
    route = [start] + list(best) + [end]
    return {"status": 0, "num_vehicles": 1, "solution_cost": length(best),
            "vehicle_data": {"0": {"task_id": ["Depot"] + [str(t) for t in best] + ["Depot"], "route": route,
                                   "type": ["Depot"] + ["Delivery"] * len(best) + ["Depot"]}},
            "dropped_tasks": {"task_id": [], "task_index": []}}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/cuopt/health":
            return self._send(200, {"status": "RUNNING", "version": "mock"})
        if self.path.startswith("/cuopt/solution/"):
            rid = self.path.rsplit("/", 1)[-1]
            with LOCK:
                answer = SOLUTIONS.get(rid)
            if answer is None:
                return self._send(404, {"error": f"no request {rid}"})
            return self._send(200, {"response": {"solver_response": answer}, "reqId": rid})
        self._send(404, {"error": "unknown path"})

    def do_POST(self):
        if self.path.split("?")[0] != "/cuopt/request":
            return self._send(404, {"error": "unknown path"})
        problem = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        try:
            answer = solve_milp(problem) if "csr_constraint_matrix" in problem else solve_route(problem)
        except Exception as exc:  # noqa: BLE001 - report like the real server does
            return self._send(400, {"error": f"{exc.__class__.__name__}: {exc}"})
        rid = str(uuid.uuid4())
        with LOCK:
            SOLUTIONS[rid] = answer
        self._send(200, {"reqId": rid})

    def do_DELETE(self):
        with LOCK:
            SOLUTIONS.pop(self.path.rsplit("/", 1)[-1], None)
        self._send(200, {"deleted": True})

    def log_message(self, fmt, *args):
        pass


def serve(port=5000, host="127.0.0.1"):
    """Start in a background thread (tests). Returns the server; .server_address has the real port."""
    srv = ThreadingHTTPServer((host, port), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def main():
    ap = argparse.ArgumentParser(description="Pretend NVIDIA cuOpt server (CPU, for tests)")
    ap.add_argument("--port", type=int, default=5000)
    a = ap.parse_args()
    print(f"Mock cuOpt on http://127.0.0.1:{a.port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
