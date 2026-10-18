"""
Devices that send one text line per event over TCP/IP, ended by a terminator
(default CR LF). Used for barcode scanners, vision cameras and rack cameras.

mode: client -> the gateway connects to the device's IP:port (device is TCP server)
mode: server -> the gateway listens on port; the device connects in (device is TCP client)
"""
import asyncio

from .base import ScannerDriver


class LineTcpDriver(ScannerDriver):
    RECONNECT_MAX_SECONDS = 30

    def _terminator(self):
        t = self.cfg.get("terminator", "\r\n")
        return t.encode("utf-8").decode("unicode_escape").encode("latin-1")

    async def _read_stream(self, reader, peer):
        term = self._terminator()
        buf = b""
        self.on_status(self.cfg, "ok")
        self.log.info("%s connected (%s)", self.cfg["id"], peer)
        while True:
            chunk = await reader.read(1024)
            if not chunk:
                break
            buf += chunk
            while term in buf:
                raw, buf = buf.split(term, 1)
                code = raw.decode("utf-8", errors="replace").strip()
                if code:
                    self.on_scan(self.cfg, code)
        self.on_status(self.cfg, "down")
        self.log.warning("%s disconnected (%s)", self.cfg["id"], peer)

    async def _run_client(self):
        delay = 1
        while True:
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(self.cfg["host"], int(self.cfg["port"])), timeout=5)
                delay = 1
                await self._read_stream(reader, f"{self.cfg['host']}:{self.cfg['port']}")
                writer.close()
            except (OSError, asyncio.TimeoutError) as exc:
                self.on_status(self.cfg, "down")
                self.log.warning("%s cannot reach %s:%s (%s); retry in %ss", self.cfg["id"], self.cfg["host"],
                                 self.cfg["port"], exc, delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, self.RECONNECT_MAX_SECONDS)

    async def _run_server(self):
        async def handle(reader, writer):
            peer = writer.get_extra_info("peername")
            allowed = self.cfg.get("host")
            if allowed and allowed not in ("0.0.0.0", peer[0]):
                self.log.warning("%s rejected connection from unexpected IP %s", self.cfg["id"], peer[0])
                writer.close()
                return
            try:
                await self._read_stream(reader, peer)
            finally:
                writer.close()

        server = await asyncio.start_server(handle, "0.0.0.0", int(self.cfg["port"]))
        self.log.info("%s listening on port %s for scanner connections", self.cfg["id"], self.cfg["port"])
        self.on_status(self.cfg, "down")  # until the scanner connects
        async with server:
            await server.serve_forever()

    async def run(self):
        if self.cfg.get("mode", "client") == "server":
            await self._run_server()
        else:
            await self._run_client()


class HoneywellTcpDriver(LineTcpDriver):
    """Honeywell scanners (fixed-mount, or handhelds behind an Ethernet adapter). Each line = one barcode."""


class CognexTcpDriver(LineTcpDriver):
    """Cognex In-Sight (e.g. IS8500) set up to send `PASS` or `FAIL,<reason>` per inspection.
    The camera is a TCP server (default port 3000); the gateway connects as a client."""


class RackCameraTcpDriver(LineTcpDriver):
    """Rack camera sending `SLOT,<bin>,EMPTY|OCCUPIED|<goods code>` per checked slot."""
