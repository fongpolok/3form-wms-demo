"""First login on a new installation (production, not demo):
    python manage.py create_pic --company "Client Ltd" --username alice --staff-id P001 --name "Alice Chan"
The password is asked for (never typed on the command line)."""
import getpass

from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from accounts.models import Account
from userprofile.models import Users
from utils.md5 import Md5


class Command(BaseCommand):
    help = "Create the company and its first PIC account"

    def add_arguments(self, parser):
        for a in ("company", "username", "staff-id", "name"):
            parser.add_argument(f"--{a}", required=True)

    def handle(self, *args, **o):
        if User.objects.filter(username=o["username"]).exists():
            raise CommandError("That username already exists.")
        pw = getpass.getpass("New PIC password: ")
        if pw != getpass.getpass("Repeat password: "):
            raise CommandError("Passwords do not match.")
        try:
            validate_password(pw)
        except ValidationError as exc:
            raise CommandError(" ".join(exc.messages))
        tenant = Users.objects.filter(name=o["company"], is_delete=False).first()
        if tenant is None:
            openid = Md5.md5(o["company"])
            tenant = Users.objects.create(user_id=0, name=o["company"], openid=openid, appid=Md5.md5(openid + "app"),
                                          t_code=Md5.md5(openid), ip="127.0.0.1", developer=False)
        user = User.objects.create_user(o["username"], password=pw)
        Account.objects.create(user=user, tenant_openid=tenant.openid, staff_id=o["staff_id"], display_name=o["name"],
                               role=Account.ROLE_PIC)
        self.stdout.write(self.style.SUCCESS(f"PIC {o['username']} created for {o['company']}. Sign in at /login."))
