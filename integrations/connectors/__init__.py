from .base import Connector, ErpError
from .oracle import OracleConnector
from .sap import SapConnector
from .workday import WorkdayConnector

ADAPTERS = {"SAP": SapConnector, "ORACLE": OracleConnector, "WORKDAY": WorkdayConnector}


def for_connection(conn):
    cls = ADAPTERS.get(conn.system)
    if cls is None:
        raise ErpError(f"No connector for system '{conn.system}' yet. Choose SAP, Oracle or Workday.")
    return cls(conn)
