"""Phase 5: ERP connectors against the mock ERP server (real HTTP), inbox, outbox, Workday."""
import sys
import threading
import uuid
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from accounts.models import Account
from core import mongo, secrets
from inventory.models import Alert
from integrations import erp_sync
from integrations.connectors import ErpError, for_connection
from integrations.models import ErpConnection
from mes import services as mes

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import mock_erp  # noqa: E402

pytestmark = pytest.mark.django_db


@pytest.fixture(scope="module")
def erp_url():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), mock_erp.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def _conn(people, url, system="SAP", password="mock123"):
    return ErpConnection.objects.create(tenant_openid=people["pic"].tenant_openid, name=f"{system} test", system=system,
                                        base_url=url, username="mock", secret_enc=secrets.encrypt(password), enabled=True)


def test_sap_pull_imports_valid_orders_and_holds_the_rest(people, factory, erp_url):
    conn = _conn(people, erp_url)
    out = erp_sync.pull_orders(conn)
    assert out["received"] == 3 and len(out["imported"]) == 1 and sorted(out["inbox"]) == ["1000452", "1000453"]
    wo = mongo.db().work_orders.find_one({"erp_ref": "1000451"})
    assert wo["source"] == "ERP" and wo["qty"] == 1200 and wo["client_priority"] == 2 and not wo["special_urgent"]
    assert mongo.db().batches.count_documents({"wo_id": wo["wo_id"]}) == 2          # 1000-piece batches
    assert Alert.objects.filter(kind="ERP_INBOX", is_open=True).exists()
    again = erp_sync.pull_orders(conn)
    assert again["skipped"] == 3 and not again["imported"]                          # never imported twice


def test_inbox_approve_with_edit_and_reject(people, factory, erp_url, clients):
    conn = _conn(people, erp_url)
    erp_sync.pull_orders(conn)
    r = clients["pic"].post("/api/v1/integrations/erp-inbox", {"erp_ref": "1000452", "conn_id": conn.pk, "approve": True,
                                                               "edits": {"product_code": "HC-50"}}, format="json")
    assert r.status_code == 200 and mongo.db().work_orders.find_one({"wo_id": r.json()["wo_id"]})["erp_ref"] == "1000452"
    bad = clients["pic"].post("/api/v1/integrations/erp-inbox", {"erp_ref": "1000453", "conn_id": conn.pk,
                                                                 "approve": True}, format="json")
    assert bad.status_code == 400 and "goods list" in bad.json()["detail"]
    clients["pic"].post("/api/v1/integrations/erp-inbox", {"erp_ref": "1000453", "conn_id": conn.pk, "approve": False},
                        format="json")
    assert mongo.db().erp_inbox.find_one({"erp_ref": "1000453"})["status"] == "rejected"
    assert clients["em"].get("/api/v1/integrations/erp-inbox").status_code == 403


def test_oracle_pull(people, factory, erp_url):
    out = erp_sync.pull_orders(_conn(people, erp_url, "ORACLE"))
    assert out["received"] == 1 and out["inbox"] == ["WO-ORA-7781"]      # SR-30 not in this test's goods list


def test_results_go_back_to_the_erp(people, factory, erp_url):
    conn = _conn(people, erp_url)
    mock_erp.RECEIVED.clear()
    from inventory.services import create_bin
    create_bin(people["pic"], "FG-09", "FG")
    erp_sync.pull_orders(conn)
    wo = mongo.db().work_orders.find_one({"erp_ref": "1000451"})
    w = people["worker"]
    factory.receive(people["pic"], "JAR", 2000, "RM-02", "JAR-B")
    factory.receive(people["pic"], "CREAM", 60000, "RM-02", "CR-B")
    from mes.materials import recheck_waiting
    recheck_waiting(people["pic"].tenant_openid)
    for b in mongo.db().batches.find({"wo_id": wo["wo_id"]}):
        for n in range(1, 7):
            mes.start_step(w, f"WS-{n:02d}", b["batch_id"], uuid.uuid4().hex)
            if n == 2:                                   # 3 spilled at filling; 597 good from then on
                mes.record_scrap(w, "WS-02", 3, "SPILL", uuid.uuid4().hex)
            mes.finish_step(w, f"WS-{n:02d}", b["qty"] - (3 if n >= 2 else 0), uuid.uuid4().hex)
        mes.put_away(w, "WS-06", "FG-09", uuid.uuid4().hex)
    item = mongo.db().erp_outbox.find_one({"wo_id": wo["wo_id"]})
    assert item and item["status"] == "pending" and item["result"]["scrap_by_reason"] == {"SPILL": 6}
    assert erp_sync.push_outbox(people["pic"].tenant_openid) == {"sent": 1, "failed": 0}
    sent = mongo.db().erp_outbox.find_one({"wo_id": wo["wo_id"]})
    assert sent["status"] == "sent" and sent["erp_confirmation"].startswith("CONF-")
    body = mock_erp.RECEIVED[-1]["body"]
    assert body["ManufacturingOrder"] == "1000451" and body["ConfirmationYieldQuantity"] == "1194"


def test_outbox_retries_and_alerts(people, erp_url):
    conn = _conn(people, erp_url, password="wrong")
    mongo.db().erp_outbox.insert_one({"tenant_openid": people["pic"].tenant_openid, "wo_id": "WO-X", "conn_id": conn.pk,
                                      "result": {"erp_ref": "1", "good_qty": 1, "scrap_qty": 0, "batch_ids": [],
                                                 "finished_at": "2026-10-19T10:00:00", "text": "x"},
                                      "status": "pending", "attempts": 0,
                                      "created_at": datetime.now(timezone.utc) - timedelta(hours=2)})
    assert erp_sync.push_outbox(people["pic"].tenant_openid) == {"sent": 0, "failed": 1}
    item = mongo.db().erp_outbox.find_one({"wo_id": "WO-X"})
    assert item["attempts"] == 1 and "refused" in item["last_error"]
    assert Alert.objects.filter(kind="ERP_OUTBOX", is_open=True).exists()


def test_wrong_password_is_reported(people, erp_url):
    with pytest.raises(ErpError, match="refused the sign-in"):
        for_connection(_conn(people, erp_url, password="bad")).ping()


def test_workday_creates_renames_disables_workers_only(people, erp_url):
    t = people["pic"].tenant_openid
    Account.objects.create(tenant_openid=t, staff_id="1006", display_name="Old name", role="WORKER", source="workday")
    Account.objects.filter(pk=people["pic"].pk).update(staff_id="1002")       # a PIC who is also in the HR report
    res = erp_sync.import_staff(_conn(people, erp_url, "WORKDAY"))
    assert res["created"] == 1                      # only 1007; 1002 already exists as the PIC and is not touched
    assert Account.objects.get(tenant_openid=t, staff_id="1007").role == "WORKER"
    assert Account.objects.get(tenant_openid=t, staff_id="1001").display_name == "Chan Tai Man"
    assert not Account.objects.get(tenant_openid=t, staff_id="1006").is_active
    pic = Account.objects.get(pk=people["pic"].pk)
    assert pic.role == "PIC" and pic.display_name == "PIC" and pic.is_active
