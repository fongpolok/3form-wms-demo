"""Driver registry: settings.yaml `driver:` name -> class."""
from .honeywell_tcp import HoneywellTcpDriver

DRIVERS = {
    "honeywell_tcp": HoneywellTcpDriver,
    # Add new hardware brands here, e.g. "zebra_tcp": ZebraTcpDriver,
}
