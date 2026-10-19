"""
ERP connector interface. One adapter per system; all speak HTTPS + JSON and use
the connection details the PIC saved in Settings -> Integrations.

    fetch_released_orders() -> [ {erp_ref, product_code, qty, due_date, client, priority, raw} ]
    push_result(result)     -> ERP reference of the confirmation
    fetch_staff()           -> [ {staff_id, name, active} ]       (Workday)
    ping()                  -> short status text
Field names come from settings.yaml (erp.<system>.fields), so a client's own
names can be mapped without code changes.
"""
import logging

import requests

from core import config, secrets

logger = logging.getLogger("app")


class ErpError(Exception):
    """Connection or data problem, shown to the PIC as-is."""


class Connector:
    system = ""

    def __init__(self, conn):
        self.conn = conn
        self.cfg = config.get(f"erp.{self.system.lower()}", {}) or {}
        self.fields = self.cfg.get("fields", {})
        self.timeout = float(config.get("erp.timeout_seconds", 30))

    # ---- HTTP -----------------------------------------------------------------
    def _auth(self):
        secret = secrets.decrypt(self.conn.secret_enc) if self.conn.secret_enc else ""
        if self.conn.auth_type == "basic":
            return {"auth": (self.conn.username, secret)}
        if self.conn.auth_type == "api_key":
            return {"headers": {"APIKey": secret}}
        return {"headers": {"Authorization": f"Bearer {secret}"}}          # oauth2 token / bearer

    def _url(self, path):
        if not self.conn.base_url:
            raise ErpError("No ERP address saved for this connection.")
        return self.conn.base_url.rstrip("/") + path

    def _request(self, method, path, **kw):
        auth = self._auth()
        headers = {"Accept": "application/json", **auth.pop("headers", {}), **kw.pop("headers", {})}
        try:
            r = requests.request(method, self._url(path), headers=headers, timeout=self.timeout, **auth, **kw)
        except requests.RequestException as exc:
            raise ErpError(f"Cannot reach {self.conn.name}: {exc.__class__.__name__}")
        if r.status_code in (401, 403):
            raise ErpError(f"{self.conn.name} refused the sign-in ({r.status_code}). Check user / password.")
        if r.status_code >= 400:
            raise ErpError(f"{self.conn.name} answered {r.status_code}: {r.text[:200]}")
        return r.json() if r.content else {}

    # ---- mapping ----------------------------------------------------------------
    def _map(self, row):
        f = self.fields
        def val(key):
            return row.get(f.get(key, key))
        due = str(val("due_date") or "")
        if due.startswith("/Date("):                 # SAP OData v2 date: /Date(1730419200000)/
            from datetime import datetime, timezone
            ms = int(due[6:due.index(")")].split("+")[0])
            due = datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date().isoformat()
        return {"erp_ref": str(val("erp_ref") or ""), "product_code": str(val("product_code") or "").strip(),
                "qty": val("qty"), "due_date": due[:10], "client": val("client") or "",
                "priority": val("priority"), "raw": row}

    # ---- interface ----------------------------------------------------------------
    def fetch_released_orders(self):
        raise ErpError(f"{self.system} does not provide production orders.")

    def push_result(self, result):
        raise ErpError(f"{self.system} does not accept production results.")

    def fetch_staff(self):
        raise ErpError(f"{self.system} does not provide a staff list.")

    def ping(self):
        raise NotImplementedError
