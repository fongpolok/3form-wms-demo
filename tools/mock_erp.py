"""
Mock ERP server for testing the connectors without a real SAP / Oracle / Workday.

    python tools/mock_erp.py --port 8090 --user mock --password mock123

Then in Settings -> Integrations add a connection with address http://127.0.0.1:8090,
username mock, password mock123 (http is allowed only for 127.0.0.1 / localhost).

Serves (same paths as config/settings.yaml erp.*):
  SAP     GET  .../A_ProductionOrder_2          released production orders (OData v2 JSON)
          POST .../ProdnOrdConf2                 confirmations (results back)
  Oracle  GET  .../workOrders                   released work orders
          POST .../workOrderOperationTransactions
  Workday GET  .../customreport2/staff_list     staff report (RaaS JSON)
  Any     GET  /_received                       what the connectors sent back
The sample orders include one unknown product (to show the ERP inbox).
"""
import argparse
import base64
import json
import time
from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

RECEIVED = []


def sap_date(d):
    return f"/Date({int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp() * 1000)})/"


def sap_orders():
    t = date.today()
    return {"d": {"results": [
        {"ManufacturingOrder": "1000451", "Material": "HC-50", "TotalQuantity": "1200", "ProductionPlant": "HK01",
         "MfgOrderPlannedEndDate": sap_date(t + timedelta(days=5)), "SalesOrderCustomer": "Demo Retail", "MfgOrderPriority": "2"},
        {"ManufacturingOrder": "1000452", "Material": "LT-200", "TotalQuantity": "800", "ProductionPlant": "HK01",
         "MfgOrderPlannedEndDate": sap_date(t + timedelta(days=8)), "SalesOrderCustomer": "Demo Spa", "MfgOrderPriority": "3"},
        {"ManufacturingOrder": "1000453", "Material": "LIPBALM-5", "TotalQuantity": "500", "ProductionPlant": "HK01",
         "MfgOrderPlannedEndDate": sap_date(t + timedelta(days=9)), "SalesOrderCustomer": "Demo Retail", "MfgOrderPriority": "3"},
    ]}}


def oracle_orders():
    t = date.today()
    return {"items": [
        {"WorkOrderNumber": "WO-ORA-7781", "ItemNumber": "SR-30", "PlannedStartQuantity": 600,
         "PlannedCompletionDate": f"{t + timedelta(days=6)}T17:00:00+08:00", "CustomerName": "Demo Clinic",
         "WorkOrderPriority": 1, "OrganizationCode": "HK01"},
    ]}


def workday_staff():
    return {"Report_Entry": [
        {"Employee_ID": "1001", "Worker": "Chan Tai Man", "Active": "1"},
        {"Employee_ID": "1002", "Worker": "Wong Siu Ling", "Active": "1"},
        {"Employee_ID": "1007", "Worker": "Lee Ka Ho", "Active": "1"},
        {"Employee_ID": "1006", "Worker": "Cheung Mei", "Active": "0"},
    ]}


class Handler(BaseHTTPRequestHandler):
    user, password = "mock", "mock123"

    def _ok_auth(self):
        h = self.headers.get("Authorization", "")
        if not h.startswith("Basic "):
            return False
        u, _, p = base64.b64decode(h[6:]).decode().partition(":")
        return u == self.user and p == self.password

    def _send(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/_received":
            return self._send(200, RECEIVED)
        if not self._ok_auth():
            return self._send(401, {"error": "unauthorised"})
        if path.endswith("/A_ProductionOrder_2"):
            return self._send(200, sap_orders())
        if path.endswith("/workOrders"):
            return self._send(200, oracle_orders())
        if path.endswith("/staff_list"):
            return self._send(200, workday_staff())
        self._send(404, {"error": f"unknown path {path}"})

    def do_POST(self):
        if not self._ok_auth():
            return self._send(401, {"error": "unauthorised"})
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        path = urlparse(self.path).path
        RECEIVED.append({"path": path, "body": body, "at": time.strftime("%H:%M:%S")})
        print(f"  <- result {path}: {body}", flush=True)
        if path.endswith("/ProdnOrdConf2"):
            return self._send(201, {"d": {"MfgOrderConfirmation": f"CONF-{len(RECEIVED):05d}"}})
        if path.endswith("/workOrderOperationTransactions"):
            return self._send(201, {"TransactionId": 900000 + len(RECEIVED)})
        self._send(404, {"error": f"unknown path {path}"})

    def log_message(self, fmt, *args):
        print(f"  {self.command} {self.path.split('?')[0]} -> {args[1] if len(args) > 1 else ''}", flush=True)


def main():
    ap = argparse.ArgumentParser(description="Mock SAP / Oracle / Workday for connector tests")
    ap.add_argument("--port", type=int, default=8090)
    ap.add_argument("--user", default="mock")
    ap.add_argument("--password", default="mock123")
    a = ap.parse_args()
    Handler.user, Handler.password = a.user, a.password
    print(f"Mock ERP on http://127.0.0.1:{a.port}  (user {a.user})", flush=True)
    ThreadingHTTPServer(("127.0.0.1", a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
