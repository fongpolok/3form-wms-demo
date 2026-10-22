"""Phase 3: calendar, scheduling engine, plan workflow, permissions, triggers."""
import uuid
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from aps import calendar as cal
from aps import engine, service
from aps.models import Holiday, StaffingOverride
from core import mongo
from inventory.models import Alert
from mes import services as mes

HKT = ZoneInfo("Asia/Hong_Kong")
SHIFTS = [{"code": "A", "start": "08:00", "end": "16:00", "break_start": "12:00", "break_minutes": 45, "workers": 6}]
API = "/api/v1"


def _monday(hour=8):
    d = date(2026, 11, 2)          # a Monday, not a holiday
    return datetime(d.year, d.month, d.day, hour, tzinfo=HKT)


def _slots(start=None, workers=None, days=2, **kw):
    shifts = [dict(SHIFTS[0], workers=workers)] if workers is not None else SHIFTS
    return cal.build(start or _monday(), days=days, slot_minutes=5, shifts=shifts, working_days=[0, 1, 2, 3, 4, 5],
                     holidays=kw.get("holidays", {}), staffing=kw.get("staffing", {}))


def _job(bid, minutes, product="P", urgent=False, due="2026-11-10", prio=3, steps=("MIX", "FILL")):
    return engine.Job(bid, f"WO-{bid}", product, urgent, due, prio, "2026-11-01", [
        {"step_no": i, "step_code": c, "minutes": minutes} for i, c in enumerate(steps, 1)])


# ----------------------------------------------------------------- calendar
def test_calendar_breaks_holidays_and_staffing():
    slots = _slots(holidays={date(2026, 11, 3): "Factory day off"}, staffing={(date(2026, 11, 2), "A"): 2})
    by_time = {s.start.strftime("%a %H:%M"): s for s in slots}
    assert by_time["Mon 08:00"].working and by_time["Mon 08:00"].workers == 2
    assert not by_time["Mon 12:00"].working and not by_time["Mon 12:40"].working and by_time["Mon 12:45"].working
    assert not by_time["Mon 16:00"].working
    assert not any(s.working for s in slots if s.start.date() == date(2026, 11, 3))


def test_planned_minutes_skip_sundays_and_holidays(db):
    Holiday.objects.create(date=date(2026, 11, 4), name="Test")
    # Mon 2 - Sun 8 Nov 2026: 6 working days minus 1 holiday = 5 days x 2 shifts x (480 - 45) min
    assert cal.planned_minutes(date(2026, 11, 2), date(2026, 11, 8)) == 5 * 2 * 435


# ------------------------------------------------------------------- engine
STATIONS = {"WS-01": "MIX", "WS-02": "FILL"}


def test_steps_run_in_order_and_never_overlap():
    res = engine.schedule(_slots(), STATIONS, [_job("A", 60), _job("B", 60)], [], 5, 0)
    ops = {(o["batch_id"], o["step_code"]): o for o in res.ops}
    assert ops[("A", "FILL")]["start"] >= ops[("A", "MIX")]["end"]
    for ws in STATIONS:
        mine = sorted((o for o in res.ops if o["workstation"] == ws), key=lambda o: o["start"])
        assert all(a["end"] <= b["start"] for a, b in zip(mine, mine[1:]))


def test_priority_urgent_then_due_date_then_client_priority():
    jobs = [_job("late-due", 30, due="2026-11-20"), _job("early-due", 30, due="2026-11-05"),
            _job("urgent", 30, urgent=True, due="2026-11-30"), _job("vip", 30, due="2026-11-20", prio=1)]
    res = engine.schedule(_slots(), STATIONS, jobs, [], 5, 0)
    mix = [o["batch_id"] for o in sorted(res.ops, key=lambda o: o["start"]) if o["step_code"] == "MIX"]
    assert mix == ["urgent", "early-due", "vip", "late-due"]


def test_changeover_only_when_product_changes():
    jobs = [_job("A", 30, product="X"), _job("B", 30, product="X"), _job("C", 30, product="Y")]
    res = engine.schedule(_slots(), STATIONS, jobs, [], 5, 20)
    mix = {o["batch_id"]: o for o in res.ops if o["step_code"] == "MIX"}
    assert mix["A"]["setup_minutes"] == 0 and mix["B"]["setup_minutes"] == 0 and mix["C"]["setup_minutes"] == 20


def test_work_pauses_over_the_break():
    res = engine.schedule(_slots(start=_monday(11)), {"WS-01": "MIX"}, [_job("A", 120, steps=("MIX",))], [], 5, 0)
    op = res.ops[0]
    assert op["start"].astimezone(HKT).strftime("%H:%M") == "11:00"
    assert op["end"].astimezone(HKT).strftime("%H:%M") == "13:45"     # 2 h of work + 45 min break


def test_worker_limit_keeps_stations_idle():
    jobs = [_job("A", 60, steps=("MIX",)), _job("B", 60, steps=("FILL",))]
    two = engine.schedule(_slots(workers=2), STATIONS, jobs, [], 5, 0)
    one = engine.schedule(_slots(workers=1), STATIONS, jobs, [], 5, 0)
    assert two.ops[0]["start"] == two.ops[1]["start"]                # both run together
    a, b = sorted(one.ops, key=lambda o: o["start"])
    assert b["start"] >= a["end"]                                     # one person: one station at a time


def test_fixed_running_op_blocks_its_station():
    t0 = _monday()
    fixed = [engine.Fixed("WS-01", "R", "WO-R", "P", 1, "MIX", t0, t0 + timedelta(hours=1), "running")]
    res = engine.schedule(_slots(), {"WS-01": "MIX"}, [_job("A", 30, steps=("MIX",))], fixed, 5, 0)
    planned = next(o for o in res.ops if o["batch_id"] == "A")
    assert planned["start"] >= t0 + timedelta(hours=1)


def test_job_beyond_horizon_is_reported():
    res = engine.schedule(_slots(days=1), {"WS-01": "MIX"}, [_job("A", 60 * 20, steps=("MIX",))], [], 5, 0)
    assert res.unscheduled and res.unscheduled[0]["reason"] == "beyond planning horizon"


# ---------------------------------------------------------- plan workflow
@pytest.mark.django_db
def test_normal_order_makes_a_draft_urgent_order_publishes(people, factory):
    t = people["pic"].tenant_openid
    mes.create_work_order(people["pic"], {"product_code": "HC-50", "qty": 20, "due_date": "2026-12-01"}, source="ERP")
    assert service.current(t, service.DRAFT) is not None and service.current(t) is None
    assert Alert.objects.filter(kind="PLAN_DRAFT", is_open=True).count() == 1
    wo, _ = mes.create_work_order(people["pic"], {"product_code": "HC-50", "qty": 10, "due_date": "2026-12-01"})
    assert wo["special_urgent"]
    pub = service.current(t)
    assert pub is not None and pub["published_by"].startswith("auto (urgent")
    assert Alert.objects.filter(kind="PLAN_CHANGED").exists()


@pytest.mark.django_db
def test_accept_and_reject_drafts(people, factory, clients):
    t = people["pic"].tenant_openid
    mes.create_work_order(people["pic"], {"product_code": "HC-50", "qty": 20, "due_date": "2026-12-01"}, source="ERP")
    draft = service.current(t, service.DRAFT)
    assert clients["worker"].post(f"{API}/aps/plans/{draft['plan_id']}/decision", {"accept": True},
                                  format="json").status_code == 403
    r = clients["em"].post(f"{API}/aps/plans/{draft['plan_id']}/decision", {"accept": True}, format="json")
    assert r.status_code == 200 and r.json()["status"] == "published"
    assert not Alert.objects.filter(kind="PLAN_DRAFT", is_open=True).exists()
    new = clients["em"].post(f"{API}/aps/replan", {}, format="json").json()
    clients["em"].post(f"{API}/aps/plans/{new['plan_id']}/decision", {"accept": False}, format="json")
    assert mongo.db().plans.find_one({"plan_id": new["plan_id"]})["status"] == "rejected"
    assert service.current(t)["plan_id"] == draft["plan_id"]


@pytest.mark.django_db
def test_waiting_material_orders_are_blocked_not_planned(people, factory):
    t = people["pic"].tenant_openid
    wo, _ = mes.create_work_order(people["pic"], {"product_code": "HC-50", "qty": 500, "due_date": "2026-12-01"},
                                  source="ERP")
    assert wo["status"] == "waiting_material"
    plan = service.compute(t)
    assert [b["wo_id"] for b in plan["blocked"]] == [wo["wo_id"]]
    assert not any(o["wo_id"] == wo["wo_id"] for o in plan["ops"])


@pytest.mark.django_db
def test_late_risk_flag(people, factory):
    t = people["pic"].tenant_openid
    yesterday = (date.today() - timedelta(days=1)).isoformat()      # cannot be met whatever the calendar says
    wo, _ = mes.create_work_order(people["pic"], {"product_code": "HC-50", "qty": 20, "due_date": yesterday},
                                  source="ERP")
    order = next(o for o in service.compute(t)["orders"] if o["wo_id"] == wo["wo_id"])
    assert order["late_risk"] is True


@pytest.mark.django_db
def test_worker_queue_follows_published_plan(people, factory):
    t = people["pic"].tenant_openid
    a, _ = mes.create_work_order(people["pic"], {"product_code": "HC-50", "qty": 10, "batches": 1,
                                                 "due_date": "2026-12-20"}, source="ERP")
    b, _ = mes.create_work_order(people["pic"], {"product_code": "HC-50", "qty": 10, "batches": 1,
                                                 "due_date": "2026-12-05"}, source="ERP")
    plan = service.request_replan(t, "test")
    service.decide(people["em"], plan["plan_id"], True)
    board = mes.worker_board(t, "WS-01")
    assert board["queue"][0]["wo_id"] == b["wo_id"] and board["queue"][0]["planned_start"] is not None


@pytest.mark.django_db
def test_frozen_window_keeps_published_next_step(people, factory):
    t = people["pic"].tenant_openid
    mes.create_work_order(people["pic"], {"product_code": "HC-50", "qty": 10, "batches": 1, "due_date": "2026-12-20"},
                          source="ERP")
    first = service.request_replan(t, "test")
    service.decide(people["em"], first["plan_id"], True)
    op = next(o for o in first["ops"] if o["step_no"] == 1)
    later = op["start"] - timedelta(minutes=1)
    if (op["start"] - datetime.now(timezone.utc)) > timedelta(hours=4):
        pytest.skip("first operation is outside the frozen window at this time of day")
    urgent, _ = mes.create_work_order(people["pic"], {"product_code": "HC-50", "qty": 10, "due_date": "2026-12-01"})
    pub = service.current(t)
    kept = next(o for o in pub["ops"] if o["batch_id"] == op["batch_id"] and o["step_no"] == 1)
    assert kept["kind"] == "frozen" and kept["start"] > later


@pytest.mark.django_db
def test_calendar_api_permissions_and_validation(clients):
    shifts = [{"code": "A", "start": "07:00", "end": "15:00", "break_start": "11:00", "break_minutes": 30, "workers": 5}]
    assert clients["em"].put(f"{API}/aps/calendar", {"shifts": shifts, "working_days": [0, 1, 2, 3, 4]},
                             format="json").status_code == 403
    bad = [dict(shifts[0], break_start="16:00")]
    assert clients["pic"].put(f"{API}/aps/calendar", {"shifts": bad, "working_days": [0]}, format="json").status_code == 400
    ok = clients["pic"].put(f"{API}/aps/calendar", {"shifts": shifts, "working_days": [0, 1, 2, 3, 4]}, format="json")
    assert ok.status_code == 200 and cal.shift_settings()[1] == [0, 1, 2, 3, 4]
    assert clients["pic"].post(f"{API}/aps/holidays", {"date": "2026-12-24", "name": "Factory"},
                               format="json").status_code == 201
    assert clients["pic"].post(f"{API}/aps/staffing", {"date": "2026-12-23", "shift_code": "A", "workers": 3},
                               format="json").status_code == 201
    assert StaffingOverride.objects.get(date=date(2026, 12, 23)).workers == 3
    assert clients["worker"].get(f"{API}/aps/plan").status_code == 403


@pytest.mark.django_db
def test_long_machine_stop_drafts_a_replan(people, factory):
    from aps.triggers import check_long_stops
    _, (batch,) = mes.create_work_order(people["pic"], {"product_code": "HC-50", "qty": 10, "batches": 1,
                                                        "due_date": "2026-12-20"}, source="ERP")
    w = people["worker"]
    mes.start_step(w, "WS-01", batch["batch_id"], uuid.uuid4().hex)
    mes.machine_stop(w, "WS-01", "BREAKDOWN", uuid.uuid4().hex)
    mongo.db().wip.update_one({"batch_id": batch["batch_id"]},
                              {"$set": {"stopped_since": datetime.now(timezone.utc) - timedelta(minutes=45)}})
    plans = check_long_stops()
    assert len(plans) == 1 and "stopped" in plans[0]["reason"]
    assert check_long_stops() == []          # only once per stop


# ----------------------------------------------------------------- saving changeovers (v3.6.0)
def test_builtin_groups_same_product_within_the_day_window():
    jobs = [_job("A", 30, product="X", due="2026-11-05"), _job("B", 30, product="Y", due="2026-11-05"),
            _job("C", 30, product="X", due="2026-11-06"), _job("D", 30, product="X", due="2026-11-09")]
    assert [j.batch_id for j in engine.sequence(jobs, 0)] == ["A", "B", "C", "D"]
    # C (same product, due 1 day later) moves up; D is 4 days later, so it does not jump B.
    assert [j.batch_id for j in engine.sequence(jobs, 1)] == ["A", "C", "B", "D"]


def test_grouping_never_overtakes_or_delays_urgent():
    jobs = [_job("U1", 30, product="X", urgent=True, due="2026-11-09"), _job("U2", 30, product="Y", urgent=True,
            due="2026-11-09"), _job("C", 30, product="X", due="2026-11-05")]
    assert [j.batch_id for j in engine.sequence(jobs, 14)] == ["U1", "U2", "C"]


def test_rules_are_pic_only_validated_and_used(people, clients):
    from aps import rules
    url = f"{API}/aps/rules"
    assert clients["em"].put(url, {"changeover_cost_minutes": 5}, format="json").status_code == 403
    assert clients["pic"].put(url, {"group_same_product_days": 99}, format="json").status_code == 400
    r = clients["pic"].put(url, {"changeover_cost_minutes": 45, "group_same_product_days": 2}, format="json")
    assert r.status_code == 200 and r.json() == {"changeover_cost_minutes": 45, "group_same_product_days": 2}
    assert rules.get("group_same_product_days") == 2
    assert clients["em"].get(f"{API}/aps/calendar").json()["rules"]["changeover_cost_minutes"] == 45
