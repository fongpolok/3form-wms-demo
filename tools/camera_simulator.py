"""
Pretend to be a camera (TCP server), for testing without hardware.

Vision camera (like a Cognex In-Sight set up to send PASS / FAIL,<reason>):
    python tools/camera_simulator.py --mode vision --port 3000 --every 5 --fail-rate 0.1
Rack camera (SLOT,<bin>,EMPTY|OCCUPIED|<goods code>):
    python tools/camera_simulator.py --mode rack --port 3100
Either mode: type any line + Enter to send it exactly (e.g. "FAIL,Cap missing").
"""
import argparse
import random
import socket
import sys
import threading
import time

REASONS = ["Cap missing", "Label skewed", "Fill level low", "Seal defect"]


def main():
    ap = argparse.ArgumentParser(description="Camera simulator")
    ap.add_argument("--mode", choices=["vision", "rack"], default="vision")
    ap.add_argument("--port", type=int, default=3000)
    ap.add_argument("--every", type=float, default=0, help="auto-send a result every N seconds (vision only)")
    ap.add_argument("--fail-rate", type=float, default=0.1)
    args = ap.parse_args()

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", args.port))
    srv.listen(1)
    print(f"Simulated {args.mode} camera on 127.0.0.1:{args.port}. Waiting for the gateway...", flush=True)
    state = {"conn": None}
    lock = threading.Lock()

    def accept_loop():   # like a real camera: the gateway may disconnect and reconnect at any time
        while True:
            c, a = srv.accept()
            with lock:
                state["conn"] = c
            print(f"Gateway connected from {a}.", flush=True)

    threading.Thread(target=accept_loop, daemon=True).start()

    def send(line):
        with lock:
            c = state["conn"]
            if c is None:
                print(f"  (no gateway connected; dropped {line})", flush=True)
                return
            try:
                c.sendall(line.encode() + b"\r\n")
            except OSError:
                state["conn"] = None
                print(f"  (gateway gone; dropped {line})", flush=True)
                return
        print(f"  -> {line}", flush=True)

    if args.mode == "vision" and args.every > 0:
        def auto():
            while True:
                time.sleep(args.every)
                send(f"FAIL,{random.choice(REASONS)}" if random.random() < args.fail_rate else "PASS")
        threading.Thread(target=auto, daemon=True).start()

    print("Type a line and press Enter to send it (Ctrl+C to quit):", flush=True)
    for line in sys.stdin:
        if line.strip():
            send(line.strip())
    while args.every > 0:          # stdin closed but auto mode still running
        time.sleep(1)


if __name__ == "__main__":
    main()
