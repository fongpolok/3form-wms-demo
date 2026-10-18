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
    conn, addr = srv.accept()
    print(f"Gateway connected from {addr}.", flush=True)

    if args.send:
        conn.sendall(args.send.encode() + b"\r\n")
        print(f"Sent {args.send}", flush=True)
        time.sleep(0.5)
        conn.close()
        return

    def drain():  # keep the socket healthy; scanners ignore input
        try:
            while conn.recv(1024):
                pass
        except OSError:
            pass
    threading.Thread(target=drain, daemon=True).start()
    print("Type a barcode and press Enter (Ctrl+C to quit):", flush=True)
    for line in sys.stdin:
        code = line.strip()
        if code:
            conn.sendall(code.encode() + b"\r\n")
            print(f"  beep -> {code}", flush=True)


if __name__ == "__main__":
    main()
