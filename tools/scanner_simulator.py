"""
Pretend to be a Honeywell scanner in TCP server mode, for testing without hardware.

    python tools/scanner_simulator.py --port 55256            # then type barcodes + Enter
    python tools/scanner_simulator.py --port 55256 --send B-20261019-0001

The gateway (mode: client) connects to this port and receives each line
followed by CR LF, exactly like the real scanner.
"""
import argparse
import socket
import sys
import threading
import time


def main():
    ap = argparse.ArgumentParser(description="Honeywell TCP scanner simulator")
    ap.add_argument("--port", type=int, default=55256)
    ap.add_argument("--send", help="Send one barcode as soon as the gateway connects, then exit")
    args = ap.parse_args()

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", args.port))
    srv.listen(1)
    print(f"Simulated scanner listening on 127.0.0.1:{args.port}. Waiting for the gateway...", flush=True)
    state = {"conn": None}
    lock = threading.Lock()
    ready = threading.Event()

    def accept_loop():   # like a real scanner: the gateway may disconnect and reconnect at any time
        while True:
            c, a = srv.accept()
            with lock:
                state["conn"] = c
            print(f"Gateway connected from {a}.", flush=True)
            ready.set()

    threading.Thread(target=accept_loop, daemon=True).start()

    def send(code):
        with lock:
            c = state["conn"]
            if c is None:
                return False
            try:
                c.sendall(code.encode() + b"\r\n")
                return True
            except OSError:
                state["conn"] = None
                return False

    if args.send:
        ready.wait()
        send(args.send)
        print(f"Sent {args.send}", flush=True)
        time.sleep(0.5)
        return

    print("Type a barcode and press Enter (Ctrl+C to quit):", flush=True)
    for line in sys.stdin:
        code = line.strip()
        if code:
            print(f"  beep -> {code}" if send(code) else f"  (no gateway connected; dropped {code})", flush=True)
    while True:          # stdin closed: keep serving reconnects
        time.sleep(1)


if __name__ == "__main__":
    main()
