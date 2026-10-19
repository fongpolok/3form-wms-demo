"""Oracle (modelled on Oracle Fusion Cloud Manufacturing REST work orders)."""
from .base import Connector


class OracleConnector(Connector):
    system = "ORACLE"

    def fetch_released_orders(self):
        params = {"q": self.cfg.get("orders_query", ""), "limit": 200, "onlyData": "true"}
        if self.conn.company_code:
            params["q"] += f";OrganizationCode={self.conn.company_code}"
        data = self._request("GET", self.cfg["orders_path"], params=params)
        return [self._map(r) for r in data.get("items", [])]

    def push_result(self, result):
        body = {"WorkOrderNumber": result["erp_ref"], "TransactionQuantity": result["good_qty"],
                "ScrapQuantity": result["scrap_qty"], "TransactionDate": result["finished_at"],
                "TransactionNote": result["text"][:240], "LotNumbers": result["batch_ids"]}
        data = self._request("POST", self.cfg["results_path"], json=body,
                             headers={"Content-Type": "application/vnd.oracle.adf.resourceitem+json"})
        return str(data.get("TransactionId") or data.get("id") or "ok")

    def ping(self):
        self._request("GET", self.cfg["orders_path"], params={"limit": 1, "onlyData": "true"})
        return "Connected: work orders readable."
