"""Phase 4: anonymiser, agent jobs (with a fake AI), chat tool loop, API keys, integrations, search, SOPs."""
import io
import json

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from agent import chat, jobs, llm, search, sop
from agent.anonymise import Anonymiser
from core import mongo
from integrations.models import AiProvider
from mes import services as mes

pytestmark = pytest.mark.django_db
API = "/api/v1"


class FakeAI:
    """Stands in for the provider's /chat/completions; records what was sent."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.sent = []

    def __call__(self, url, json=None, headers=None, timeout=None):     # noqa: A002 - mirrors requests.post
        self.sent.append(json)
        reply = self.replies.pop(0) if self.replies else {"content": "ok"}

        class R:
            status_code = 200

            def json(self_inner):
                return {"choices": [{"message": reply, "finish_reason": "stop"}],
                        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}
        return R()


def _key(people, cap=300):
    from core import secrets
    AiProvider.objects.update_or_create(tenant_openid=people["pic"].tenant_openid,
                                        defaults={"api_key_enc": secrets.encrypt("sk-test"), "daily_call_cap": cap})


def test_anonymiser_hides_and_restores(people):
    a = Anonymiser(people["pic"].tenant_openid)
    out = a.apply({"client": "Demo Clinic", "staff_id": "1001", "goods_price": 12.5, "note": "Demo Clinic called",
                   "qty": 5})
    assert out["client"] == "Client A" and "price" not in json.dumps(out) and out["qty"] == 5
    assert out["staff_id"].startswith("Worker ") and "Demo Clinic" not in json.dumps(out)
    assert a.restore("Call Client A today") == "Call Demo Clinic today"


def test_jobs_work_without_ai(people, factory):
    mes.create_work_order(people["pic"], {"product_code": "HC-50", "qty": 500, "due_date": "2026-12-01",
                                          "client": "Demo Clinic"}, source="ERP")     # waits for material
    res = jobs.run_job(people["pic"].tenant_openid, "work_orders")
    assert res["source"] == "rules" and res["findings"] == 1
    adv = mongo.db().advice.find_one({"status": "open"})
    assert "cannot start" in adv["title"] and adv["title_zh"]


def test_advice_expires_when_no_longer_true(people, factory):
    wo, _ = mes.create_work_order(people["pic"], {"product_code": "HC-50", "qty": 150, "due_date": "2026-12-01"},
                                  source="ERP")
    jobs.run_job(people["pic"].tenant_openid, "work_orders")
    factory.receive(people["pic"], "JAR", 100, "RM-02", "JAR-9")
    from mes.materials import recheck_waiting
    recheck_waiting(people["pic"].tenant_openid)
    jobs.run_job(people["pic"].tenant_openid, "work_orders")
    assert mongo.db().advice.find_one({"key": f"wo-short:{wo['wo_id']}"})["status"] == "expired"


def test_ai_receives_only_anonymised_data(people, factory, monkeypatch):
    _key(people)
    mes.create_work_order(people["pic"], {"product_code": "HC-50", "qty": 500, "due_date": "2026-12-01",
                                          "client": "Demo Clinic"}, source="ERP")
    fake = FakeAI([{"content": json.dumps({"items": []})}])
    monkeypatch.setattr(llm.requests, "post", fake)
    res = jobs.run_job(people["pic"].tenant_openid, "work_orders")
    assert res["source"] == "ai"
    sent = json.dumps(fake.sent)
    assert "Demo Clinic" not in sent and "Client A" in sent
    assert fake.sent[0]["thinking"] == {"type": "disabled"} and fake.sent[0]["model"] == "deepseek-v4-pro"


def test_daily_cap_switches_to_plain_calculation(people, factory, monkeypatch):
    _key(people, cap=0)
    ok, why = llm.available(people["pic"].tenant_openid)
    assert not ok and "limit" in why


def test_chat_uses_tools_then_answers(people, factory, monkeypatch):
    _key(people)
    mes.create_work_order(people["pic"], {"product_code": "HC-50", "qty": 20, "due_date": "2026-12-01",
                                          "client": "Demo Clinic"}, source="ERP")
    fake = FakeAI([
        {"content": "", "tool_calls": [{"id": "c1", "type": "function",
                                        "function": {"name": "list_orders", "arguments": "{}"}}]},
        {"content": "One open order for Client A, due 2026-12-01."},
    ])
    monkeypatch.setattr(llm.requests, "post", fake)
    r = chat.ask(people["em"], "Which orders are open?")
    assert [t["tool"] for t in r["tools"]] == ["list_orders"]
    assert r["a"] == "One open order for Demo Clinic, due 2026-12-01."           # restored locally
    tool_msg = next(m for m in fake.sent[1]["messages"] if m["role"] == "tool")
    assert "Demo Clinic" not in tool_msg["content"] and "Client A" in tool_msg["content"]


def test_chat_offline_without_key(people, clients):
    r = clients["em"].post(f"{API}/agent/chat", {"question": "hello"}, format="json").json()
    assert r["a"].startswith("Advisor offline")
    assert clients["worker"].post(f"{API}/agent/chat", {"question": "hi"}, format="json").status_code == 403


def test_advice_decisions_are_for_people(people, factory, clients):
    mes.create_work_order(people["pic"], {"product_code": "HC-50", "qty": 500, "due_date": "2026-12-01"}, source="ERP")
    jobs.run_job(people["pic"].tenant_openid, "work_orders")
    adv = mongo.db().advice.find_one({"status": "open"})
    r = clients["em"].post(f"{API}/agent/advice/{adv['advice_id']}/decision", {"accept": True, "comment": "ordering"},
                           format="json")
    assert r.status_code == 200 and r.json()["status"] == "accepted" and r.json()["decision_comment"] == "ordering"


def test_read_only_api_keys(people, clients):
    from rest_framework.test import APIClient
    r = clients["pic"].post(f"{API}/integrations/api-keys", {"name": "BI dashboard"}, format="json")
    raw = r.json()["api_key"]
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Api-Key {raw}")
    assert c.get(f"{API}/mes/progress").status_code == 200
    assert c.post(f"{API}/mes/work-orders", {"product_code": "X"}, format="json").status_code == 403
    assert c.post(f"{API}/agent/chat", {"question": "x"}, format="json").status_code == 403
    assert clients["em"].post(f"{API}/integrations/api-keys", {"name": "x"}, format="json").status_code == 403
    clients["pic"].post(f"{API}/integrations/api-keys/{r.json()['id']}/revoke", {}, format="json")
    assert c.get(f"{API}/mes/progress").status_code in (401, 403)


def test_integration_secrets_are_encrypted_and_masked(people, clients):
    r = clients["pic"].put(f"{API}/integrations/ai", {"api_key": "sk-abcdef123456", "model": "deepseek-v4-pro"},
                           format="json")
    assert r.status_code == 200 and r.json()["key_hint"] == "••••3456" and "sk-abcdef" not in json.dumps(r.json())
    row = AiProvider.objects.get(tenant_openid=people["pic"].tenant_openid)
    assert "sk-abcdef" not in row.api_key_enc and llm.provider(people["pic"].tenant_openid)["api_key"] == "sk-abcdef123456"
    e = clients["pic"].post(f"{API}/integrations/erp", {"name": "SAP prod", "system": "SAP", "base_url": "https://sap.example",
                                                        "username": "svc", "secret": "Pa55word!"}, format="json").json()
    assert e["secret_hint"] == "••••ord!"
    tested = clients["pic"].post(f"{API}/integrations/erp/{e['id']}/test", {}, format="json").json()["last_test_result"]
    assert tested.startswith("✕ Cannot reach")          # the test really connects (made-up address)
    assert clients["em"].get(f"{API}/integrations/erp").status_code == 403
    assert clients["pic"].put(f"{API}/integrations/ai", {"base_url": "http://insecure"}, format="json").status_code == 400


def test_sop_upload_is_searchable_and_removable(people, monkeypatch):
    def broken(*a, **k):
        raise RuntimeError("no search index in test")
    f = SimpleUploadedFile("SOP-FILL-03.md", "Nozzle calibration\n\nRe-calibrate the filling nozzle every 4 hours.\n\n"
                           "灌裝噴嘴每四小時校準一次。".encode(), content_type="text/markdown")
    doc = sop.upload(people["pic"], f, "Nozzle calibration")
    assert doc["chunks"] >= 1
    monkeypatch.setattr(search.coll().__class__, "aggregate", broken)      # force the simple fallback search
    hits = search.search(people["pic"].tenant_openid, "calibrate")
    assert hits and hits[0]["kind"] == "sop"
    assert search.search(people["pic"].tenant_openid, "噴嘴")
    sop.remove(people["pic"], doc["sop_id"])
    assert not search.search(people["pic"].tenant_openid, "calibrate")
    with pytest.raises(sop.SopError):
        sop.upload(people["pic"], SimpleUploadedFile("x.exe", b"MZ"))


def test_alarm_wakes_the_agent(people):
    from inventory.alerts import raise_alert
    raise_alert(people["pic"].tenant_openid, "SPC_OUT_OF_CONTROL", "SPC alarm: Fill weight", dedupe_key="spc:x")
    assert mongo.db().agent_state.find_one({"_id": people["pic"].tenant_openid})["pending"] is True


def test_system_and_api_accounts_cannot_sign_in_at_a_workstation(people, clients):
    from accounts import services as acc
    from integrations.erp_sync import system_account
    sysacct = system_account(people["pic"].tenant_openid)
    key = clients["pic"].post(f"{API}/integrations/api-keys", {"name": "x"}, format="json").json()
    from accounts.models import ApiKey
    api_acct = ApiKey.objects.get(pk=key["id"]).account
    for staff_id in (sysacct.staff_id, api_acct.staff_id):
        with pytest.raises(acc.LoginError):
            acc.worker_login(staff_id, people["device_token"])
