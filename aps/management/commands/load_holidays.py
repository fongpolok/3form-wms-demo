"""Load Hong Kong general holidays into the calendar (safe to run again)."""
from datetime import date

from django.core.management.base import BaseCommand

from aps.holidays import HK_HOLIDAYS
from aps.models import Holiday


class Command(BaseCommand):
    help = "Load Hong Kong general holidays (2026-2027) into the APS calendar"

    def handle(self, *args, **opts):
        n = 0
        for d, name in HK_HOLIDAYS.items():
            _, created = Holiday.objects.get_or_create(date=date.fromisoformat(d),
                                                       defaults={"name": name, "source": "gov.hk"})
            n += created
        self.stdout.write(self.style.SUCCESS(f"{n} holiday(s) added, {Holiday.objects.count()} in calendar"))
