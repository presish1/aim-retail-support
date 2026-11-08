import asyncio
import json
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
    region = "local-test"

    async def propose(self, *args):
        raise ModelUnavailable("Forced offline model for deterministic transport tests.")


@pytest.fixture
def channel_system(tmp_path):
    store = Store(tmp_path / "whatsapp.db")
    store.set_setting("verification_mode", "code")
    workflow = Workflow(store, OfflineModel())
    hub = ChannelHub()
    return store, workflow, hub, WhatsAppChannel(store, workflow, hub)


def send(channel_system, record, text, client_id=None):
    _, _, _, channel = channel_system
    asyncio.run(channel.handle(record["id"], client_id or uuid.uuid4().hex, text, "baseline"))
    return channel.store.channel(record["id"])


def verify(channel_system, contact="aarav@example.com", query="Where is my order?"):
    store, _, _, channel = channel_system
    record = channel.start()
    record = send(channel_system, record, query)
    record = send(channel_system, record, contact)
    assert record["stage"] == "code"
    return send(channel_system, record, store.channel(record["id"])["demo_code"])


def test_contact_match_is_not_verification(channel_system):
    store, _, _, channel = channel_system
    record = channel.start()
    record = send(channel_system, record, "Where is my order?")
    assert "email address or mobile number" in record["messages"][-1]["text"]
    record = send(channel_system, record, "AARAV@EXAMPLE.COM")
    assert store.session(record["id"])["customer"] is None
    assert record["stage"] == "code"
    public = channel.snapshot(record)
    assert "candidate_customer" not in public and "demo_code" not in public and public["customer_name"] is None
    assert "4812" not in json.dumps(public)


@pytest.mark.parametrize("identifier", ["aarav@example.com", "+91 90000 00101", "90000.00101"])
def test_email_and_phone_resolve_same_account(channel_system, identifier):
    store = channel_system[0]
    assert store.find_customer(identifier)["customer_id"] == "demo-customer-a"
    assert channel_system[3].identifier("My contact is " + identifier) is not None


def test_verification_finds_owned_active_orders_without_number(channel_system):
    store = channel_system[0]
    record = verify(channel_system)
    assert record["stage"] == "choose_order"
    assert record["choices"] == ["4812", "4816"]
    assert store.session(record["id"])["customer"] == "demo-customer-a"
    assert "4901" not in record["messages"][-1]["text"]
    record = send(channel_system, record, "1")
    assert record["selected_order"] == "4812"
    assert record["messages"][-1]["product"]["amount"] == 1999
    assert record["messages"][-1]["product"]["name"] == "Weekday Hoodie"
    assert record["latest_trace"]["evidence"]["order_id"] == "4812"


def test_single_customer_order_is_found_automatically(channel_system):
    store = channel_system[0]
    record = verify(channel_system, "+91 90000 00102")
    assert record["stage"] == "verified" and record["selected_order"] == "4901"
    assert store.session(record["id"])["customer"] == "demo-customer-b"
    assert record["messages"][-1]["product"]["name"] == "Utility Jacket"


def test_code_and_contact_are_not_forwarded_to_model_history(channel_system):
    store, _, _, channel = channel_system
    record = channel.start()
    record = send(channel_system, record, "Can I return the Oxford?")
    record = send(channel_system, record, "aarav@example.com")
    code = record["demo_code"]
    record = send(channel_system, record, code)
    history = json.dumps(store.session(record["id"])["history"])
    assert code not in history and "aarav@example.com" not in history
    assert record["selected_order"] == "4813"


def test_combined_question_and_contact_preserves_intent(channel_system):
    store, _, _, channel = channel_system
    record = send(channel_system, channel.start(), "Can I return the Oxford? My email is aarav@example.com")
    assert "return the Oxford" in record["pending_request"]
    assert "aarav@example.com" not in record["pending_request"]
    record = send(channel_system, record, record["demo_code"])
    assert record["selected_order"] == "4813"
    assert "Request by 24 November" in record["messages"][-1]["text"]
    assert record["return_draft"]["step"] == "reason"


def test_sixth_code_attempt_requires_new_challenge(channel_system):
    store, _, _, channel = channel_system
    record = send(channel_system, channel.start(), "aarav@example.com")
    wrong = "000000" if record["demo_code"] != "000000" else "111111"
    for _ in range(6): record = send(channel_system, record, wrong)
    assert record["stage"] == "contact"
    assert store.session(record["id"])["customer"] is None


def test_wrong_code_cannot_bind_identity(channel_system):
    store, _, _, channel = channel_system
    record = send(channel_system, channel.start(), "aarav@example.com")
    wrong = "000000" if record["demo_code"] != "000000" else "111111"
    record = send(channel_system, record, wrong)
    assert record["stage"] == "code" and store.session(record["id"])["customer"] is None
    assert "couldn't verify" in record["messages"][-1]["text"]


def test_expired_challenge_cannot_bind_identity(channel_system):
    store, _, _, channel = channel_system
    record = send(channel_system, channel.start(), "aarav@example.com")
    code = record["demo_code"]
    record["expires_at"] = 0
    store.save_channel(record)
    record = send(channel_system, record, code)
    assert record["stage"] == "contact" and store.session(record["id"])["customer"] is None


def test_unknown_contact_returns_not_found_without_challenge(channel_system):
    _, _, _, channel = channel_system
    known = send(channel_system, channel.start(), "aarav@example.com")
    unknown = send(channel_system, channel.start(), "nobody@example.com")
    assert known["stage"] == "code"
    assert "couldn't find a customer account" in unknown["messages"][-1]["text"]
    assert unknown["stage"] == "contact"
    assert unknown["demo_code"] is None and unknown["candidate_customer"] is None
    failed = send(channel_system, unknown, "123456")
    assert failed["stage"] == "contact"


def test_cross_customer_order_is_still_denied_after_verification(channel_system):
    record = verify(channel_system)
    record = send(channel_system, record, "4901")
    assert "couldn't find an accessible order" in record["messages"][-1]["text"]
    assert record["selected_order"] is None


def test_replayed_message_id_does_not_repeat_inference_or_ticket(channel_system):
    store = channel_system[0]
    record = verify(channel_system)
    record = send(channel_system, record, "4812")
    request_id = uuid.uuid4().hex
    record = send(channel_system, record, "Contact support about this delivery", request_id)
    count = len(record["messages"])
    trace_count = len(store.records("traces"))
    again = send(channel_system, record, "Contact support about this delivery", request_id)
    assert len(again["messages"]) == count and len(store.records("traces")) == trace_count
    assert len(store.records("tickets")) == 1


def test_resume_restores_conversation_and_identity(channel_system):
    _, _, _, channel = channel_system
    record = verify(channel_system)
    resumed = channel.start(record["id"])
    assert channel.snapshot(resumed) == channel.snapshot(record)


def test_updates_only_broadcast_to_verified_owner(channel_system):
    store, _, hub, channel = channel_system
    a = verify(channel_system)
    b = verify(channel_system, "ananya@example.com")
    guest = channel.start()

    class Socket:
        def __init__(self): self.events = []
        async def send_json(self, event): self.events.append(event)

    sockets = [Socket() for _ in range(3)]
    for record, socket in zip([a, b, guest], sockets): hub.add(record["id"], socket)
    asyncio.run(hub.source_changed(store, "4812"))
    assert sockets[0].events[0]["order_id"] == "4812"
    assert not sockets[1].events and not sockets[2].events


def test_websocket_protocol_and_demo_inbox_permissions(channel_system, monkeypatch):
    import backend.app as api
    store, workflow, hub, _ = channel_system
    monkeypatch.setattr(api, "store", store)
    monkeypatch.setattr(api, "workflow", workflow)
    monkeypatch.setattr(api, "channel_hub", hub)
    with TestClient(api.app) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/api/whatsapp/ws", headers={"origin": "https://unrelated.example"}):
                pass
        with client.websocket_connect("/api/whatsapp/ws", headers={"origin": "http://127.0.0.1:5173"}) as ws:
            ws.send_json({"type": "resume", "session_id": None})
            initial = ws.receive_json()
            assert initial["type"] == "session"
            token = initial["session_id"]
            ws.send_json({"type": "message", "id": uuid.uuid4().hex, "text": "aarav@example.com", "mode": "baseline"})
            events = []
            while True:
                event = ws.receive_json()
                events.append(event)
                if event["type"] == "typing" and event["active"] is False: break
            assert any(e["type"] == "ack" for e in events)
            assert next(e for e in events if e["type"] == "message")["stage"] == "code"
            assert client.get("/api/studio/whatsapp", headers={"X-Demo-Session": token}).status_code == 403
            key = client.get("/api/studio/bootstrap").json()["admin_key"]
            inbox = client.get("/api/studio/whatsapp", headers={"X-Demo-Session": token, "X-Demo-Admin": key}).json()
            assert len(inbox["code"]) == 6
            ws.send_json({"type": "message", "id": "invalid1234", "text": "x" * 2001})
            assert ws.receive_json()["type"] == "error"
