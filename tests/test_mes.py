import re
import uuid

import pytest

from accounts.models import AuditLog
from core import ids, mongo
from mes import services

pytestmark = pytest.mark.django_db
API = "/api/v1"


def _wo(people, **kw):
    data = {"product_code": "HC-50", "product_name": "Hand cream", "qty": 100, "batches": 1,
            "due_date": "2026-12-01", "ship_mode": "stock", **kw}
    return services.create_work_order(people["pic"], data, source=kw.pop("source", "PIC"))


def test_id_formats():
    assert re.fullmatch(r"WO-\d{8}-\d{4}", ids.new_work_order_id())
    b = ids.new_batch_id()
    assert re.fullmatch(r"B-\d{8}-\d{4}", b)
    assert ids.new_wip_id(b, 3) == f"WIP-{b}-S03-001"
    assert ids.new_wip_id(b, 3) == f"WIP-{b}-S03-002"


def test_pic_orders_are_special_urgent_and_split_into_batches(people):
    wo, batches = _wo(people, qty=101, batches=2)
    assert wo["special_urgent"] is True
    assert [b["qty"] for b in batches] == [51, 50]
    erp_wo, _ = services.create_work_order(people["pic"], {"product_code": "X", "qty": 5, "due_date": "2026-12-01"},
                                           source="ERP")
    assert erp_wo["special_urgent"] is False


def test_full_step_flow_and_wip_id(people):
    _, (batch,) = _wo(people)
    w = people["worker"]
    wip = services.start_step(w, "WS-01", batch["batch_id"], uuid.uuid4().hex)
    assert wip["wip_id"] == f"WIP-{batch['batch_id']}-S01-001"
    services.record_scrap(w, "WS-01", 4, "SPILL", uuid.uuid4().hex)
    services.machine_stop(w, "WS-01", "BREAKDOWN", uuid.uuid4().hex)
    services.machine_resume(w, "WS-01", uuid.uuid4().hex)
    with pytest.raises(services.MesError, match="more than"):
        services.finish_step(w, "WS-01", 97, uuid.uuid4().hex)
    services.finish_step(w, "WS-01", 96, uuid.uuid4().hex)
    b = mongo.db().batches.find_one({"batch_id": batch["batch_id"]})
    assert b["current_step_no"] == 2 and b["status"] == "waiting" and b["last_good_qty"] == 96
    # Step 2 receives the 96 good pieces
    wip2 = services.start_step(w, "WS-02", batch["batch_id"], uuid.uuid4().hex)
    assert wip2["qty_in"] == 96


def test_wrong_step_is_refused(people):
    _, (batch,) = _wo(people)
    with pytest.raises(services.MesError, match="step 1"):
        services.start_step(people["worker"], "WS-03", batch["batch_id"], uuid.uuid4().hex)


def test_replayed_events_count_once(people):
    _, (batch,) = _wo(people)
    w = people["worker"]
    start_id = uuid.uuid4().hex
    services.start_step(w, "WS-01", batch["batch_id"], start_id)
    services.start_step(w, "WS-01", batch["batch_id"], start_id)
    scrap_id = uuid.uuid4().hex
    services.record_scrap(w, "WS-01", 2, "LEAK", scrap_id)
    assert services.record_scrap(w, "WS-01", 2, "LEAK", scrap_id) == {"duplicate": True}
    assert mongo.db().wip.find_one({"batch_id": batch["batch_id"]})["scrap_qty"] == 2
    assert mongo.db().wip.count_documents({"batch_id": batch["batch_id"]}) == 1


def test_scrap_rules(people):
    _, (batch,) = _wo(people)
    w = people["worker"]
    services.start_step(w, "WS-01", batch["batch_id"], uuid.uuid4().hex)
    with pytest.raises(services.MesError, match="camera"):
        services.record_scrap(w, "WS-01", 1, "VISION", uuid.uuid4().hex)
    with pytest.raises(services.MesError, match="note"):
        services.record_scrap(w, "WS-01", 1, "OTHER", uuid.uuid4().hex)
    with pytest.raises(services.MesError, match="reason"):
        services.record_scrap(w, "WS-01", 1, "NOPE", uuid.uuid4().hex)


def test_worker_board_hides_scrap(people, clients):
    _, (batch,) = _wo(people)
    clients["worker"].post(f"{API}/mes/workstations/WS-01/start", {"batch_id": batch["batch_id"]}, format="json")
    r = clients["worker"].post(f"{API}/mes/workstations/WS-01/scrap", {"qty": 3, "reason_code": "SPILL"}, format="json")
    assert r.json() == {"recorded": True}
    board = clients["worker"].get(f"{API}/mes/workstations/WS-01/board").json()
    assert "scrap_qty" not in board["current"]
    assert board["current"]["expected_good"] == board["current"]["qty_in"] - 3
    assert clients["worker"].get(f"{API}/mes/events").status_code == 403


def test_only_pic_edits_wip_and_it_is_audited(people, clients):
    _, (batch,) = _wo(people)
    w = people["worker"]
    wip = services.start_step(w, "WS-01", batch["batch_id"], uuid.uuid4().hex)
    services.finish_step(w, "WS-01", 100, uuid.uuid4().hex)
    url = f"{API}/mes/wip/{wip['wip_id']}"
    body = {"changes": {"good_qty": 98}, "reason": "Recount"}
    assert clients["em"].patch(url, body, format="json").status_code == 403
    assert clients["worker"].patch(url, body, format="json").status_code == 403
    assert clients["pic"].patch(url, {"changes": {"good_qty": 98}, "reason": ""}, format="json").status_code == 400
    r = clients["pic"].patch(url, body, format="json")
    assert r.status_code == 200 and r.json()["good_qty"] == 98 and r.json()["edited_by_pic"]
    entry = AuditLog.objects.get(action="wip.edit")
    assert entry.before == {"good_qty": 100} and entry.after == {"good_qty": 98} and entry.reason == "Recount"


def test_pic_scrap_edit_updates_wip_total(people):
    _, (batch,) = _wo(people)
    w = people["worker"]
    services.start_step(w, "WS-01", batch["batch_id"], uuid.uuid4().hex)
    ev = uuid.uuid4().hex
    services.record_scrap(w, "WS-01", 5, "SPILL", ev)
    services.pic_edit_event(people["pic"], ev, {"qty": 2}, "Miscount")
    assert mongo.db().wip.find_one({"batch_id": batch["batch_id"]})["scrap_qty"] == 2


def test_last_step_completes_batch_and_work_order(people):
    wo, (batch,) = _wo(people, qty=10)
    w = people["worker"]
    for n in range(1, 7):
        services.start_step(w, f"WS-{n:02d}", batch["batch_id"], uuid.uuid4().hex)
        services.finish_step(w, f"WS-{n:02d}", 10, uuid.uuid4().hex)
    assert mongo.db().batches.find_one({"batch_id": batch["batch_id"]})["status"] == "awaiting_putaway"
    from inventory.services import create_bin
    create_bin(people["pic"], "FG-01", "FG")
    services.put_away(w, "WS-06", "FG-01", uuid.uuid4().hex)
    assert mongo.db().batches.find_one({"batch_id": batch["batch_id"]})["status"] == "done"
    assert mongo.db().work_orders.find_one({"wo_id": wo["wo_id"]})["status"] == "done"
    prog = services.progress_overview(people["pic"].tenant_openid)
    assert prog[0]["progress_pct"] == 100.0


def test_gateway_requires_token_and_dedupes(clients):
    payload = {"event_id": "e1", "device_id": "SCN-01", "workstation": "WS-01", "code": "B-1"}
    assert clients["anon"].post(f"{API}/gateway/scans", payload, format="json").status_code in (401, 403)
    ok = clients["anon"].post(f"{API}/gateway/scans", payload, format="json", HTTP_X_GATEWAY_TOKEN="test-gateway-token")
    assert ok.json() == {"recorded": True}
    again = clients["anon"].post(f"{API}/gateway/scans", payload, format="json", HTTP_X_GATEWAY_TOKEN="test-gateway-token")
    assert again.json() == {"duplicate": True}


def test_scan_feed_open_to_own_registered_device_only(people, clients):
    services.record_gateway_scan("e-badge", "SCN-01", "WS-01", "1001")
    url = f"{API}/mes/workstations/WS-01/scans"
    assert clients["anon"].get(url).status_code == 403
    assert clients["anon"].get(url, HTTP_X_DEVICE_TOKEN="wrong").status_code == 403
    ok = clients["anon"].get(url, HTTP_X_DEVICE_TOKEN=people["device_token"])
    assert ok.status_code == 200 and ok.json()[0]["code"] == "1001"
    other = clients["anon"].get(f"{API}/mes/workstations/WS-02/scans", HTTP_X_DEVICE_TOKEN=people["device_token"])
    assert other.status_code == 403


def test_station_status_lists_every_workstation(people, clients):
    _, (batch,) = _wo(people)
    services.start_step(people["worker"], "WS-01", batch["batch_id"], uuid.uuid4().hex)
    data = clients["em"].get(f"{API}/mes/station-status").json()
    assert [w["code"] for w in data] == [f"WS-{n:02d}" for n in range(1, 7)]
    assert data[0]["running"]["batch_id"] == batch["batch_id"]
    assert clients["worker"].get(f"{API}/mes/station-status").status_code == 403
