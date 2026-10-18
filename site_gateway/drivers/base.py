"""
Scanner driver interface. To support a new hardware brand, add a module in
this folder with a class that subclasses ScannerDriver, then register it in
DRIVERS (site_gateway/drivers/__init__.py) and set `driver:` in settings.yaml.
"""
import abc
import logging


class ScannerDriver(abc.ABC):
    def __init__(self, device_cfg, on_scan, on_status):
        """
        device_cfg: one entry of scanner_gateway.devices in settings.yaml
        on_scan(device_cfg, code): call for every barcode read
        on_status(device_cfg, status): call with "ok" / "down"
        """
        self.cfg = device_cfg
        self.on_scan = on_scan
        self.on_status = on_status
        self.log = logging.getLogger("scanner")

    @abc.abstractmethod
    async def run(self):
        """Run forever; reconnect on errors. Must never raise."""
