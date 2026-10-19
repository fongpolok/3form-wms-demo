"""
Anonymiser: what leaves the site for the AI provider (settings.yaml agent.anonymise.*,
decision PENDING with the owner, each part can be switched off).

  clients  -> "Client A", "Client B", ...
  workers  -> "Worker 1", ... (staff IDs and names)
  prices   -> fields with price / cost / amount / value_hkd removed
  company  -> "the company"

The mapping lives only in memory for one run; the AI's answer is converted back
(restore) before it is shown to the PIC / Engineering Manager.
"""
import re
import string

from accounts.models import Account
from core import config
from userprofile.models import Users

PRICE_KEYS = re.compile(r"(price|cost|amount|value_hkd|capital)", re.I)
CLIENT_KEYS = {"client", "customer", "customer_name"}
WORKER_KEYS = {"staff_id", "started_by", "finished_by", "actor", "actor_name", "counted_by", "created_by",
               "decided_by", "published_by", "updated_by", "acknowledged_by"}


class Anonymiser:
    def __init__(self, tenant):
        cfg = config.get("agent.anonymise", {}) or {}
        self.on = {k: bool(cfg.get(k, True)) for k in ("clients", "workers", "prices", "company")}
        self.fwd = {}       # real -> alias
        self.back = {}      # alias -> real
        self.counters = {"client": 0, "worker": 0}
        if self.on["company"]:
            u = Users.objects.filter(openid=tenant).first()
            for name in filter(None, [u.name if u else "", config.get("demo.tenant_name", "")]):
                if len(name) > 3:
                    self._alias(name, "the company")
        if self.on["clients"]:
            # Learn every client name up front, so a name inside free text is hidden even
            # when the text comes before the "client" field (found by test_ai_receives_only_anonymised_data).
            from core import mongo
            from customer.models import ListModel as Customer
            names = set(mongo.db().work_orders.distinct("client", {"tenant_openid": tenant}))
            names |= set(Customer.objects.filter(openid=tenant, is_delete=False).values_list("customer_name", flat=True))
            for name in sorted(n for n in names if n and len(n) >= 3):
                self.client(name)
        if self.on["workers"]:
            for a in Account.objects.filter(tenant_openid=tenant):
                alias = self._next("worker")
                self._alias(a.staff_id, alias)
                if a.display_name and len(a.display_name) > 2:
                    self.fwd[a.display_name] = alias

    def _alias(self, real, alias):
        real = str(real)
        if real and real not in self.fwd:
            self.fwd[real] = alias
            self.back.setdefault(alias, real)
        return self.fwd.get(real, alias)

    def _next(self, kind):
        self.counters[kind] += 1
        n = self.counters[kind]
        if kind == "client":
            return "Client " + (string.ascii_uppercase[n - 1] if n <= 26 else str(n))
        return f"Worker {n}"

    def client(self, name):
        if not name or not self.on["clients"]:
            return name
        return self.fwd.get(name) or self._alias(name, self._next("client"))

    def worker(self, value):
        if not value or not self.on["workers"]:
            return value
        return self.fwd.get(str(value)) or self._alias(str(value), self._next("worker"))

    def apply(self, obj, key=None):
        """Anonymise a JSON-like structure (dict / list / str)."""
        if isinstance(obj, dict):
            out = {}
            for k, v in obj.items():
                if self.on["prices"] and PRICE_KEYS.search(k):
                    continue
                if k in CLIENT_KEYS and isinstance(v, str):
                    out[k] = self.client(v)
                elif k in WORKER_KEYS and isinstance(v, (str, int)):
                    out[k] = self.worker(v)
                else:
                    out[k] = self.apply(v, k)
            return out
        if isinstance(obj, list):
            return [self.apply(v, key) for v in obj]
        if isinstance(obj, str):
            return self.text(obj)
        return obj

    def text(self, s):
        for real in sorted(self.fwd, key=len, reverse=True):
            if len(real) >= 3 and real in s:
                s = s.replace(real, self.fwd[real])
        return s

    def restore(self, s):
        """Put real names back into the AI's answer (stays on site)."""
        if not isinstance(s, str):
            return s
        for alias in sorted(self.back, key=len, reverse=True):
            if alias != "the company":
                s = s.replace(alias, self.back[alias])
        return s

    def restore_obj(self, obj):
        if isinstance(obj, dict):
            return {k: self.restore_obj(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self.restore_obj(v) for v in obj]
        return self.restore(obj)
