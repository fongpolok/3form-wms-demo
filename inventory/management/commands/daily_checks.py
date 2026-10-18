"""Daily housekeeping: expiry alerts + re-check orders waiting for material."""
from django.core.management.base import BaseCommand

from accounts.models import Account
from inventory.services import expiry_alerts
from mes.materials import recheck_waiting


class Command(BaseCommand):
    help = "Raise expiry alerts and re-check orders waiting for material"

    def handle(self, *args, **opts):
        for tenant in Account.objects.order_by().values_list("tenant_openid", flat=True).distinct():
            n = expiry_alerts(tenant)
            released = recheck_waiting(tenant)
            self.stdout.write(f"{tenant[:8]}: {n} expiry alert(s), released {released}")
