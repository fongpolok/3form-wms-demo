"""SAP (modelled on S/4HANA OData v2 production-order and confirmation APIs)."""
from .base import Connector


class SapConnector(Connector):
    system = "SAP"

    def fetch_released_orders(self):
        params = {"$format": "json", "$filter": self.cfg.get("orders_filter", "")}
        if self.conn.company_code:
            params["$filter"] = f"({params['$filter']}) and ProductionPlant eq '{self.conn.company_code}'"
        data = self._request("GET", self.cfg["orders_path"], params=params)
        rows = (data.get("d") or {}).get("results", data.get("value", []))
        return [self._map(r) for r in rows]

    def push_result(self, result):
        body = {"ManufacturingOrder": result["erp_ref"], "ConfirmationYieldQuantity": str(result["good_qty"]),
                "ConfirmationScrapQuantity": str(result["scrap_qty"]), "ConfirmationText": result["text"][:40],
                "PostingDate": result["finished_at"][:10], "YY_BatchIDs": ",".join(result["batch_ids"])}
        data = self._request("POST", self.cfg["results_path"], json=body, headers={"Content-Type": "application/json"})
        return str(((data.get("d") or {}).get("MfgOrderConfirmation")) or data.get("id") or "ok")

    def ping(self):
        self._request("GET", self.cfg["orders_path"], params={"$format": "json", "$top": 1})
        return "Connected: production orders readable."
