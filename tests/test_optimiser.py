"""v3.6.0: optional NVIDIA cuOpt for production planning and pick routes (tested with tools/mock_cuopt.py)."""
import itertools
import math

import pytest

from aps import engine
from inventory.models import Alert
from optimiser import pick, plan_milp
from optimiser.cuopt import CuoptUnavailable
from optimiser.models import OptimiserSetting
from tests.test_aps import _job, _slots
from tools import mock_cuopt

API = "/api/v1"
DEAD_URL = "http://127.0.0.1:9"      # nothing listens here


@pytest.fixture(scope="module")
def cuopt_url():
    srv = mock_cuopt.serve(port=0)
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def _lateness(ops, due):
    finish = {}
    for o in ops:
        finish[o["batch_id"]] = max(finish.get(o["batch_id"], o["end"]), o["end"])
    t0 = min(o["start"] for o in ops)
    return {b: max(0.0, (f - t0).total_seconds() / 60 - due[b]) for b, f in finish.items()}


# ------------------------------------------------------------------ planning
def test_cuopt_plan_beats_due_date_order_on_total_lateness(cuopt_url):
    """Long job X is due a little earlier than short job Y. Due-date order runs X first and makes both late;
    doing Y first makes Y on time and X only slightly later, so total lateness drops."""
    slots, stations = _slots(), {"WS-01": "MIX"}
    jobs = [_job("X", 300, due="2026-11-03", steps=("MIX",)), _job("Y", 30, due="2026-11-04", steps=("MIX",))]
    due_minutes = {"X": 100, "Y": 120}
    due_slot = lambda j: due_minutes[j.batch_id] // 5            # noqa: E731
    builtin = engine.schedule(slots, stations, jobs, [], 5, 0)
    cu = plan_milp.schedule(slots, stations, jobs, [], 5, 0, 1, due_slot, cuopt_url)
    first = lambda res: sorted(res.ops, key=lambda o: o["start"])[0]["batch_id"]   # noqa: E731
    assert first(builtin) == "X" and first(cu) == "Y"
    assert all(o["engine"] == "cuopt" for o in cu.ops)
    # Clock minutes include the lunch break, but the order of the two totals is what matters.
    assert sum(_lateness(cu.ops, due_minutes).values()) < sum(_lateness(builtin.ops, due_minutes).values())


def test_cuopt_plan_keeps_every_rule(cuopt_url):
    stations = {"WS-01": "MIX", "WS-02": "FILL", "WS-03": "FILL"}     # FILL has a choice of two stations
    jobs = [_job(f"J{i}", 40 + 10 * i, product="P" if i % 2 else "Q", urgent=(i == 3)) for i in range(5)]
    res = plan_milp.schedule(_slots(), stations, jobs, [], 5, 20, 1, lambda j: 200, cuopt_url)
    assert not res.unscheduled and len(res.ops) == 10
    ops = {(o["batch_id"], o["step_code"]): o for o in res.ops}
    for j in jobs:
        assert ops[(j.batch_id, "FILL")]["start"] >= ops[(j.batch_id, "MIX")]["end"]
    for ws in stations:
        mine = sorted((o for o in res.ops if o["workstation"] == ws), key=lambda o: o["start"])
        assert all(a["end"] <= (b.get("setup_start") or b["start"]) for a, b in zip(mine, mine[1:]))
        for a, b in zip(mine, mine[1:]):       # changeover between different products
            if a["product_code"] != b["product_code"]:
                assert b["setup_minutes"] == 20
    assert {o["workstation"] for o in res.ops if o["step_code"] == "FILL"} == {"WS-02", "WS-03"}


def test_cuopt_down_raises_and_changes_nothing():
    with pytest.raises(CuoptUnavailable, match="not reachable"):
        plan_milp.schedule(_slots(), {"WS-01": "MIX"}, [_job("A", 30, steps=("MIX",))], [], 5, 0, 1,
                           lambda j: 100, DEAD_URL)


def test_too_big_plan_is_refused_with_a_message(cuopt_url, monkeypatch):
    from core import config
    real = config.get
    monkeypatch.setattr(config, "get",
                        lambda k, d=None: 3 if k == "optimiser.cuopt.max_binary_variables" else real(k, d))
    jobs = [_job(f"J{i}", 30, steps=("MIX",)) for i in range(4)]
    with pytest.raises(plan_milp.PlanTooLarge, match="too big"):
        plan_milp.schedule(_slots(), {"WS-01": "MIX"}, jobs, [], 5, 0, 1, lambda j: 100, cuopt_url)


def test_replan_with_cuopt_down_keeps_published_plan_and_raises_red_alert(people, clients):
    from aps import service
    from core import mongo
    from mes import services as mes
    mes.create_work_order(people["pic"], {"product_code": "HC-50", "qty": 50, "due_date": "2026-12-01"}, source="ERP")
    first = service.request_replan(people["pic"].tenant_openid, "test")
    service.decide(people["pic"], first["plan_id"], True)
    OptimiserSetting.objects.create(tenant_openid=people["pic"].tenant_openid, plan_engine="cuopt", cuopt_url=DEAD_URL)
    n_plans = mongo.db().plans.count_documents({})
    r = clients["em"].post(f"{API}/aps/replan")
    assert r.status_code == 503 and "published plan is unchanged" in r.json()["detail"]
    assert mongo.db().plans.count_documents({}) == n_plans
    assert service.current(people["pic"].tenant_openid)["plan_id"] == first["plan_id"]
    alert = Alert.objects.get(kind="OPTIMISER_UNAVAILABLE", is_open=True)
    assert alert.severity == "alarm" and "production plan" in alert.title


def test_replan_with_cuopt_up_uses_cuopt_and_clears_the_alarm(people, cuopt_url):
    from aps import service
    from mes import services as mes
    tenant = people["pic"].tenant_openid
    mes.create_work_order(people["pic"], {"product_code": "HC-50", "qty": 50, "due_date": "2026-12-01"}, source="ERP")
    OptimiserSetting.objects.create(tenant_openid=tenant, plan_engine="cuopt", cuopt_url=DEAD_URL)
    with pytest.raises(CuoptUnavailable):
        service.request_replan(tenant, "down")
    OptimiserSetting.objects.filter(tenant_openid=tenant).update(cuopt_url=cuopt_url)
    plan = service.request_replan(tenant, "back up")
    assert plan["engine"] == "cuopt" and plan["ops"] and all(o.get("engine") == "cuopt" for o in plan["ops"])
    assert not Alert.objects.filter(kind="OPTIMISER_UNAVAILABLE", is_open=True).exists()


# ------------------------------------------------------------------ pick routes
def test_walking_distance_uses_the_shorter_cross_aisle():
    lay = {"gap": 3.0, "pitch": 1.0, "length": 20, "depot": (1, 0)}
    assert pick.distance((1, 2), (1, 7), lay) == 5
    assert pick.distance((1, 2), (3, 3), lay) == 2 * 3 + (2 + 3)            # via the front
    assert pick.distance((1, 18), (2, 19), lay) == 3 + (2 + 1)              # via the back


def _best_length(dist):
    return min(pick.tour_length(list(p), dist) for p in itertools.permutations(range(1, len(dist))))


@pytest.mark.parametrize("engine_name", ["builtin", "cuopt"])
def test_pick_route_is_shortest_and_lists_unmapped_bins_last(engine_name, cuopt_url):
    stops = [{"bin_name": f"B{i}", "aisle": a, "position": p, "lines": []}
             for i, (a, p) in enumerate([(3, 15), (1, 4), (2, 18), (1, 12), (4, 2), (2, 6)])]
    stops.append({"bin_name": "NOWHERE", "aisle": None, "position": None, "lines": []})
    route = pick.plan_route(stops, engine_name, cuopt_url)
    points = [pick.layout()["depot"]] + [(s["aisle"], s["position"]) for s in stops[:-1]]
    assert route["distance_m"] == pytest.approx(_best_length(pick.matrix(points)), abs=0.1)
    assert [s["seq"] for s in route["stops"]] == list(range(1, 7))
    assert [s["bin_name"] for s in route["unlocated"]] == ["NOWHERE"]


def test_pick_route_api_follows_fefo_and_engine_setting(people, clients, factory, cuopt_url):
    tenant = people["pic"].tenant_openid
    for b, a, p in (("RM-01", 2, 10), ("RM-02", 1, 3)):
        assert clients["pic"].patch(f"{API}/inventory/bins/{b}/location", {"aisle": a, "position": p},
                                    format="json").status_code == 200
    assert clients["em"].patch(f"{API}/inventory/bins/RM-01/location", {"aisle": 1, "position": 1},
                               format="json").status_code == 403
    body = {"lines": [{"goods_code": "CREAM", "qty": 2500}, {"goods_code": "JAR", "qty": 10}]}
    r = clients["em"].post(f"{API}/inventory/pick-route", body, format="json").json()
    assert r["engine"] == "builtin" and [s["bin_name"] for s in r["stops"]] == ["RM-02", "RM-01"]
    rm02 = r["stops"][0]["lines"]
    assert rm02 == [{"goods_code": "CREAM", "lot_number": "CR-EARLY", "qty": 2000, "expiry_date": rm02[0]["expiry_date"]}]
    OptimiserSetting.objects.create(tenant_openid=tenant, pick_engine="cuopt", cuopt_url=DEAD_URL)
    r = clients["em"].post(f"{API}/inventory/pick-route", body, format="json")
    assert r.status_code == 503 and Alert.objects.filter(kind="OPTIMISER_UNAVAILABLE", is_open=True).exists()
    OptimiserSetting.objects.filter(tenant_openid=tenant).update(cuopt_url=cuopt_url)
    r = clients["em"].post(f"{API}/inventory/pick-route", body, format="json").json()
    assert r["engine"] == "cuopt" and [s["bin_name"] for s in r["stops"]] == ["RM-02", "RM-01"]
    assert not Alert.objects.filter(kind="OPTIMISER_UNAVAILABLE", is_open=True).exists()


def test_optimiser_settings_are_pic_only_and_validated(people, clients, cuopt_url):
    url = f"{API}/integrations/optimiser"
    assert clients["em"].get(url).status_code == 403
    assert clients["pic"].get(url).json()["plan_engine"] == "builtin"
    bad = clients["pic"].put(url, {"plan_engine": "cuopt", "cuopt_url": "ftp://x"}, format="json")
    assert bad.status_code == 400
    ok = clients["pic"].put(url, {"plan_engine": "cuopt", "cuopt_url": cuopt_url, "cuopt_token": "t0k"}, format="json")
    assert ok.status_code == 200 and ok.json()["has_token"] and "t0k" not in ok.content.decode()
    test = clients["pic"].post(f"{url}/test").json()
    assert test["ok"] and "mock" in test["reply"]
