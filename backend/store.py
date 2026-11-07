"""Small persistent synthetic order system. No live customer data belongs here."""
import json
import math
import os
import sqlite3
import uuid
from datetime import datetime, timezone
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
              CREATE TABLE IF NOT EXISTS customers (id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, phone TEXT UNIQUE NOT NULL, record TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS channel_sessions (id TEXT PRIMARY KEY, record TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS returns (id TEXT PRIMARY KEY, record TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS activity (id TEXT PRIMARY KEY, record TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS media (id TEXT PRIMARY KEY, session_id TEXT NOT NULL, path TEXT NOT NULL);
            """)
        if self.setting("demo_now") is None:
            self.reset()
        self.seed_customers()
        if self.setting("erp_samples_v1") is None:
            for order in json.loads((ROOT / "data/orders.json").read_text()):
                with self.connect() as db:
                    db.execute("INSERT OR IGNORE INTO orders VALUES (?,?,?)", (order["order_id"], order["customer_id"], json.dumps(order)))
            self.set_setting("erp_samples_v1", True)
        if self.setting("verification_mode") is None:
            self.set_setting("verification_mode", "demo_match")
        if self.setting("inference_mode") is None:
            self.set_setting("inference_mode", "model")
        for sample in json.loads((ROOT / "data/orders.json").read_text()):
            record = self.order(sample["order_id"])
            if not record:
                continue
            original = json.dumps(record, sort_keys=True)
            for key in ("payment_status", "priority", "revision", "notes"):
                record.setdefault(key, sample.get(key, ""))
            for item in record["items"]:
                fixture = next((i for i in sample["items"] if i["item_id"] == item["item_id"]), {})
                if "unit_price" in fixture:
                    item.setdefault("unit_price", fixture["unit_price"])
            if json.dumps(record, sort_keys=True) != original:
                self.save_order(record)
        from .region import migrate
        migrate(self, ROOT)

    def seed_customers(self):
        customers = json.loads((ROOT / "data/customers.json").read_text())
        with self.connect() as db:
            for customer in customers:
                db.execute("INSERT OR IGNORE INTO customers VALUES (?,?,?,?)", (customer["customer_id"], customer["email"].lower(), customer["phone"], json.dumps(customer)))
                row = db.execute("SELECT record FROM customers WHERE id=?", (customer["customer_id"],)).fetchone()
                if row:
                    merged = {**customer, **json.loads(row[0])}
                    db.execute("UPDATE customers SET record=? WHERE id=?", (json.dumps(merged), customer["customer_id"]))

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
            for table in ("settings", "orders", "tickets", "traces", "customers", "channel_sessions", "returns", "activity", "media"):
                db.execute(f"DELETE FROM {table}")  # fixed internal identifiers
            db.execute("UPDATE sessions SET history='[]'")
            for name, value in {**config, "policy": policy, "ticket_store_available": True, "verification_mode": "demo_match", "inference_mode": "model"}.items():
                db.execute("INSERT INTO settings VALUES (?,?)", (name, json.dumps(value)))
            for order in orders:
                db.execute("INSERT INTO orders VALUES (?,?,?)", (order["order_id"], order["customer_id"], json.dumps(order)))
        self.seed_customers()

    def customer(self, customer_id):
        with self.connect() as db:
            row = db.execute("SELECT record FROM customers WHERE id=?", (customer_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def find_customer(self, identifier):
        identifier = identifier.strip()
        if identifier.upper().startswith("CUS"):
            suffix = identifier[3:].lstrip("-")
            if suffix.isdigit():
                identifier = "CUS-" + suffix
        normalized = identifier.strip().lower()
        if "@" not in normalized:
            digits = "".join(c for c in normalized if c.isdigit())
            if len(digits) == 10:
                digits = "91" + digits
            normalized = "+" + digits
        with self.connect() as db:
            row = db.execute("SELECT record FROM customers WHERE email=? OR phone=? OR lower(id)=? OR lower(json_extract(record,'$.display_id'))=?", (normalized, normalized, identifier.strip().lower(), identifier.strip().lower())).fetchone()
        return json.loads(row[0]) if row else None

    def bind_customer(self, session_id, customer):
        with self.connect() as db:
            db.execute("UPDATE sessions SET customer=?, history='[]' WHERE id=?", (customer, session_id))

    def channel(self, session_id):
        with self.connect() as db:
            row = db.execute("SELECT record FROM channel_sessions WHERE id=?", (session_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def save_channel(self, record):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO channel_sessions VALUES (?,?)", (record["id"], json.dumps(record)))

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

    def all_records(self, table):
        assert table in ("customers", "channel_sessions", "returns", "activity")
        with self.connect() as db:
            rows = db.execute(f"SELECT record FROM {table} ORDER BY rowid DESC LIMIT 500").fetchall()
        return [json.loads(row[0]) for row in rows]

    def log(self, entity, entity_id, action, summary, changes=None, actor="Store admin"):
        entry = {"id": "ACT-" + uuid.uuid4().hex[:10], "at": datetime.now(timezone.utc).isoformat(), "entity": entity, "entity_id": entity_id, "action": action, "summary": summary, "changes": changes or {}, "actor": actor}
        with self.connect() as db:
            db.execute("INSERT INTO activity VALUES (?,?)", (entry["id"], json.dumps(entry)))
        return entry

    def save_customer(self, customer):
        with self.connect() as db:
            db.execute("INSERT INTO customers VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET email=excluded.email,phone=excluded.phone,record=excluded.record", (customer["customer_id"], customer["email"].lower(), customer["phone"], json.dumps(customer)))

    def insert_order(self, order):
        with self.connect() as db:
            db.execute("INSERT INTO orders VALUES (?,?,?)", (order["order_id"], order["customer_id"], json.dumps(order)))

    def next_id(self, entity):
        assert entity in ("orders", "customers", "returns")
        start = {"orders": 5000, "customers": 1000, "returns": 1000}[entity]
        prefix = {"orders": "", "customers": "CUS-", "returns": "RMA-"}[entity]
        with self.connect() as db:
            values = [r[0] for r in db.execute(f"SELECT id FROM {entity}")]
            if entity == "customers":
                values.extend(json.loads(r[0]).get("display_id", "") for r in db.execute("SELECT record FROM customers"))
        numbers = [int(v.removeprefix(prefix)) for v in values if v.removeprefix(prefix).isdigit()]
        return prefix + str(max([start, *numbers]) + 1)

    def return_for_item(self, order_id, item_id):
        return next((r for r in self.all_records("returns") if r["order_id"] == order_id and r["item_id"] == item_id), None)

    def save_return(self, record):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO returns VALUES (?,?)", (record["id"], json.dumps(record)))

    def create_return_once(self, record):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = [json.loads(r[0]) for r in db.execute("SELECT record FROM returns ORDER BY rowid DESC")]
            existing = next((r for r in rows if r["order_id"] == record["order_id"] and r["item_id"] == record["item_id"] and r["status"] != "declined"), None)
            if existing:
                return existing
            number = max([1000, *[int(r["id"].removeprefix("RMA-")) for r in rows]]) + 1
            record = {**record, "id": "RMA-" + str(number)}
            db.execute("INSERT INTO returns VALUES (?,?)", (record["id"], json.dumps(record)))
            return record

    def transition_return(self, before, after):
        """Commit return and payment projection together, rejecting stale staff edits."""
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT record FROM returns WHERE id=?", (before["id"],)).fetchone()
            if not row or json.loads(row[0]) != before:
                raise ValueError("return_conflict")
            if after["status"] != before["status"] and after["status"] in ("received", "refunded"):
                row = db.execute("SELECT record FROM orders WHERE id=?", (after["order_id"],)).fetchone()
                order = json.loads(row[0]) if row else None
                item = next((i for i in order["items"] if i["item_id"] == after["item_id"]), None) if order else None
                if not item or not math.isfinite(item["unit_price"]) or not math.isfinite(after["refund_amount"]):
                    raise ValueError("invalid_return_value")
                if not item or type(after["quantity"]) is not int or not 1 <= after["quantity"] <= item["quantity"] or abs(item["unit_price"] * after["quantity"] - after["refund_amount"]) > .01:
                    raise ValueError("return_value_mismatch")
                item["returned"] = after["quantity"] >= item["quantity"]
                if after["status"] == "refunded":
                    order["payment_status"] = "refunded" if all(i.get("returned") for i in order["items"]) else "partially_refunded"
                order["revision"] = order.get("revision", 1) + 1
                order["source_updated_at"] = datetime.now(timezone.utc).isoformat()
                db.execute("UPDATE orders SET record=? WHERE id=?", (json.dumps(order), order["order_id"]))
            db.execute("UPDATE returns SET record=? WHERE id=?", (json.dumps(after), after["id"]))

    def update_ticket(self, ticket):
        with self.connect() as db:
            if ticket["status"] == "resolved":
                db.execute("UPDATE tickets SET record=?, dedup_key=id WHERE id=?", (json.dumps(ticket), ticket["id"]))
            else:
                db.execute("UPDATE tickets SET record=? WHERE id=?", (json.dumps(ticket), ticket["id"]))

    def conversation(self, reference):
        return next((c for c in self.all_records("channel_sessions") if c.get("reference", c["id"][:10]) == reference), None)

    def revise_order(self, order_id, transform, expected_revision=None):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT record FROM orders WHERE id=?", (order_id,)).fetchone()
            if not row:
                raise KeyError(order_id)
            before = json.loads(row[0])
            if expected_revision is not None and expected_revision != before.get("revision", 1):
                raise ValueError("revision_conflict")
            after = transform(json.loads(row[0]))
            after["revision"] = before.get("revision", 1) + 1
            after["source_updated_at"] = datetime.now(timezone.utc).isoformat()
            db.execute("UPDATE orders SET record=? WHERE id=?", (json.dumps(after), order_id))
        return before, after

    def save_trace(self, trace, session_id):
        with self.connect() as db:
            db.execute("INSERT INTO traces VALUES (?,?,?)", (trace["id"], session_id, json.dumps(trace)))

    def save_ticket(self, ticket, session_id, dedup_key):
        # A uniqueness constraint also protects simultaneous duplicate requests.
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO tickets VALUES (?,?,?,?)", (ticket["id"], session_id, dedup_key, json.dumps(ticket)))
            row = db.execute("SELECT record FROM tickets WHERE dedup_key=?", (dedup_key,)).fetchone()
        return json.loads(row[0])
