"""
Pick routes: the order to visit bins so the picker walks the least.

Walking distance (settings.yaml -> warehouse_layout): bins sit in numbered aisles at a position along
the aisle. Same aisle: walk along it. Different aisles: walk to the front (position 0) or back
cross-aisle, whichever is shorter, across, and back in. The picker starts and ends at the depot.

Engines: "builtin" (every order tried for short lists; nearest bin first + 2-opt clean-up for long ones) or "cuopt"
(cuOpt routing, one picker). Bins without a location cannot be routed: they are listed at the end.
"""
import itertools

from core import config

from . import cuopt


def layout():
    lay = config.get("warehouse_layout", {}) or {}
    depot = lay.get("depot") or {}
    return {"gap": float(lay.get("aisle_gap_m", 3.0)), "pitch": float(lay.get("bin_pitch_m", 1.2)),
            "length": int(lay.get("aisle_length_positions", 20)),
            "depot": (int(depot.get("aisle", 1)), int(depot.get("position", 0)))}


def distance(a, b, lay=None):
    """Metres between two (aisle, position) points."""
    lay = lay or layout()
    (a1, p1), (a2, p2) = a, b
    if a1 == a2:
        return abs(p1 - p2) * lay["pitch"]
    along = min(p1 + p2, 2 * lay["length"] - p1 - p2) * lay["pitch"]
    return abs(a1 - a2) * lay["gap"] + along


def matrix(points, lay=None):
    lay = lay or layout()
    return [[round(distance(a, b, lay), 2) for b in points] for a in points]


def tour_length(order, dist):
    path = [0] + order + [0]
    return sum(dist[path[i]][path[i + 1]] for i in range(len(path) - 1))


def builtin_order(dist):
    """Up to optimiser.builtin_exact_stops bins: try every order (the shortest walk for sure).
    More bins: nearest neighbour from the depot (index 0), then 2-opt until no swap shortens the walk."""
    if len(dist) - 1 <= int(config.get("optimiser.builtin_exact_stops", 8)):
        return list(min(itertools.permutations(range(1, len(dist))), key=lambda o: tour_length(list(o), dist)))
    todo = set(range(1, len(dist)))
    order, here = [], 0
    while todo:
        here = min(todo, key=lambda j: (dist[here][j], j))
        order.append(here)
        todo.remove(here)
    improved = True
    while improved:
        improved = False
        for i in range(len(order) - 1):
            for k in range(i + 1, len(order)):
                new = order[:i] + order[i:k + 1][::-1] + order[k + 1:]
                if tour_length(new, dist) + 1e-9 < tour_length(order, dist):
                    order, improved = new, True
    return order


def cuopt_order(dist, url, token=""):
    n = len(dist)
    problem = {"cost_matrix_data": {"data": {"0": dist}},
               "task_data": {"task_locations": list(range(1, n))},
               "fleet_data": {"vehicle_locations": [[0, 0]]},
               "solver_config": {"time_limit": float(config.get("optimiser.cuopt.time_limit_seconds", 20))}}
    answer = cuopt.solve(url, token, problem)
    if answer.get("status") not in (0, "0", None) or not answer.get("vehicle_data"):
        raise cuopt.CuoptUnavailable(f"cuOpt found no route (status: {answer.get('status', 'unknown')}).")
    route = next(iter(answer["vehicle_data"].values()))["route"]
    order = [i for i in route if i != 0]
    if sorted(order) != list(range(1, n)):
        raise cuopt.CuoptUnavailable("cuOpt returned a route that does not visit every bin once.")
    return order


def plan_route(stops, engine="builtin", url="", token=""):
    """stops: [{"bin_name", "aisle", "position", "lines": [...]}]. Returns the ordered pick list."""
    lay = layout()
    located = [s for s in stops if s.get("aisle") is not None and s.get("position") is not None]
    unlocated = [s for s in stops if s not in located]
    points = [lay["depot"]] + [(int(s["aisle"]), int(s["position"])) for s in located]
    dist = matrix(points, lay)
    if len(located) <= 1:
        order = list(range(1, len(points)))
    elif engine == "cuopt":
        order = cuopt_order(dist, url, token)
    else:
        order = builtin_order(dist)
    ordered = [dict(located[i - 1], seq=n + 1) for n, i in enumerate(order)]
    return {"engine": engine, "stops": ordered, "unlocated": unlocated,
            "distance_m": round(tour_length(order, dist), 1) if order else 0.0,
            "depot": {"aisle": lay["depot"][0], "position": lay["depot"][1]}}
