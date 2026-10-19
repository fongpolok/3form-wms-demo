"""Workday (staff list only, modelled on a Workday custom report (RaaS) in JSON)."""
from .base import Connector


class WorkdayConnector(Connector):
    system = "WORKDAY"

    def fetch_staff(self):
        data = self._request("GET", self.cfg["staff_path"], params={"format": "json"})
        f = self.fields
        out = []
        for r in data.get("Report_Entry", []):
            active = str(r.get(f.get("active", "Active"), "1")).lower() in ("1", "true", "yes", "active")
            out.append({"staff_id": str(r.get(f.get("staff_id"), "")).strip(), "name": str(r.get(f.get("name"), "")).strip(),
                        "active": active})
        return [s for s in out if s["staff_id"]]

    def ping(self):
        return f"Connected: {len(self.fetch_staff())} staff in the report."
