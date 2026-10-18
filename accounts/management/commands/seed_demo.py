"""
Create the demo company, the three demo accounts and two sample work orders.
Safe to run again (existing records are kept).

    python manage.py seed_demo                 # accounts + sample work orders
    python manage.py seed_demo --register-device WS-01   # also prints a device token
"""
import os
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts import services as account_services
from accounts.models import Account
from core import config, mongo
from mes import services as mes_services
from staff.models import ListModel as Staff
from userprofile.models import Users
from utils.md5 import Md5


class Command(BaseCommand):
    help = "Create demo PIC / Engineering Manager / Worker accounts and sample work orders"

    def add_arguments(self, parser):
        parser.add_argument("--register-device", dest="device_ws", help="Workstation code, e.g. WS-01")
        parser.add_argument("--no-orders", action="store_true")

    @transaction.atomic
    def handle(self, *args, **opts):
        demo = config.get("demo", {})
        pic_pw, em_pw = os.environ.get("DEMO_PIC_PASSWORD"), os.environ.get("DEMO_EM_PASSWORD")
        if not pic_pw or not em_pw:
            raise CommandError("Set DEMO_PIC_PASSWORD and DEMO_EM_PASSWORD in .env first.")

        tenant = Users.objects.filter(name="demo", is_delete=False).first()
        if tenant is None:
            openid = Md5.md5(demo.get("tenant_name", "3Form Demo"))
            tenant = Users.objects.create(user_id=0, name="demo", openid=openid, appid=Md5.md5(openid + "app"),
                                          t_code=Md5.md5(openid), ip="127.0.0.1", developer=False)
        openid = tenant.openid

        def staff_row(name, staff_type):
            row = Staff.objects.filter(openid=openid, staff_name=name).first()
            return row or Staff.objects.create(openid=openid, staff_name=name, staff_type=staff_type, check_code=8888)

        def ensure(role, staff_id, name, username=None, password=None, staff_type="Worker"):
            acct = Account.objects.filter(tenant_openid=openid, staff_id=staff_id).first()
            if acct:
                return acct, False
            user = None
            if username:
                user = User.objects.filter(username=username).first() or User.objects.create_user(username, password=password)
            acct = Account.objects.create(user=user, tenant_openid=openid, staff_id=staff_id, display_name=name,
                                          role=role, legacy_staff_pk=staff_row(name, staff_type).pk)
            return acct, True

        pic, new_pic = ensure(Account.ROLE_PIC, "P001", "Demo PIC", demo.get("pic_username", "pic_demo"), pic_pw, "Admin")
        em, new_em = ensure(Account.ROLE_EM, "E001", "Demo Eng. Manager", demo.get("em_username", "em_demo"), em_pw,
                            "Manager")
        worker, new_w = ensure(Account.ROLE_WORKER, demo.get("worker_staff_id", "1001"), "Demo Worker")
        for i in range(2, 7):
            ensure(Account.ROLE_WORKER, f"100{i}", f"Worker {i}")

        self.stdout.write(self.style.SUCCESS("Demo accounts:"))
        self.stdout.write(f"  PIC              username={pic.user.username:<10} password=(DEMO_PIC_PASSWORD in .env)"
                          f"{'  [new]' if new_pic else ''}")
        self.stdout.write(f"  Eng. Manager     username={em.user.username:<10} password=(DEMO_EM_PASSWORD in .env)"
                          f"{'  [new]' if new_em else ''}")
        self.stdout.write(f"  Worker           staff ID={worker.staff_id} (also 1002-1006), registered device needed"
                          f"{'  [new]' if new_w else ''}")

        if opts["device_ws"]:
            device, raw = account_services.register_device(pic, f"Demo tablet {opts['device_ws']}", opts["device_ws"])
            self.stdout.write(self.style.WARNING(f"Device token for {opts['device_ws']} (shown once): {raw}"))

        if not opts["no_orders"]:
            mongo.ensure_indexes()
            if not mes_services.list_work_orders(openid, limit=1):
                due = date.today() + timedelta(days=7)
                mes_services.create_work_order(pic, {"product_code": "HC-50", "product_name": "Hand cream 50 ml",
                                                     "client": "Demo Retail", "qty": 500, "batches": 2,
                                                     "due_date": due.isoformat(), "ship_mode": "stock"}, source="ERP")
                mes_services.create_work_order(pic, {"product_code": "SR-30", "product_name": "Serum 30 ml",
                                                     "client": "Demo Clinic", "qty": 120, "batches": 1,
                                                     "due_date": (due - timedelta(days=5)).isoformat(),
                                                     "ship_mode": "direct"}, source="PIC")
                self.stdout.write(self.style.SUCCESS("Created 2 sample work orders (1 Special / Urgent)."))
