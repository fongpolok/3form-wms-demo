"""
Generate realistic demo history for pitching (all records tagged as demo).

    python manage.py seed_history              # 90 days of history + today's live orders
    python manage.py seed_history --days 30
    python manage.py seed_history --clear      # remove every demo record (real data untouched)

Run `manage.py seed_demo` first (creates the demo company and accounts).
"""
import math
import random
import uuid
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from binset.models import ListModel as LegacyBin
from core import config, mongo
from goods.models import ListModel as Goods
from inventory import services as inv
from inventory.models import (Alert, BinZone, MaterialRequest, Movement, Product, RecipeLine, Reservation, Shipment,
                              StockLot)
from mes.workstations import list_workstations, routing
from userprofile.models import Users

SEED = "demo-seed"
HKT = ZoneInfo("Asia/Hong_Kong")
PRODUCTS = {   # code: (name, shelf life days, recipe {material: per piece}, typical order size, client)
    "HC-50": ("Hand cream 50 ml", 730, {"CREAM-BASE": 52, "JAR-50": 1, "CAP-STD": 1, "LABEL-HC": 1}, (240, 600),
              "Demo Retail"),
    "SR-30": ("Serum 30 ml", 540, {"SERUM-BASE": 31, "BOTTLE-30": 1, "CAP-STD": 1, "LABEL-SR": 1}, (120, 360),
              "Demo Clinic"),
    "LT-200": ("Body lotion 200 ml", 900, {"LOTION-BASE": 205, "BOTTLE-200": 1, "CAP-STD": 1, "LABEL-LT": 1},
               (180, 480), "Demo Spa"),
}
MATERIALS = {"CREAM-BASE": "Cream base (g)", "SERUM-BASE": "Serum base (ml)", "LOTION-BASE": "Lotion base (ml)",
             "JAR-50": "Jar 50 ml", "BOTTLE-30": "Dropper bottle 30 ml", "BOTTLE-200": "Pump bottle 200 ml",
             "CAP-STD": "Standard cap", "LABEL-HC": "Label – hand cream", "LABEL-SR": "Label – serum",
             "LABEL-LT": "Label – lotion"}
BINS = ([(f"RM-A{i:02d}", "RAW") for i in range(1, 9)] + [(f"FG-B{i:02d}", "FG") for i in range(1, 13)]
        + [("QA-C01", "QA"), ("HOLD-D01", "HOLD"), ("DMG-E01", "DAMAGE")])
SCRAP_WEIGHTS = {"SPILL": 34, "LEAK": 21, "LABEL": 15, "UNDER": 11, "DAMAGE": 8, "MACHINE": 6, "CONTAM": 3,
                 "OTHER": 2}
DOWN_WEIGHTS = {"CHANGEOVER": 40, "MATERIAL": 20, "BREAKDOWN": 15, "CLEANING": 15, "BREAK": 10}
WORKERS = ["1001", "1002", "1003", "1004", "1005", "1006"]


def _pick(weights):
    return random.choices(list(weights), weights=list(weights.values()))[0]


def _utc(local_naive):
    return local_naive.replace(tzinfo=HKT).astimezone(timezone.utc)


class Command(BaseCommand):
    help = "Create (or --clear) demo production history"

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=90)
        parser.add_argument("--clear", action="store_true")
        parser.add_argument("--seed", type=int, default=2026)

    def handle(self, *args, **opts):
        tenant_row = Users.objects.filter(name="demo", is_delete=False).first()
        if tenant_row is None:
            raise CommandError("Run `python manage.py seed_demo` first.")
        self.t = tenant_row.openid
        self.db = mongo.db()
        if opts["clear"]:
            self.clear()
            return
        if self.db.work_orders.find_one({"tenant_openid": self.t, "demo": True}):
            raise CommandError("Demo history already exists. Run with --clear first.")
        random.seed(opts["seed"])
        mongo.ensure_indexes()
        self.master_data()
        self.history(opts["days"])
        self.live_orders()
        self.stdout.write(self.style.SUCCESS("Demo history created. Remove it any time with: seed_history --clear"))

    # ------------------------------------------------------------ clear
    def clear(self):
        t = self.t
        n_mongo = 0
        for coll in ("work_orders", "batches", "wip", "step_events", "vision_results"):
            n_mongo += self.db[coll].delete_many({"tenant_openid": t, "demo": True}).deleted_count
        n_mongo += self.db.plans.delete_many({"tenant_openid": t}).deleted_count   # plans are derived; rebuilt any time
        with transaction.atomic():
            wo_ids = list(Reservation.objects.filter(tenant_openid=t, is_demo=True).values_list("wo_id", flat=True))
            MaterialRequest.objects.filter(tenant_openid=t, wo_id__startswith="WO-", goods_code__in=MATERIALS).delete()
            Reservation.objects.filter(tenant_openid=t, is_demo=True).delete()
            n_pg = sum(m.objects.filter(tenant_openid=t, is_demo=True).delete()[0]
                       for m in (StockLot, Movement, Shipment, Alert))
            Alert.objects.filter(tenant_openid=t, ref__in=wo_ids).delete()
            RecipeLine.objects.filter(product__tenant_openid=t, product__goods_code__in=PRODUCTS).delete()
            Product.objects.filter(tenant_openid=t, goods_code__in=PRODUCTS).delete()
            BinZone.objects.filter(tenant_openid=t, bin_name__in=[b for b, _ in BINS]).delete()
            LegacyBin.objects.filter(openid=t, creater=SEED).delete()
            Goods.objects.filter(openid=t, creater=SEED).delete()
        self.stdout.write(self.style.SUCCESS(f"Removed demo data: {n_mongo} MES records, {n_pg} inventory records."))

    # ------------------------------------------------------------ master data
    def master_data(self):
        t = self.t
        for code, desc in {**{k: v[0] for k, v in PRODUCTS.items()}, **MATERIALS}.items():
            if not Goods.objects.filter(openid=t, goods_code=code, is_delete=False).exists():
                Goods.objects.create(goods_code=code, goods_desc=desc, goods_supplier="Demo Supplier",
                                     goods_unit="Piece", goods_class="Cosmetics", goods_brand="3Form Demo",
                                     goods_color="", goods_shape="", goods_specs="", goods_origin="HK", creater=SEED,
                                     bar_code=code, openid=t)
        for name, zone in BINS:
            if not LegacyBin.objects.filter(openid=t, bin_name=name, is_delete=False).exists():
                prop = {"QA": "Inspection", "HOLD": "Holding", "DAMAGE": "Damage"}.get(zone, "Normal")
                LegacyBin.objects.create(bin_name=name, bin_size="Floor", bin_property=prop, empty_label=True,
                                         creater=SEED, bar_code=name, openid=t)
            BinZone.objects.update_or_create(tenant_openid=t, bin_name=name, defaults={"zone": zone})
        for code, (name, life, recipe, _, _) in PRODUCTS.items():
            p, _ = Product.objects.update_or_create(tenant_openid=t, goods_code=code,
                                                    defaults={"name": name, "shelf_life_days": life, "routing": []})
            p.recipe.all().delete()
            for m, q in recipe.items():
                p.recipe.create(material_code=m, qty_per_piece=q)

    def _receive(self, code, qty, when, lot, bin_name, expiry):
        lot_row, _ = StockLot.objects.get_or_create(
            tenant_openid=self.t, goods_code=code, lot_number=lot, bin_name=bin_name,
            defaults={"goods_desc": MATERIALS.get(code, code), "expiry_date": expiry, "received_at": when,
                      "source": "inbound", "is_demo": True})
        lot_row.qty += qty
        lot_row.save()
        Movement.objects.create(ts=when, tenant_openid=self.t, kind=Movement.RECEIVE, goods_code=code, lot_number=lot,
                                bin_to=bin_name, qty=qty, ref=f"PO-{when:%Y%m%d}", actor="Warehouse (demo)",
                                is_demo=True)

    def _restock(self, day):
        """A delivery of every raw material, enough for ~2 weeks."""
        when = datetime.combine(day, time(9, 0))
        bins = [b for b, z in BINS if z == "RAW"]
        for i, code in enumerate(MATERIALS):
            per_day = {"CREAM-BASE": 26000, "SERUM-BASE": 9000, "LOTION-BASE": 68000}.get(code, 1300)
            qty = int(per_day * 15 * random.uniform(0.9, 1.15))
            life = 365 if code.endswith("BASE") else None
            expiry = (day + timedelta(days=life + random.randint(-30, 30))) if life else None
            self._receive(code, qty, when, f"{code[:3]}-{day:%y%m%d}", bins[i % len(bins)], expiry)

    # ------------------------------------------------------------ history
    def _id(self, kind, day):
        key = f"{kind}:{day:%Y%m%d}"
        seq = self.db.counters.find_one_and_update({"_id": key}, {"$inc": {"seq": 1}}, upsert=True,
                                                   return_document=True)["seq"]
        return (config.get("ids.work_order") if kind == "wo" else config.get("ids.batch")).format(
            date=f"{day:%Y%m%d}", seq=seq)

    def history(self, days):
        today = date.today()
        start = today - timedelta(days=days)
        steps = routing()
        ws_by_step = {w["step_code"]: w["code"] for w in list_workstations()}
        std = {s["code"]: float(s["std_seconds_per_unit"]) for s in steps}
        drift_start = today - timedelta(days=8)        # a 3-day fill-weight drift, recent enough to see on SPC
        self.stats = {"orders": 0, "batches": 0, "events": 0}
        fg_stock = []            # (product, batch, qty) waiting for shipment
        day = start
        while day < today:
            if (day - start).days % 14 == 0:
                self._restock(day)
            if day.weekday() < 6:   # Mon-Sat
                clock = datetime.combine(day, time(8, 0))
                for _ in range(random.choice([1, 2, 2, 3])):
                    with transaction.atomic():
                        clock = self._one_order(day, clock, steps, ws_by_step, std, drift_start, fg_stock)
                if day.weekday() in (1, 4) and fg_stock:     # ship finished goods twice a week
                    self._ship_some(day, fg_stock)
            day += timedelta(days=1)
        self.stdout.write(f"History: {self.stats}")

    def _one_order(self, day, clock, steps, ws_by_step, std, drift_start, fg_stock):
        code = random.choices(list(PRODUCTS), weights=[5, 3, 2])[0]
        name, life, recipe, size, client = PRODUCTS[code]
        qty = random.randint(*size) // 10 * 10
        n_batches = 1 if qty < 300 else 2
        ship_mode = "direct" if client == "Demo Clinic" and random.random() < 0.6 else "stock"
        wo_id = self._id("wo", day)
        urgent = random.random() < 0.12
        created = _utc(clock - timedelta(hours=random.randint(20, 70)))
        wo = {"wo_id": wo_id, "tenant_openid": self.t, "product_code": code, "product_name": name, "client": client,
              "client_priority": random.randint(1, 4), "qty": qty,
              "due_date": (day + timedelta(days=random.randint(0, 3))).isoformat(), "ship_mode": ship_mode,
              "source": "PIC" if urgent else "ERP", "special_urgent": urgent,
              "routing": [{"step_no": i, "code": s["code"], "name": s["name"], "measurement": s.get("measurement"),
                           "is_qc": bool(s.get("is_qc"))} for i, s in enumerate(steps, 1)],
              "status": "done", "created_by": "Demo PIC", "created_at": created, "materials": None, "shortages": [],
              "demo": True}
        base, extra = divmod(qty, n_batches)
        batch_docs = []
        for i in range(n_batches):
            bqty = base + (1 if i < extra else 0)
            batch_id = self._id("batch", day)
            used = []
            issue_ts = clock
            for m, per in recipe.items():
                used += inv.issue(self.t, m, math.ceil(bqty * per), batch_id, "Demo worker", ts=issue_ts, is_demo=True)
            good = bqty
            wips, events = [], []
            for n, s in enumerate(steps, 1):
                ws = ws_by_step[s["code"]]
                worker = random.choice(WORKERS)
                start = clock + timedelta(minutes=random.randint(2, 6))
                perf = random.uniform(0.78, 0.97)
                run_s = std[s["code"]] * good / perf
                down_s = 0
                wip_id = f"WIP-{batch_id}-S{n:02d}-001"
                ev = lambda typ, ts, **kw: events.append(  # noqa: E731
                    {"event_id": uuid.uuid4().hex, "type": typ, "wip_id": wip_id, "batch_id": batch_id,
                     "wo_id": wo_id, "workstation": ws, "step_no": n, "step_code": s["code"],
                     "tenant_openid": self.t, "ts": _utc(ts), "source": "worker", "staff_id": worker,
                     "actor_name": f"Worker {worker[-1]}", "role": "WORKER", "demo": True, **kw})
                ev("start", start)
                if random.random() < 0.15:
                    reason = _pick(DOWN_WEIGHTS)
                    down_s = int(run_s * random.uniform(0.15, 0.6))
                    stop_at = start + timedelta(seconds=run_s * random.uniform(0.2, 0.7))
                    ev("stop", stop_at, reason_code=reason)
                    ev("resume", stop_at + timedelta(seconds=down_s), reason_code=reason)
                scrap = 0
                rate = {"FILL": 0.018, "CAP": 0.008, "LABEL": 0.012, "PACK": 0.006, "QC": 0.01}.get(s["code"], 0.004)
                for _ in range(random.randint(0, 3)):
                    q = max(1, int(good * rate * random.uniform(0.2, 0.8)))
                    if scrap + q >= good:
                        break
                    scrap += q
                    reason = "VISION" if s["code"] == "QC" and random.random() < 0.5 else _pick(SCRAP_WEIGHTS)
                    ev("scrap", start + timedelta(seconds=run_s * random.random()), qty=q, reason_code=reason,
                       note="Other: residue on nozzle" if reason == "OTHER" else "",
                       source="camera" if reason == "VISION" else "worker")
                if s.get("measurement"):
                    target = s["measurement"]["target"]
                    drifting = drift_start <= day < drift_start + timedelta(days=3)
                    for k in range(5):
                        val = round(random.gauss(target + (0.65 if drifting else 0.0), 0.25), 2)
                        ev("measure", start + timedelta(seconds=run_s * (k + 1) / 6), value=val, target=target,
                           unit=s["measurement"]["unit"], measure_name=s["measurement"]["name"],
                           in_spec=abs(val - target) <= target * float(config.get("mes.measurement_tolerance_pct", 2)) / 100)
                end = start + timedelta(seconds=run_s + down_s)
                good_out = good - scrap
                ev("finish", end, qty=good_out)
                wips.append({"wip_id": wip_id, "batch_id": batch_id, "wo_id": wo_id, "tenant_openid": self.t,
                             "step_no": n, "step_code": s["code"], "workstation": ws, "status": "done",
                             "qty_in": good, "good_qty": good_out, "scrap_qty": scrap, "downtime_seconds": down_s,
                             "stopped_since": None, "started_at": _utc(start), "finished_at": _utc(end),
                             "started_by": worker, "finished_by": worker, "edited_by_pic": False, "demo": True})
                good = good_out
                clock = end
            done_at = clock + timedelta(minutes=10)
            bdoc = {"batch_id": batch_id, "wo_id": wo_id, "tenant_openid": self.t, "qty": bqty,
                    "current_step_no": len(steps), "current_step_code": steps[-1]["code"], "total_steps": len(steps),
                    "status": "done", "good_qty_out": good, "last_good_qty": good, "materials_used": used,
                    "created_at": created, "qc_passed_at": _utc(clock), "finished_at": _utc(done_at), "demo": True}
            if ship_mode == "stock":
                bin_name = inv.suggest_fg_bin(self.t) or "FG-B01"
                inv.put_away_finished(self.t, code, batch_id, good, bin_name, "Demo worker", shelf_life_days=life,
                                      ts=done_at, is_demo=True)
                bdoc["bin_name"] = bin_name
                fg_stock.append((code, batch_id, good, client))
            else:
                ship = inv.ship_direct(self.t, client, batch_id, code, good, "Demo worker", ts=done_at, is_demo=True)
                bdoc["shipment_id"] = ship.shipment_id
            batch_docs.append(bdoc)
            self.db.wip.insert_many(wips)
            self.db.step_events.insert_many(events)
            self.stats["batches"] += 1
            self.stats["events"] += len(events)
        wo["finished_at"] = _utc(clock)
        self.db.work_orders.insert_one(wo)
        self.db.batches.insert_many(batch_docs)
        self.stats["orders"] += 1
        return clock + timedelta(minutes=random.randint(10, 40))

    def _ship_some(self, day, fg_stock):
        when = datetime.combine(day, time(16, 0))
        keep = []
        for code, batch_id, qty, client in fg_stock:
            if random.random() < 0.8:
                with transaction.atomic():
                    sid = f"SH-{day:%Y%m%d}-{uuid.uuid4().hex[:6].upper()}"
                    picked = inv.issue(self.t, code, qty, sid, "Warehouse (demo)", kind=Movement.SHIP, ts=when,
                                       is_demo=True) if inv.on_hand(self.t, code) >= qty else []
                    if picked:
                        Shipment.objects.create(tenant_openid=self.t, shipment_id=sid, client=client, source="stock",
                                                lines=picked, shipped_at=when, created_by="Warehouse (demo)",
                                                is_demo=True)
            else:
                keep.append((code, batch_id, qty, client))
        fg_stock[:] = keep

    # ------------------------------------------------------------ today
    def live_orders(self):
        """Three orders for today's demo: one running, one ready, one waiting for material."""
        from mes import services as mes

        from accounts.models import Account
        pic = Account.objects.filter(tenant_openid=self.t, role="PIC").first()
        made = []
        for code, qty, batches, mode, urgent in [("HC-50", 400, 2, "stock", False), ("LT-200", 240, 1, "stock", False),
                                                 ("SR-30", 200, 1, "direct", True)]:
            if code == "SR-30":   # make serum labels short (60 in total) so this order waits for material
                lots = list(StockLot.objects.filter(tenant_openid=self.t, goods_code="LABEL-SR", qty__gt=0))
                for i, lot in enumerate(lots):
                    lot.qty = 60 if i == 0 else 0
                    lot.save(update_fields=["qty"])
            wo, bs = mes.create_work_order(pic, {"product_code": code, "qty": qty, "batches": batches,
                                                 "due_date": (date.today() + timedelta(days=2)).isoformat(),
                                                 "ship_mode": mode, "client": PRODUCTS[code][4]},
                                           source="PIC" if urgent else "ERP")
            self.db.work_orders.update_one({"wo_id": wo["wo_id"]}, {"$set": {"demo": True}})
            self.db.batches.update_many({"wo_id": wo["wo_id"]}, {"$set": {"demo": True}})
            Reservation.objects.filter(wo_id=wo["wo_id"]).update(is_demo=True)
            Alert.objects.filter(ref=wo["wo_id"]).update(is_demo=True)
            made.append((wo["wo_id"], wo["status"]))
        # Put the first hand-cream batch on the line: mixing done, filling running with a few readings.
        worker = Account.objects.filter(tenant_openid=self.t, staff_id="1001").first()
        first = self.db.batches.find_one({"wo_id": made[0][0]}, sort=[("batch_id", 1)])
        busy = self.db.wip.find_one({"tenant_openid": self.t, "status": "running",
                                     "workstation": {"$in": ["WS-01", "WS-02"]}})
        if worker and first and made[0][1] == "released" and not busy:
            mes.start_step(worker, "WS-01", first["batch_id"], uuid.uuid4().hex)
            mes.record_scrap(worker, "WS-01", 3, "SPILL", uuid.uuid4().hex)
            mes.finish_step(worker, "WS-01", first["qty"] - 3, uuid.uuid4().hex)
            mes.start_step(worker, "WS-02", first["batch_id"], uuid.uuid4().hex)
            for _ in range(4):
                mes.record_measurement(worker, "WS-02", round(random.gauss(50.0, 0.25), 2), uuid.uuid4().hex)
            for coll in ("wip", "step_events"):
                self.db[coll].update_many({"batch_id": first["batch_id"]}, {"$set": {"demo": True}})
        # A week of upcoming ERP orders for the APS plan; the 6,000-piece hand cream due tomorrow is
        # deliberately too big to make it in time, so the plan shows a LATE RISK.
        for code, qty, nb, mode, due_in in [("HC-50", 3000, 2, "stock", 3), ("LT-200", 2400, 2, "stock", 4),
                                            ("SR-30", 1500, 1, "direct", 5), ("HC-50", 2000, 1, "stock", 6),
                                            ("LT-200", 1800, 1, "stock", 7), ("HC-50", 6000, 2, "stock", 1)]:
            wo, _ = mes.create_work_order(pic, {"product_code": code, "qty": qty, "batches": nb, "ship_mode": mode,
                                                "due_date": (date.today() + timedelta(days=due_in)).isoformat(),
                                                "client": PRODUCTS[code][4],
                                                "client_priority": random.randint(1, 4)}, source="ERP")
            self.db.work_orders.update_one({"wo_id": wo["wo_id"]}, {"$set": {"demo": True}})
            self.db.batches.update_many({"wo_id": wo["wo_id"]}, {"$set": {"demo": True}})
            Reservation.objects.filter(wo_id=wo["wo_id"]).update(is_demo=True)
            made.append((wo["wo_id"], wo["status"]))
        # Publish a starting plan, as if the Engineering Manager had accepted it.
        from aps import service as aps
        em = Account.objects.filter(tenant_openid=self.t, role="EM").first() or pic
        plan = aps.request_replan(self.t, "demo start plan", "seed_history")
        aps.decide(em, plan["plan_id"], True)
        inv.expiry_alerts(self.t)
        Alert.objects.filter(tenant_openid=self.t, kind=Alert.EXPIRY, detail__icontains="RM-A").update(is_demo=True)
        Alert.objects.filter(tenant_openid=self.t, kind__startswith="PLAN_").update(is_demo=True)
        self.stdout.write(f"Today's orders: {made}")
