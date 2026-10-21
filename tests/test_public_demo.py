"""Public website demo mode (PUBLIC_DEMO=1): one-click sign-in, refused settings, AI cap, daily reset."""
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from rest_framework.test import APIClient

from accounts.models import Account, Device
from core import mongo

API = "/api/v1"


@pytest.fixture
def demo_on(monkeypatch):
    monkeypatch.setenv("PUBLIC_DEMO", "1")


@pytest.fixture
def demo_company(db, monkeypatch):
    monkeypatch.setenv("DEMO_PIC_PASSWORD", "unused-Pic#2026x")
    monkeypatch.setenv("DEMO_EM_PASSWORD", "unused-Em#2026xx")
    call_command("seed_demo", "--no-orders", verbosity=0)


def _signed_in(res):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {res.json()['token']}")
    return c


def test_off_by_default(demo_company):
    c = APIClient()
    assert c.get(f"{API}/auth/public-demo").json() == {"enabled": False}
    assert c.post(f"{API}/auth/demo-login", {"role": "pic"}, format="json").status_code == 404


def test_one_click_sign_in_for_each_role(demo_on, demo_company):
    c = APIClient()
    info = c.get(f"{API}/auth/public-demo").json()
    assert info["enabled"] and info["ai_daily_calls"] == 30 and info["workstations"][0]["code"] == "WS-01"
    for role, expected in (("pic", "PIC"), ("em", "EM")):
        res = c.post(f"{API}/auth/demo-login", {"role": role}, format="json")
        assert res.status_code == 200 and res.json()["account"]["role"] == expected
        assert _signed_in(res).get(f"{API}/auth/me").status_code == 200
    res = c.post(f"{API}/auth/demo-login", {"role": "worker", "workstation": "WS-03"}, format="json")
    body = res.json()
    assert body["account"]["staff_id"] == "1001" and body["device"]["workstation"] == "WS-03"
    assert c.get(f"{API}/devices/current", HTTP_X_DEVICE_TOKEN=body["device_token"]).json()["workstation"] == "WS-03"
    # The same tablet is reused, not one new device per click
    c.post(f"{API}/auth/demo-login", {"role": "worker", "workstation": "WS-03"}, format="json")
    assert Device.objects.filter(workstation="WS-03").count() == 1
    assert c.post(f"{API}/auth/demo-login", {"role": "worker", "workstation": "WS-99"}, format="json").status_code == 404
    assert c.post(f"{API}/auth/demo-login", {"role": "AGENT"}, format="json").status_code == 404


def test_risky_settings_are_refused_but_reading_works(demo_on, demo_company):
    pic = _signed_in(APIClient().post(f"{API}/auth/demo-login", {"role": "pic"}, format="json"))
    for path, body in ((f"{API}/integrations/api-keys", {"name": "x"}),
                       (f"{API}/integrations/ai", {"base_url": "http://169.254.169.254"}),
                       (f"{API}/integrations/erp", {"kind": "sap"}),
                       (f"{API}/accounts", {"role": "PIC"}),
                       (f"{API}/devices", {"name": "x", "workstation": "WS-01"}),
                       (f"{API}/sop", {}),
                       ("/staff/", {"staff_name": "x"})):
        r = pic.post(path, body, format="json")
        assert r.status_code == 403 and "public demo" in r.json()["detail"], path
    assert pic.get(f"{API}/integrations/ai").status_code == 200
    assert pic.get(f"{API}/accounts").status_code == 200
    # Production work is allowed
    r = pic.post(f"{API}/mes/work-orders", {"product_code": "HC-50", "product_name": "Hand cream", "qty": 10,
                                           "batches": 1, "due_date": "2026-12-01", "ship_mode": "stock"}, format="json")
    assert r.status_code in (200, 201), r.content


def test_ai_cap_cannot_be_raised_in_demo(demo_on, demo_company):
    from agent import llm
    from integrations.models import AiProvider
    tenant = Account.objects.get(staff_id="P001").tenant_openid
    AiProvider.objects.create(tenant_openid=tenant, daily_call_cap=5000)
    assert llm.provider(tenant)["daily_call_cap"] == 30


def test_reset_refused_outside_demo(demo_company):
    with pytest.raises(CommandError, match="PUBLIC_DEMO"):
        call_command("public_demo_reset")


@pytest.mark.django_db(transaction=True)
def test_reset_wipes_visitor_changes_and_rebuilds(demo_on, monkeypatch):
    from core.management.commands import public_demo_reset as cmd
    real_get = cmd.config.get
    monkeypatch.setattr(cmd.config, "get", lambda k, d=None: 3 if k == "public_demo.history_days" else real_get(k, d))
    mongo.db().llm_usage.insert_one({"_id": "x", "calls": 7})
    call_command("public_demo_reset", verbosity=0)
    wo_before = mongo.db().work_orders.count_documents({})
    assert wo_before > 0 and Device.objects.filter(name__startswith="Public demo tablet").count() == 6
    mongo.db().work_orders.insert_one({"wo_id": "WO-VISITOR", "tenant_openid": "t"})
    Account.objects.create(tenant_openid="t", staff_id="9999", display_name="Visitor", role="WORKER")
    call_command("public_demo_reset", "--if-stale", verbosity=0)          # fresh: nothing happens
    assert mongo.db().work_orders.find_one({"wo_id": "WO-VISITOR"})
    call_command("public_demo_reset", verbosity=0)
    assert not mongo.db().work_orders.find_one({"wo_id": "WO-VISITOR"})
    assert not Account.objects.filter(staff_id="9999").exists()
    assert mongo.db().llm_usage.find_one({"_id": "x"})["calls"] == 7   # reset never lifts the AI cap
    pic = APIClient().post(f"{API}/auth/demo-login", {"role": "pic"}, format="json")
    assert pic.status_code == 200
