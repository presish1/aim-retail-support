"""Retail operations endpoints for the local, synthetic ERP."""
import re
import sqlite3
from datetime import date
from typing import Literal

from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .service import iso_now


CATALOG = [
    {"sku": "TL-HOOD-01", "name": "Weekday Hoodie", "price": 78, "color": "Forest"},
    {"sku": "TL-OXFD-02", "name": "Everyday Oxford", "price": 64, "color": "White"},
    {"sku": "TL-CHIN-03", "name": "Straight-leg Chino", "price": 72, "color": "Stone"},
    {"sku": "TL-TEE-04", "name": "Archive Tee", "price": 28, "color": "Ink"},
    {"sku": "TL-CARD-05", "name": "Ribbed Cardigan", "price": 88, "color": "Oat"},
    {"sku": "TL-OVER-06", "name": "Canvas Overshirt", "price": 96, "color": "Navy"},
    {"sku": "TL-JACK-07", "name": "Utility Jacket", "price": 112, "color": "Olive"},
]


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CustomerBody(Body):
    first_name: str = Field(min_length=1, max_length=60)
    last_name: str = Field(default="", max_length=60)
    email: str = Field(min_length=5, max_length=150)
    phone: str = Field(min_length=7, max_length=30)
    city: str = Field(default="", max_length=100)
    notes: str = Field(default="", max_length=1000)


class Line(Body):
    sku: str
    quantity: int = Field(default=1, ge=1, le=10)
    size: str = Field(default="M", max_length=10)


class NewOrder(Body):
    customer_id: str
    items: list[Line] = Field(min_length=1, max_length=10)
    shipping_city: str = Field(min_length=1, max_length=100)
    payment_status: Literal["paid", "pending"] = "paid"
    priority: Literal["normal", "high"] = "normal"
    notes: str = Field(default="", max_length=1000)


class OrderPatch(Body):
    status: Literal["processing", "in_transit", "delivered", "partially_delivered", "cancelled", "returned"] | None = None
    carrier_eta_date: str | None = None
    carrier: str | None = Field(default=None, max_length=80)
    tracking_reference: str | None = Field(default=None, max_length=100)
    shipping_city: str | None = Field(default=None, max_length=100)
    payment_status: Literal["paid", "pending", "partially_refunded", "refunded"] | None = None
    priority: Literal["normal", "high"] | None = None
    notes: str | None = Field(default=None, max_length=2000)
    revision: int | None = None


class ReturnCreate(Body):
    order_id: str
    item_id: str
    reason: str = Field(min_length=1, max_length=200)
    quantity: int = Field(default=1, ge=1)


class ReturnPatch(Body):
    status: Literal["requested", "approved", "declined", "received", "refunded"]
    notes: str = Field(default="", max_length=1000)


class TicketPatch(Body):
    status: Literal["queued", "in_progress", "resolved"]
    assignee: str = Field(default="Unassigned", max_length=80)
    internal_note: str = Field(default="", max_length=1000)


def state(store):
    conversations = []
    for channel in store.all_records("channel_sessions"):
        session = store.session(channel["id"])
        customer = store.customer(session["customer"]) if session and session["customer"] else None
        last = channel["messages"][-1] if channel["messages"] else {}
        conversations.append({"reference": channel.get("reference", channel["id"][:10]), "customer_id": customer["customer_id"] if customer else None,
                              "customer_name": full_name(customer) if customer else "Unmatched visitor", "stage": channel["stage"], "order_id": channel.get("selected_order"),
                              "last_message": last.get("text", ""), "updated_at": last.get("at", channel.get("created_at", "")), "message_count": len(channel["messages"]),
                              "verification_code": channel.get("demo_code") if channel["stage"] == "code" else None,
                              "mode": (channel.get("latest_trace") or {}).get("mode")})
    return {"orders": store.orders(), "customers": store.all_records("customers"), "returns": store.all_records("returns"),
            "settings": store.settings(), "tickets": store.records("tickets"), "traces": store.records("traces"),
            "activity": store.all_records("activity"), "conversations": sorted(conversations, key=lambda c: c["updated_at"], reverse=True), "catalog": CATALOG}


def full_name(customer):
    return " ".join(str(customer.get(k, "")) for k in ("first_name", "last_name")).strip()


async def update_order(store, workflow, hub, order_id, body):
    fields = body.model_dump(exclude_unset=True)
    expected = fields.pop("revision", None)
    if any(value is None for key, value in fields.items() if key != "carrier_eta_date"):
        raise HTTPException(422, "Order fields cannot be empty. Use an empty string to clear optional text.")
    if fields.get("carrier_eta_date"):
        try:
            fields["carrier_eta_date"] = date.fromisoformat(fields["carrier_eta_date"]).isoformat()
        except ValueError:
            raise HTTPException(422, "Use a valid delivery estimate date.")

    def apply(order):
        order.update(fields)
        if order["status"] == "delivered":
            order["carrier_eta_date"] = None
            for item in order["items"]:
                item["status"] = "delivered"
                item["delivered_at"] = item.get("delivered_at") or store.setting("demo_now")
        elif "status" in fields and order["status"] in ("processing", "in_transit", "cancelled"):
            for item in order["items"]:
                item["status"] = order["status"]
                item["delivered_at"] = None
        return order

    try:
        before, after = store.revise_order(order_id, apply, expected)
    except KeyError:
        raise HTTPException(404, "Order not found.")
    except ValueError:
        raise HTTPException(409, "This order was changed in another tab. Reload the current record before saving.")
    changes = {k: {"before": before.get(k), "after": after.get(k)} for k in fields if before.get(k) != after.get(k)}
    summary = f"Order #{order_id} updated"
    if "status" in changes:
        summary = f"Order #{order_id}: {str(before['status']).replace('_', ' ')} → {str(after['status']).replace('_', ' ')}"
    store.log("order", order_id, "updated", summary, changes)
    await hub.source_changed(store, order_id, workflow=workflow, before=before, notify=True)
    return {"order": after, "saved_at": iso_now(), "source": "SQLite"}


def register(app, get_store, get_workflow, get_hub, require_admin):
    auth = [Depends(require_admin)]

    @app.post("/api/studio/customers", dependencies=auth)
    async def create_customer(body: CustomerBody):
        store = get_store()
        email = body.email.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            raise HTTPException(422, "Enter a valid email address.")
        digits = re.sub(r"\D", "", body.phone)
        if len(digits) == 10:
            digits = "1" + digits
        if not 10 <= len(digits) <= 15:
            raise HTTPException(422, "Enter a phone number with country code.")
        customer = {**body.model_dump(), "customer_id": store.next_id("customers"), "email": email, "phone": "+" + digits, "created_at": iso_now(), "synthetic": True}
        customer["display_id"] = customer["customer_id"]
        try:
            store.save_customer(customer)
        except sqlite3.IntegrityError:
            raise HTTPException(409, "A customer with that email or phone number already exists.")
        store.log("customer", customer["customer_id"], "created", f"Customer {full_name(customer)} created")
        await get_hub().studio_changed("customers", customer["customer_id"])
        return customer

    @app.patch("/api/studio/customers/{customer_id}", dependencies=auth)
    async def edit_customer(customer_id: str, body: CustomerBody):
        store = get_store()
        customer = store.customer(customer_id)
        if not customer:
            raise HTTPException(404, "Customer not found.")
        email = body.email.strip().lower()
        digits = re.sub(r"\D", "", body.phone)
        if len(digits) == 10:
            digits = "1" + digits
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email) or not 10 <= len(digits) <= 15:
            raise HTTPException(422, "Check the email address and phone number.")
        customer.update(body.model_dump(), email=email, phone="+" + digits)
        try:
            store.save_customer(customer)
        except sqlite3.IntegrityError:
            raise HTTPException(409, "That email or phone belongs to another customer.")
        store.log("customer", customer_id, "updated", f"Customer {full_name(customer)} updated")
        await get_hub().studio_changed("customers", customer_id)
        return customer

    @app.post("/api/studio/orders", dependencies=auth)
    async def create_order(body: NewOrder):
        store = get_store()
        if not store.customer(body.customer_id):
            raise HTTPException(404, "Select an existing customer.")
        order_id = store.next_id("orders")
        items = []
        for n, line in enumerate(body.items, 1):
            product = next((p for p in CATALOG if p["sku"] == line.sku), None)
            if not product:
                raise HTTPException(422, "Select an item from the product list.")
            items.append({"item_id": f"{order_id}-{n}", "sku": product["sku"], "name": product["name"], "quantity": line.quantity,
                          "unit_price": product["price"], "size": line.size, "color": product["color"], "status": "processing", "delivered_at": None, "final_sale": False, "returned": False})
        order = {"order_id": order_id, "customer_id": body.customer_id, "policy_version": store.setting("policy")["version"], "status": "processing", "carrier": "Unassigned", "carrier_eta_date": None,
                 "source_updated_at": iso_now(), "ordered_at": store.setting("demo_now"), "tracking_url": None, "tracking_reference": "", "shipping_city": body.shipping_city,
                 "currency": "USD", "order_total": sum(i["quantity"] * i["unit_price"] for i in items), "payment_status": body.payment_status, "priority": body.priority, "notes": body.notes, "revision": 1, "items": items}
        store.insert_order(order)
        store.log("order", order_id, "created", f"Order #{order_id} created", {"total": order["order_total"]})
        await get_hub().source_changed(store, order_id)
        return order

    @app.post("/api/studio/returns", dependencies=auth)
    async def create_return(body: ReturnCreate):
        store = get_store()
        order = store.order(body.order_id)
        item = next((i for i in order["items"] if i["item_id"] == body.item_id), None) if order else None
        if not item or not item.get("delivered_at"):
            raise HTTPException(422, "A return must reference a delivered item.")
        if body.quantity > item.get("quantity", 1):
            raise HTTPException(422, "Return quantity exceeds the purchased quantity.")
        existing = store.return_for_item(body.order_id, body.item_id)
        if existing and existing["status"] != "declined":
            raise HTTPException(409, "An existing return already covers this item.")
        record = {**body.model_dump(), "id": store.next_id("returns"), "customer_id": order["customer_id"], "item_name": item["name"], "status": "requested", "created_at": iso_now(), "updated_at": iso_now(), "notes": "", "refund_amount": body.quantity * item.get("unit_price", order["order_total"] if len(order["items"]) == 1 else 0)}
        store.save_return(record)
        store.log("return", record["id"], "created", f"Return {record['id']} requested for order #{body.order_id}")
        await get_hub().studio_changed("returns", record["id"])
        return record

    @app.patch("/api/studio/returns/{return_id}", dependencies=auth)
    async def edit_return(return_id: str, body: ReturnPatch):
        store = get_store()
        record = next((r for r in store.all_records("returns") if r["id"] == return_id), None)
        if not record:
            raise HTTPException(404, "Return not found.")
        allowed = {"requested": {"approved", "declined"}, "approved": {"received", "declined"}, "received": {"refunded"}, "declined": {"requested"}, "refunded": set()}
        if body.status != record["status"] and body.status not in allowed[record["status"]]:
            raise HTTPException(409, "Complete the preceding return steps before this transition.")
        before = record["status"]
        record.update(status=body.status, notes=body.notes, updated_at=iso_now())
        store.save_return(record)
        if body.status in ("received", "refunded"):
            def apply(order):
                item = next(i for i in order["items"] if i["item_id"] == record["item_id"])
                item["returned"] = record["quantity"] >= item.get("quantity", 1)
                if body.status == "refunded":
                    order["payment_status"] = "refunded" if all(i.get("returned") for i in order["items"]) else "partially_refunded"
                return order
            store.revise_order(record["order_id"], apply)
        store.log("return", return_id, "updated", f"Return {return_id}: {before} → {body.status}", {"status": {"before": before, "after": body.status}})
        await get_hub().studio_changed("returns", return_id)
        return record

    @app.patch("/api/studio/tickets/{ticket_id}", dependencies=auth)
    async def edit_ticket(ticket_id: str, body: TicketPatch):
        store = get_store()
        ticket = next((t for t in store.records("tickets") if t["id"] == ticket_id), None)
        if not ticket:
            raise HTTPException(404, "Support request not found.")
        ticket.update(body.model_dump(), updated_at=iso_now())
        store.update_ticket(ticket)
        store.log("ticket", ticket_id, "updated", f"Support request {ticket_id} {body.status.replace('_', ' ')}")
        await get_hub().studio_changed("tickets", ticket_id)
        return ticket

    @app.get("/api/studio/conversations/{reference}", dependencies=auth)
    def conversation_detail(reference: str):
        record = get_store().conversation(reference)
        if not record:
            raise HTTPException(404, "Conversation not found.")
        return {"reference": reference, "messages": record["messages"], "stage": record["stage"], "latest_trace": record.get("latest_trace"), "verification_code": record.get("demo_code") if record["stage"] == "code" else None}

    @app.post("/api/studio/conversations/{reference}/reset", dependencies=auth)
    async def restart_conversation(reference: str):
        store = get_store()
        record = store.conversation(reference)
        if not record:
            raise HTTPException(404, "Conversation not found.")
        with store.connect() as db:
            db.execute("DELETE FROM channel_sessions WHERE id=?", (record["id"],))
        await get_hub().emit(record["id"], {"type": "reset_required"})
        await get_hub().studio_changed("conversations", reference)
        return {"ok": True}
