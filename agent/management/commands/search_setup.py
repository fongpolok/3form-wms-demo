"""Create the search indexes (keyword now; vector prepared, off) and fill the corpus."""
from django.core.management.base import BaseCommand

from accounts.models import Account
from agent import search


class Command(BaseCommand):
    help = "Create Atlas Search indexes and sync searchable text"

    def handle(self, *args, **opts):
        made, status = search.setup_indexes()
        self.stdout.write(f"Indexes created: {made or 'none (already there)'}; status: {status}")
        for t in Account.objects.order_by().values_list("tenant_openid", flat=True).distinct():
            self.stdout.write(f"{t[:8]}: {search.sync(t)} documents")
