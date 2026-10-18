"""Phase 2 rules: material gate, FEFO, put-away, shipping, counts, cameras, SPC, lean."""
import uuid
from datetime import date, timedelta

import pytest

from accounts.models import AuditLog
from core import mongo
from inventory.models import Alert, CountTask, MaterialRequest, Movement, Reservation, Shipment, StockLot
from mes import devices, lean, materials, services

pytestmark = pytest.mark.django_db
API = "/api/v1"
GW = {"HTTP_X_GATEWAY_TOKEN": "test-gateway-token"}


def _order(people, qty=40, batches=2, **kw):
    data = {"product_code": "HC-50", "qty": qty, "batches": batches, "due_date": "2026-12-01", "ship_mode": "stock",
            **kw}
    return services.create_work_order(people["pic"], data, source=kw.pop("source", "ERP"))


def _ev():
    return uuid.uuid4().hex


def test_fefo_picks_earliest_expiry_and_skips_expired(people, factory):
    t = people["pic"].tenant_openid
    lots = factory.pickable_lots(t, "CREAM")
    assert [l.lot_number for l in lots] == ["CR-EARLY", "CR-LATE"]
    StockLot.objects.filter(lot_number="CR-EARLY").update(expiry_date=date.today() - timedelta(days=1))
    assert [l.lot_number for l in factory.pickable_lots(t, "CREAM")] == ["CR-LATE"]


def test_order_with_enough_material_is_reserved(people, factory):
    wo, _ = _order(people, qty=40)          # needs 2000 g cream + 40 jars
    assert wo["status"] == "released"
    res = {r.goods_code: r.qty_reserved for r in Reservation.objects.filter(wo_id=wo["wo_id"])}
    assert res == {"CREAM": 2000, "JAR": 40}
    assert factory.available(people["pic"].tenant_openid, "JAR") == 60


def test_short_order_waits_until_replenished(people, factory):
    wo, (b1, _) = _order(people, qty=150)   # needs 150 jars, only 100 in stock
    assert wo["status"] == "waiting_material"
    assert wo["shortages"][0]["goods_code"] == "JAR" and wo["shortages"][0]["short"] == 50
    assert MaterialRequest.objects.get(wo_id=wo["wo_id"]).qty_short == 50
    assert Alert.objects.filter(kind=Alert.SHORTAGE, is_open=True, ref=wo["wo_id"]).exists()
    assert not Reservation.objects.filter(wo_id=wo["wo_id"]).exists()      # nothing held while waiting
    with pytest.raises(services.MesError, match="Waiting for material"):
        services.start_step(people["worker"], "WS-01", b1["batch_id"], _ev())
    board = services.worker_board(people["pic"].tenant_openid, "WS-01")
    assert board["queue"][0]["waiting_material"] is True
    # replenish -> released automatically, request closed, alert closed
    factory.receive(people["pic"], "JAR", 60, "RM-02", "JAR-2")
    assert materials.recheck_waiting(people["pic"].tenant_openid) == [wo["wo_id"]]
    assert mongo.db().work_orders.find_one({"wo_id": wo["wo_id"]})["status"] == "released"
    assert MaterialRequest.objects.get(wo_id=wo["wo_id"]).status == "closed"
    assert not Alert.objects.filter(kind=Alert.SHORTAGE, is_open=True).exists()


def test_receive_endpoint_releases_waiting_orders(people, factory, clients):
    wo, _ = _order(people, qty=150)
    r = clients["em"].post(f"{API}/inventory/receive", {"goods_code": "JAR", "qty": 50, "bin_name": "RM-02"},
                           format="json")
    assert r.status_code == 201 and r.json()["released_orders"] == [wo["wo_id"]]


def test_urgent_order_gets_material_first(people, factory):
    normal, _ = _order(people, qty=80, batches=1, due_date="2026-11-01")
    assert normal["status"] == "released"            # takes 80 of 100 jars
    urgent, _ = services.create_work_order(people["pic"], {"product_code": "HC-50", "qty": 60, "batches": 1,
                                                           "due_date": "2026-12-30"}, source="PIC")
    assert urgent["status"] == "waiting_material" and urgent["special_urgent"]
    late, _ = _order(people, qty=60, batches=1, due_date="2026-11-15")
    assert late["status"] == "waiting_material"
    factory.receive(people["pic"], "JAR", 60, "RM-02", "JAR-2")    # enough for only one of them
    assert materials.recheck_waiting(people["pic"].tenant_openid) == [urgent["wo_id"]]


def test_batches_consume_reserved_material_by_fefo(people, factory):
    wo, (b1, b2) = _order(people, qty=41, batches=2)     # 21 + 20 pieces
    w = people["worker"]
    services.start_step(w, "WS-01", b1["batch_id"], _ev())
    used = mongo.db().batches.find_one({"batch_id": b1["batch_id"]})["materials_used"]
    cream = [u for u in used if u["goods_code"] == "CREAM"]
    assert cream[0]["lot_number"] == "CR-EARLY" and sum(u["qty"] for u in cream) == 1050
    services.finish_step(w, "WS-01", 21, _ev())
    services.start_step(w, "WS-01", b2["batch_id"], _ev())
    res = Reservation.objects.get(wo_id=wo["wo_id"], goods_code="CREAM")
    assert res.qty_consumed == res.qty_reserved == 2050
    assert Movement.objects.filter(kind=Movement.ISSUE, ref=b1["batch_id"]).count() >= 2


def _run_all_steps(people, batch, good):
    w = people["worker"]
    for n in range(1, 7):
        services.start_step(w, f"WS-{n:02d}", batch["batch_id"], _ev())
        services.finish_step(w, f"WS-{n:02d}", good, _ev())


def test_put_away_into_suggested_finished_goods_bin(people, factory):
    wo, (batch,) = _order(people, qty=10, batches=1)
    _run_all_steps(people, batch, 10)
    board = services.worker_board(people["pic"].tenant_openid, "WS-06")
    assert board["putaway"]["suggested_bin"] == "FG-01"
    with pytest.raises(services.MesError, match="QA"):
        services.put_away(people["worker"], "WS-06", "QA-01", _ev())
    services.put_away(people["worker"], "WS-06", "FG-01", _ev())
    lot = StockLot.objects.get(goods_code="HC-50", lot_number=batch["batch_id"])
    assert lot.qty == 10 and lot.bin_name == "FG-01" and lot.expiry_date == date.today() + timedelta(days=365)
    assert mongo.db().work_orders.find_one({"wo_id": wo["wo_id"]})["status"] == "done"
    from inventory.services import suggest_fg_bin
    assert suggest_fg_bin(people["pic"].tenant_openid) == "FG-02"


def test_direct_order_ships_after_qc(people, factory):
    wo, (batch,) = _order(people, qty=10, batches=1, ship_mode="direct", client="Clinic A")
    _run_all_steps(people, batch, 9)
    ship = Shipment.objects.get(ref=batch["batch_id"])
    assert ship.source == "direct" and ship.client == "Clinic A" and ship.lines[0]["qty"] == 9
    assert mongo.db().work_orders.find_one({"wo_id": wo["wo_id"]})["status"] == "done"


def test_shipping_never_takes_reserved_material(people, factory, clients):
    _order(people, qty=80, batches=1)       # reserves 80 of 100 jars
    r = clients["em"].post(f"{API}/inventory/shipments", {"client": "X", "lines": [{"goods_code": "JAR", "qty": 30}]},
                           format="json")
    assert r.status_code == 400 and "20" in r.json()["detail"]
    ok = clients["em"].post(f"{API}/inventory/shipments", {"client": "X", "lines": [{"goods_code": "JAR", "qty": 20}]},
                            format="json")
    assert ok.status_code == 201


def test_cycle_count_variance_needs_pic(people, factory, clients):
    r = clients["em"].post(f"{API}/inventory/counts", {"bin_name": "RM-01", "goods_code": "JAR", "lot_number": "JAR-1",
                                                        "counted_qty": 97}, format="json").json()
    assert r["variance"] == -3
    assert CountTask.objects.get(pk=r["id"]).status == "pending"
    assert clients["em"].post(f"{API}/inventory/counts/{r['id']}/decision", {"approve": True},
                              format="json").status_code == 403
    assert clients["pic"].post(f"{API}/inventory/counts/{r['id']}/decision", {"approve": True},
                               format="json").status_code == 200
    assert StockLot.objects.get(bin_name="RM-01", goods_code="JAR").qty == 97
    assert Movement.objects.get(kind=Movement.ADJUST).qty == -3


def test_legacy_stock_writes_are_blocked(clients):
    assert clients["em"].post("/asn/list/", {}, format="json").status_code == 410
    assert clients["em"].post("/stock/recordlot/", {}, format="json").status_code == 410


def test_vision_fail_becomes_scrap(people, factory, clients):
    wo, (batch,) = _order(people, qty=10, batches=1)
    for n in range(1, 6):
        services.start_step(people["worker"], f"WS-{n:02d}", batch["batch_id"], _ev())
        services.finish_step(people["worker"], f"WS-{n:02d}", 10, _ev())
    services.start_step(people["worker"], "WS-06", batch["batch_id"], _ev())
    body = {"event_id": "v1", "device_id": "CAM", "workstation": "WS-06", "result": "FAIL", "reason": "Cap missing"}
    assert clients["anon"].post(f"{API}/gateway/vision", body, format="json", **GW).json()["scrap"] is True
    assert clients["anon"].post(f"{API}/gateway/vision", body, format="json", **GW).json() == {"duplicate": True}
    clients["anon"].post(f"{API}/gateway/vision", {**body, "event_id": "v2", "result": "PASS"}, format="json", **GW)
    wip = mongo.db().wip.find_one({"batch_id": batch["batch_id"], "step_code": "QC"})
    assert wip["scrap_qty"] == 1
    ev = mongo.db().step_events.find_one({"type": "scrap", "reason_code": "VISION"})
    assert ev["source"] == "camera" and ev["note"] == "Cap missing"


def test_rack_camera_mismatch_raises_and_clears_alert(people, factory):
    devices.record_rack_report("r1", "RACK", "RM-01", "EMPTY")
    assert Alert.objects.filter(kind=Alert.RACK, is_open=True, ref="RM-01").exists()
    devices.record_rack_report("r2", "RACK", "RM-01", "JAR")
    assert not Alert.objects.filter(kind=Alert.RACK, is_open=True).exists()
    devices.record_rack_report("r3", "RACK", "FG-01", "OCCUPIED")
    assert Alert.objects.filter(kind=Alert.RACK, is_open=True, ref="FG-01").exists()


def test_spc_alarm_on_out_of_control_reading(people, factory):
    wo, (batch,) = _order(people, qty=10, batches=1)
    w = people["worker"]
    services.start_step(w, "WS-01", batch["batch_id"], _ev())
    services.finish_step(w, "WS-01", 10, _ev())
    services.start_step(w, "WS-02", batch["batch_id"], _ev())
    import random
    random.seed(4)
    for _ in range(25):
        services.record_measurement(w, "WS-02", round(random.gauss(50.0, 0.2), 2), _ev())
    assert not Alert.objects.filter(kind=Alert.SPC).exists()
    res = services.record_measurement(w, "WS-02", 53.0, _ev())
    assert res["spc_alarm"] is True
    assert Alert.objects.filter(kind=Alert.SPC, is_open=True).exists()
    data = lean.spc(people["pic"].tenant_openid, "FILL")
    assert data["ucl"] > 50 > data["lcl"] and data["cpk"] is not None


def test_lean_summary(people, factory, clients):
    wo, (batch,) = _order(people, qty=10, batches=1)
    w = people["worker"]
    services.start_step(w, "WS-01", batch["batch_id"], _ev())
    services.record_scrap(w, "WS-01", 2, "SPILL", _ev())
    services.record_scrap(w, "WS-01", 1, "LEAK", _ev())
    services.finish_step(w, "WS-01", 7, _ev())
    data = clients["em"].get(f"{API}/lean/summary").json()
    mix = next(r for r in data["oee"] if r["workstation"] == "WS-01")
    assert mix["quality"] == 70.0 and mix["oee"] is not None
    assert [p["reason_code"] for p in data["pareto"]] == ["SPILL", "LEAK"]
    assert data["pareto"][-1]["cum_pct"] == 100.0
    assert data["yields"]["steps"][0]["fpy"] == 70.0 and data["yields"]["dpmo"] == 300000
    assert clients["worker"].get(f"{API}/lean/summary").status_code == 403


def test_recipes_editable_by_pic_and_em_only(people, factory, clients):
    body = {"goods_code": "HC-50", "shelf_life_days": 400, "recipe": [{"material_code": "JAR", "qty_per_piece": 1}]}
    assert clients["em"].post(f"{API}/inventory/products", body, format="json").status_code == 201
    assert clients["worker"].post(f"{API}/inventory/products", body, format="json").status_code == 403
    assert AuditLog.objects.filter(action="product.update", actor_role="EM").exists()


def test_product_routing_skips_a_step(people, factory):
    factory.save_product(people["pic"], {"goods_code": "HC-50", "routing": ["MIX", "FILL", "CAP", "PACK", "QC"],
                                         "recipe": []})
    wo, (batch,) = _order(people, qty=5, batches=1)
    assert [s["code"] for s in wo["routing"]] == ["MIX", "FILL", "CAP", "PACK", "QC"]
    w = people["worker"]
    for ws in ["WS-01", "WS-02", "WS-03"]:
        services.start_step(w, ws, batch["batch_id"], _ev())
        services.finish_step(w, ws, 5, _ev())
    with pytest.raises(services.MesError, match="PACK"):
        services.start_step(w, "WS-04", batch["batch_id"], _ev())       # labelling skipped
    services.start_step(w, "WS-05", batch["batch_id"], _ev())


def test_industry_switch_is_pic_only(clients):
    assert clients["em"].post(f"{API}/settings/industry", {"code": "food_beverage"}, format="json").status_code == 403
    r = clients["pic"].post(f"{API}/settings/industry", {"code": "food_beverage"}, format="json")
    assert r.status_code == 200
    assert clients["em"].get(f"{API}/settings/industry").json()["current"] == "food_beverage"
    clients["pic"].post(f"{API}/settings/industry", {"code": "cosmetics"}, format="json")
