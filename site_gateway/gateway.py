"""
3Form site gateway — runs inside the factory, always.

  * reads barcodes from scanners (drivers/), tags each with the workstation
  * writes every scan to a local outbox first, then forwards it to the core API
  * sends a heartbeat so screens can raise the network alarm
  * keeps working when the core / internet is down; catches up later

Run:  python -m site_gateway.gateway            (from the project folder)
Env:  GATEWAY_TOKEN (must match the core's .env), optional GATEWAY_ID
"""
import asyncio
import json
import logging
import logging.handlers
import os
import sys
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .drivers import DRIVERS
from .outbox.store import OfflineQueue

BASE_DIR = Path(__file__).resolve().parent.parent
log = logging.getLogger("scanner")


def load_env(path):
    """Tiny .env reader so the gateway needs no extra packages."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def setup_logging(settings):
    log_dir = BASE_DIR / settings.get("logging", {}).get("dir", "logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("[%(asctime)s][%(name)s.%(funcName)s():%(lineno)d] [%(levelname)s] %(message)s")
    fh = logging.handlers.TimedRotatingFileHandler(log_dir / "scanner.log", when="midnight", encoding="utf-8",
                                                   backupCount=int(settings.get("logging", {}).get("keep_days", 90)))
    sh = logging.StreamHandler(sys.stdout)
    for h in (fh, sh):
        h.setFormatter(fmt)
        log.addHandler(h)
    log.setLevel(settings.get("logging", {}).get("level", "INFO"))


class Gateway:
    def __init__(self, settings):
        self.settings = settings
        gw = settings["scanner_gateway"]
        self.cfg = gw
        self.base_url = os.environ.get("GATEWAY_FORWARD_URL", gw["forward_url"]).rstrip("/")
        self.token = os.environ.get("GATEWAY_TOKEN", "")
        self.gateway_id = os.environ.get("GATEWAY_ID", "GW-" + settings["site"]["code"])
        self.outbox = OfflineQueue(BASE_DIR / gw["offline_queue_file"])
        self.status = {d["id"]: "down" for d in gw["devices"]}
        self.core_online = None
        if not self.token:
            log.error("GATEWAY_TOKEN is empty; the core will refuse every scan.")

    # -- callbacks from drivers ------------------------------------------------
    def on_scan(self, device, code):
        payload = {"event_id": uuid.uuid4().hex, "device_id": device["id"], "workstation": device["workstation"],
                   "code": code, "ts": datetime.now(timezone.utc).isoformat()}
        self.outbox.put("scan", payload)
        log.info("Scan %r from %s (%s) queued", code, device["id"], device["workstation"])

    def on_status(self, device, status):
        if self.status.get(device["id"]) != status:
            log.info("Device %s is now %s", device["id"], status)
        self.status[device["id"]] = status

    # -- HTTP -------------------------------------------------------------------
    def _post(self, path, payload):
        req = urllib.request.Request(self.base_url + path, data=json.dumps(payload).encode("utf-8"), method="POST",
                                     headers={"Content-Type": "application/json", "X-Gateway-Token": self.token})
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status

    def _set_core_online(self, online):
        if online != self.core_online:
            (log.info if online else log.error)("Core API is %s (%s)", "reachable" if online else "UNREACHABLE",
                                                self.base_url)
        self.core_online = online

    async def forward_loop(self):
        loop = asyncio.get_running_loop()
        while True:
            sent_any, failed = False, False
            for row_id, kind, payload in self.outbox.peek():
                try:
                    await loop.run_in_executor(None, self._post, "/scans", payload)
                    self.outbox.done(row_id)
                    sent_any = True
                    self._set_core_online(True)
                except urllib.error.HTTPError as exc:
                    if 400 <= exc.code < 500 and exc.code not in (401, 403, 429):
                        log.error("Core rejected scan %s (%s); dropping it", payload.get("event_id"), exc.code)
                        self.outbox.done(row_id)
                        continue
                    self.outbox.failed(row_id)
                    log.warning("Core refused scan (%s); will retry. Queue size %d", exc.code, self.outbox.size())
                    failed = True
                    break
                except (urllib.error.URLError, OSError) as exc:
                    self.outbox.failed(row_id)
                    self._set_core_online(False)
                    log.warning("Core unreachable (%s); %d scan(s) waiting", exc, self.outbox.size())
                    failed = True
                    break
            if failed:
                await asyncio.sleep(float(self.cfg.get("retry_seconds", 5)))
            else:
                await asyncio.sleep(0.05 if sent_any else 0.3)

    async def heartbeat_loop(self):
        loop = asyncio.get_running_loop()
        interval = float(self.settings.get("network_alarm", {}).get("heartbeat_interval_seconds", 3))
        while True:
            payload = {"gateway_id": self.gateway_id, "queue_size": self.outbox.size(),
                       "devices": [{"device_id": d["id"], "workstation": d["workstation"], "kind": "scanner",
                                    "status": self.status.get(d["id"], "down")} for d in self.cfg["devices"]]}
            try:
                await loop.run_in_executor(None, self._post, "/heartbeat", payload)
                self._set_core_online(True)
            except (urllib.error.URLError, OSError) as exc:
                self._set_core_online(False)
                log.debug("Heartbeat failed: %s", exc)
            await asyncio.sleep(interval)

    async def run(self):
        tasks = [asyncio.create_task(self.forward_loop()), asyncio.create_task(self.heartbeat_loop())]
        for device in self.cfg["devices"]:
            driver_cls = DRIVERS.get(device["driver"])
            if driver_cls is None:
                log.error("Unknown driver %r for %s; skipped. Known: %s", device["driver"], device["id"], list(DRIVERS))
                continue
            tasks.append(asyncio.create_task(driver_cls(device, self.on_scan, self.on_status).run()))
            log.info("Started %s driver for %s -> %s", device["driver"], device["id"], device["workstation"])
        log.info("Gateway %s running; forwarding to %s; %d scan(s) waiting in outbox",
                 self.gateway_id, self.base_url, self.outbox.size())
        await asyncio.gather(*tasks)


def main():
    load_env(BASE_DIR / ".env")
    settings_file = Path(os.environ.get("THREEFORM_SETTINGS_FILE", BASE_DIR / "config" / "settings.yaml"))
    settings = yaml.safe_load(settings_file.read_text(encoding="utf-8"))
    setup_logging(settings)
    try:
        asyncio.run(Gateway(settings).run())
    except KeyboardInterrupt:
        log.info("Gateway stopped by user")


if __name__ == "__main__":
    main()
