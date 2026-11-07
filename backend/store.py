"""Small persistent synthetic order system. No live customer data belongs here."""
import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Store:
    def __init__(self, path=None):
        self.path = str(path or os.environ.get("THREADLINE_DB", ROOT / "artifacts/local/threadline.db"))
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
              CREATE TABLE IF NOT EXISTS settings (name TEXT PRIMARY KEY, value TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS orders (id TEXT PRIMARY KEY, customer TEXT NOT NULL, record TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, customer TEXT, history TEXT NOT NULL DEFAULT '[]');
              CREATE TABLE IF NOT EXISTS tickets (id TEXT PRIMARY KEY, session_id TEXT NOT NULL, dedup_key TEXT UNIQUE NOT NULL, record TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS traces (id TEXT PRIMARY KEY, session_id TEXT NOT NULL, record TEXT NOT NULL);
            """)
        if self.setting("demo_now") is None:
            self.reset()

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def reset(self):
        config = json.loads((ROOT / "data/demo-config.json").read_text())
        policy = json.loads((ROOT / "data/return-policy.json").read_text())
        orders = json.loads((ROOT / "data/orders.json").read_text())
        with self.connect() as db:
            for table in ("settings", "orders", "tickets", "traces"):
                db.execute(f"DELETE FROM {table}")  # fixed internal identifiers
            db.execute("UPDATE sessions SET history='[]'")
            for name, value in {**config, "policy": policy, "ticket_store_available": True}.items():
                db.execute("INSERT INTO settings VALUES (?,?)", (name, json.dumps(value)))
            for order in orders:
                db.execute("INSERT INTO orders VALUES (?,?,?)", (order["order_id"], order["customer_id"], json.dumps(order)))

    def setting(self, name):
        with self.connect() as db:
            row = db.execute("SELECT value FROM settings WHERE name=?", (name,)).fetchone()
        return json.loads(row[0]) if row else None

    def settings(self):
        with self.connect() as db:
            rows = db.execute("SELECT name,value FROM settings").fetchall()
        return {row[0]: json.loads(row[1]) for row in rows}

    def set_setting(self, name, value):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (name, json.dumps(value)))

    def orders(self, customer=None):
        with self.connect() as db:
            rows = db.execute("SELECT record FROM orders" + (" WHERE customer=?" if customer else "") + " ORDER BY id", (customer,) if customer else ()).fetchall()
        return [json.loads(row[0]) for row in rows]

    def order(self, order_id):
        with self.connect() as db:
            row = db.execute("SELECT record FROM orders WHERE id=?", (order_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def save_order(self, order):
        with self.connect() as db:
            db.execute("UPDATE orders SET record=? WHERE id=?", (json.dumps(order), order["order_id"]))

    def new_session(self, session_id, customer):
        with self.connect() as db:
            db.execute("INSERT INTO sessions(id,customer) VALUES (?,?)", (session_id, customer))

    def session(self, session_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        return {"id": row["id"], "customer": row["customer"], "history": json.loads(row["history"])} if row else None

    def save_history(self, session_id, history):
        with self.connect() as db:
            db.execute("UPDATE sessions SET history=? WHERE id=?", (json.dumps(history[-20:]), session_id))

    def records(self, table, session_id=None):
        assert table in ("tickets", "traces")
        with self.connect() as db:
            rows = db.execute(f"SELECT record FROM {table}" + (" WHERE session_id=?" if session_id else "") + " ORDER BY rowid DESC LIMIT 100", (session_id,) if session_id else ()).fetchall()
        return [json.loads(row[0]) for row in rows]

    def save_trace(self, trace, session_id):
        with self.connect() as db:
            db.execute("INSERT INTO traces VALUES (?,?,?)", (trace["id"], session_id, json.dumps(trace)))

    def save_ticket(self, ticket, session_id, dedup_key):
        # A uniqueness constraint also protects simultaneous duplicate requests.
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO tickets VALUES (?,?,?,?)", (ticket["id"], session_id, dedup_key, json.dumps(ticket)))
            row = db.execute("SELECT record FROM tickets WHERE dedup_key=?", (dedup_key,)).fetchone()
        return json.loads(row[0])
