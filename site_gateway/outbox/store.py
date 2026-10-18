"""
Store-and-forward queue. Every scan is written to a local SQLite file first,
then sent to the core API. If the network is down the scans wait here and
are sent, in order, when it comes back. Each scan carries a unique event_id,
so the core never counts a re-sent scan twice.
"""
import json
import sqlite3
import threading
from pathlib import Path


class OfflineQueue:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.execute("CREATE TABLE IF NOT EXISTS outbox (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                           "kind TEXT NOT NULL, payload TEXT NOT NULL, attempts INTEGER DEFAULT 0)")
        self._conn.commit()

    def put(self, kind, payload):
        with self._lock:
            self._conn.execute("INSERT INTO outbox (kind, payload) VALUES (?, ?)", (kind, json.dumps(payload)))
            self._conn.commit()

    def peek(self, limit=50):
        with self._lock:
            rows = self._conn.execute("SELECT id, kind, payload FROM outbox ORDER BY id LIMIT ?", (limit,)).fetchall()
        return [(r[0], r[1], json.loads(r[2])) for r in rows]

    def done(self, row_id):
        with self._lock:
            self._conn.execute("DELETE FROM outbox WHERE id = ?", (row_id,))
            self._conn.commit()

    def failed(self, row_id):
        with self._lock:
            self._conn.execute("UPDATE outbox SET attempts = attempts + 1 WHERE id = ?", (row_id,))
            self._conn.commit()

    def size(self):
        with self._lock:
            return self._conn.execute("SELECT COUNT(*) FROM outbox").fetchone()[0]
