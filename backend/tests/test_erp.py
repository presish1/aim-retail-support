import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from backend.model import ModelUnavailable
from backend.service import Workflow
from backend.store import Store
from backend.whatsapp import ChannelHub, WhatsAppChannel


class OfflineModel:
    model = "test-qwen"
    provider = "test"
    region = "test"
    async def propose(self, *args):
        raise ModelUnavailable("Not connected in unit tests")


@pytest.fixture
def erp_system(tmp_path, monkeypatch):
    import backend.app as module
    store = Store(tmp_path / "erp.db")
    workflow = Workflow(store, OfflineModel())
    hub = ChannelHub()
    monkeypatch.setattr(module, "store", store)
    monkeypatch.setattr(module, "workflow", workflow)
    monkeypatch.setattr(module, "channel_hub", hub)
    with TestClient(module.app) as client:
        key = client.get("/api/studio/bootstrap").json()["admin_key"]
        yield client, {"X-Demo-Admin": key}, store, workflow, hub


def create_customer(client, headers, **overrides):
    body = {"first_name": "Robin", "last_name": "Taylor", "email": "robin@example.com", "phone": "+1 202 555 0133", "city": "Austin, TX", **overrides}
    return client.post("/api/studio/customers", headers=headers, json=body)


def send(channel, record, text):
    asyncio.run(channel.handle(record["id"], uuid.uuid4().hex, text, "baseline"))
    return channel.store.channel(record["id"])


def test_default_lookup_is_clear_and_does_not_request_unavailable_code(erp_system):
    _, _, store, workflow, hub = erp_system
    channel = WhatsAppChannel(store, workflow, hub)
    record = send(channel, channel.start(), "Where is my order?")
    record = send(channel, record, "unknown@example.com")
    assert record["stage"] == "contact" and record["code_hash"] is None
    assert "couldn't find a customer account" in record["messages"][-1]["text"]
    assert "code" not in record["messages"][-1]["text"]
    record = send(channel, record, "aarav@example.com")
    assert record["stage"] == "choose_order"
    assert store.session(record["id"])["customer"] == "demo-customer-a"
    assert record["verification_method"] == "demo_contact_match"


@pytest.mark.parametrize("identifier", ["CUS-1001", "cus1001", "+91 90000 00101", "aarav@example.com"])
def test_customer_keys_match_same_record(erp_system, identifier):
    _, _, store, _, _ = erp_system
    assert store.find_customer(identifier)["customer_id"] == "demo-customer-a"


def test_new_customer_and_order_are_immediately_found_in_chat(erp_system):
    client, headers, store, workflow, hub = erp_system
    customer_response = create_customer(client, headers)
    assert customer_response.status_code == 200
    customer = customer_response.json()
    assert customer["customer_id"] == "CUS-1009"
    response = client.post("/api/studio/orders", headers=headers, json={"customer_id": customer["customer_id"], "shipping_city": "Austin, TX", "items": [{"sku": "TL-HOOD-01", "quantity": 2, "size": "L"}]})
    assert response.status_code == 200
    order = response.json()
    assert order["order_total"] == 3998 and order["status"] == "processing"
    channel = WhatsAppChannel(store, workflow, hub)
    record = send(channel, channel.start(), "Where is my order?")
    record = send(channel, record, "robin@example.com")
    assert record["selected_order"] == order["order_id"]
    assert record["latest_trace"]["evidence"]["order_total"] == 3998
    assert record["messages"][-1]["product"]["quantity"] == 2
    assert record["messages"][-1]["product"]["name"] == "Weekday Hoodie"
    assert Store(store.path).order(order["order_id"])["items"][0]["quantity"] == 2


def test_unknown_customer_cannot_have_order_created(erp_system):
    client, headers, _, _, _ = erp_system
    response = client.post("/api/studio/orders", headers=headers, json={"customer_id": "missing", "shipping_city": "Austin", "items": [{"sku": "TL-HOOD-01"}]})
    assert response.status_code == 404


def test_duplicate_contacts_and_invalid_details_are_rejected(erp_system):
    client, headers, _, _, _ = erp_system
    assert create_customer(client, headers).status_code == 200
    assert create_customer(client, headers).status_code == 409
    assert create_customer(client, headers, email="bademail", phone="1234567890").status_code == 422
    assert create_customer(client, headers, email="different@example.com", phone="1234567").status_code == 422


def test_edit_customer_updates_lookup_without_new_record(erp_system):
    client, headers, store, _, _ = erp_system
    customer = create_customer(client, headers).json()
    response = client.patch("/api/studio/customers/" + customer["customer_id"], headers=headers, json={"first_name": "Robin", "last_name": "Taylor", "email": "newrobin@example.com", "phone": "+12025550134", "city": "Boston, MA"})
    assert response.status_code == 200
    assert store.find_customer("robin@example.com") is None
    assert store.find_customer("newrobin@example.com")["customer_id"] == customer["customer_id"]


def test_order_revision_conflict_prevents_lost_updates(erp_system):
    client, headers, store, _, _ = erp_system
    initial = store.order("4812")
    r = client.patch("/api/studio/orders/4812", headers=headers, json={"status": "delivered", "revision": initial["revision"]})
    assert r.status_code == 200 and r.json()["order"]["revision"] == initial["revision"] + 1
    stale = client.patch("/api/studio/orders/4812", headers=headers, json={"status": "processing", "revision": initial["revision"]})
    assert stale.status_code == 409
    assert store.order("4812")["status"] == "delivered"
    assert len([a for a in store.all_records("activity") if a["entity"] == "order"]) == 1


def test_invalid_order_patch_cannot_corrupt_saved_fields(erp_system):
    client, headers, store, _, _ = erp_system
    before = store.order("4812")
    assert client.patch("/api/studio/orders/4812", headers=headers, json={"status": None}).status_code == 422
    assert client.patch("/api/studio/orders/4812", headers=headers, json={"carrier_eta_date": "not-a-date"}).status_code == 422
    assert store.order("4812") == before


def test_internal_order_notes_stay_in_operations_payload(erp_system):
    client, headers, store, workflow, hub = erp_system
    client.patch("/api/studio/orders/4812", headers=headers, json={"notes": "Internal operations note only"})
    channel = WhatsAppChannel(store, workflow, hub)
    record = send(channel, channel.start(), "aarav@example.com")
    record = send(channel, record, "4812")
    public = channel.snapshot(record)
    import json
    assert "latest_trace" not in public
    assert "Internal operations" not in json.dumps(public)
    assert "notes" not in store.channel(record["id"])["latest_trace"]["evidence"]
    assert store.order("4812")["notes"] == "Internal operations note only"


def test_live_notification_and_next_reply_match_saved_order(erp_system):
    client, headers, store, workflow, hub = erp_system
    channel = WhatsAppChannel(store, workflow, hub)
    record = send(channel, channel.start(), "Where is my order?")
    record = send(channel, record, "aarav@example.com")
    record = send(channel, record, "4812")

    class Socket:
        def __init__(self): self.events = []
        async def send_json(self, event): self.events.append(event)
    socket = Socket()
    hub.add(record["id"], socket)
    response = client.patch("/api/studio/orders/4812", headers=headers, json={"status": "delivered", "tracking_reference": "DEMO-UPDATED", "revision": 1})
    assert response.status_code == 200
    update = next(e for e in socket.events if e["type"] == "message")
    assert "is delivered" in update["message"]["text"]
    assert "DEMO-UPDATED" in update["message"]["text"]
    assert store.channel(record["id"])["latest_trace"]["evidence"]["revision"] == 2
    assert "latest_trace" not in update
    record = send(channel, record, "Can you check again?")
    assert "recorded as delivered" in record["messages"][-1]["text"]
    assert record["latest_trace"]["evidence"]["status"] == "delivered"


def test_automatic_update_does_not_disclose_to_other_customer(erp_system):
    client, headers, store, workflow, hub = erp_system
    channel = WhatsAppChannel(store, workflow, hub)
    record = send(channel, channel.start(), "ananya@example.com")
    class Socket:
        def __init__(self): self.events = []
        async def send_json(self, event): self.events.append(event)
    socket = Socket()
    hub.add(record["id"], socket)
    client.patch("/api/studio/orders/4812", headers=headers, json={"status": "delivered"})
    assert not socket.events


def test_full_return_lifecycle_updates_chat_and_order(erp_system):
    client, headers, store, workflow, hub = erp_system
    response = client.post("/api/studio/returns", headers=headers, json={"order_id": "4813", "item_id": "4813-1", "reason": "Wrong size"})
    assert response.status_code == 200
    record = response.json()
    assert record["refund_amount"] == 1799
    premature = client.patch("/api/studio/returns/" + record["id"], headers=headers, json={"status": "refunded"})
    assert premature.status_code == 409
    for status in ("approved", "pickup_scheduled", "received", "refunded"):
        assert client.patch("/api/studio/returns/" + record["id"], headers=headers, json={"status": status, "notes": "Internal-only inspection note", "pickup_date": "2026-11-09", "pickup_reference": "DEMO-PU-001", "inspection": "passed", "refund_reference": "DEMO-REF-001"}).status_code == 200
    assert store.order("4813")["items"][0]["returned"] is True
    assert store.order("4813")["payment_status"] == "refunded"
    channel = WhatsAppChannel(store, workflow, hub)
    chat = send(channel, channel.start(), "Can I return the Oxford?")
    chat = send(channel, chat, "aarav@example.com")
    assert "refund recorded" in chat["messages"][-1]["text"]
    assert "Internal-only" not in chat["messages"][-1]["text"]
    chat = send(channel, chat, "What is the refund status?")
    assert "refund recorded" in chat["messages"][-1]["text"]
    assert not store.records("tickets")


def test_return_must_reference_delivered_owned_item(erp_system):
    client, headers, _, _, _ = erp_system
    for body in [{"order_id": "4812", "item_id": "4812-1", "reason": "Too big"}, {"order_id": "4813", "item_id": "4901-1", "reason": "Wrong size"}]:
        assert client.post("/api/studio/returns", headers=headers, json=body).status_code == 422


def test_return_duplicate_quantity_and_authentication_checks(erp_system):
    client, headers, _, _, _ = erp_system
    body = {"order_id": "4813", "item_id": "4813-1", "reason": "Wrong size"}
    assert client.post("/api/studio/returns", json=body).status_code == 403
    assert client.post("/api/studio/returns", headers=headers, json={**body, "quantity": 2}).status_code == 422
    assert client.post("/api/studio/returns", headers=headers, json=body).status_code == 200
    assert client.post("/api/studio/returns", headers=headers, json=body).status_code == 409


def test_support_assignment_and_resolution_allow_new_request(erp_system):
    client, headers, store, workflow, hub = erp_system
    channel = WhatsAppChannel(store, workflow, hub)
    record = send(channel, channel.start(), "aarav@example.com")
    record = send(channel, record, "Please contact support about order 4814")
    ticket = store.records("tickets")[0]
    response = client.patch("/api/studio/tickets/" + ticket["id"], headers=headers, json={"status": "resolved", "assignee": "Store manager", "internal_note": "Customer contacted"})
    assert response.status_code == 200 and response.json()["assignee"] == "Store manager"
    send(channel, record, "Contact support about order 4814 again")
    assert len(store.records("tickets")) == 2


def test_live_studio_socket_requires_capability(erp_system):
    client, headers, _, _, _ = erp_system
    with client.websocket_connect("/api/studio/ws", headers={"origin": "http://127.0.0.1:5173"}) as socket:
        socket.send_json({"key": "wrong"})
        with pytest.raises(WebSocketDisconnect): socket.receive_json()
    with client.websocket_connect("/api/studio/ws", headers={"origin": "http://127.0.0.1:5173"}) as socket:
        socket.send_json({"key": headers["X-Demo-Admin"]})
        assert socket.receive_json()["type"] == "ready"
        create_customer(client, headers)
        assert socket.receive_json()["entity"] == "customers"


def test_customer_contact_does_not_leak_to_model_on_account_switch(erp_system):
    _, _, store, workflow, hub = erp_system
    channel = WhatsAppChannel(store, workflow, hub)
    record = send(channel, channel.start(), "aarav@example.com")
    record = send(channel, record, "ananya@example.com")
    assert store.session(record["id"])["customer"] == "demo-customer-b"
    assert record["selected_order"] == "4901"
    assert all("ananya@example.com" not in m["content"] for m in store.session(record["id"])["history"])


@pytest.mark.parametrize(
    "estimate,phrase",
    [("2026-11-12", "12 November"), (None, "don't have a delivery date")],
)
def test_quick_delivery_estimate_save_and_clear_notify_with_current_revision(
    erp_system, estimate, phrase
):
    client, headers, store, workflow, hub = erp_system
    channel = WhatsAppChannel(store, workflow, hub)
    record = send(channel, channel.start(), "aarav@example.com")
    record = send(channel, record, "4812")

    class Socket:
        def __init__(self):
            self.events = []

        async def send_json(self, event):
            self.events.append(event)

    socket = Socket()
    hub.add(record["id"], socket)
    response = client.patch(
        "/api/studio/orders/4812",
        headers=headers,
        json={"carrier_eta_date": estimate, "revision": 1},
    )
    assert response.status_code == 200 and response.json()["order"]["revision"] == 2
    update = next(e["message"] for e in socket.events if e["type"] == "message")
    assert "Delivery estimate updated" in update["text"] and phrase in update["text"]
    assert "₹" not in update["text"] and "9 November" not in update["text"]
    stale = client.patch(
        "/api/studio/orders/4812",
        headers=headers,
        json={"carrier_eta_date": "2026-11-15", "revision": 1},
    )
    assert (
        stale.status_code == 409 and store.order("4812")["carrier_eta_date"] == estimate
    )
    record = send(channel, record, "When will it arrive?")
    assert phrase in record["messages"][-1]["text"]
    assert record["latest_trace"]["evidence"]["revision"] == 2
