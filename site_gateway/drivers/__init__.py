"""Driver registry: settings.yaml `driver:` name -> class. Add new hardware brands here."""
from .line_tcp import CognexTcpDriver, HoneywellTcpDriver, LineTcpDriver, RackCameraTcpDriver

DRIVERS = {
    "honeywell_tcp": HoneywellTcpDriver,
    "cognex_tcp": CognexTcpDriver,
    "rack_tcp": RackCameraTcpDriver,
    "line_tcp": LineTcpDriver,   # any device that sends one text line per event
}
