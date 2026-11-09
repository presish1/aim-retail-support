"""Guarded customer order amendments: real persistence, no inventory/price inventions."""

import asyncio
import copy
import sqlite3
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

from backend.order_changes import requested_size
from backend.service import Workflow
from backend.store import Store
from backend.whatsapp import ChannelHub, WhatsAppChannel


class Offline:
    model = "test"
    provider = "test"
    region = "local"


def send(channel, record, text):
    asyncio.run(channel.handle(record["id"], uuid.uuid4().hex, text, "baseline"))
    return channel.store.channel(record["id"])


@pytest.fixture
def changes(tmp_path):
    store = Store(tmp_path / "changes.db")
    order = copy.deepcopy(store.order("4812"))
    order.update(
        order_id="5555",
        status="processing",
        carrier_eta_date=None,
        tracking_reference="",
        revision=1,
    )
    order["items"][0].update(
        item_id="5555-1", size="S", status="processing", delivered_at=None
    )
    store.insert_order(order)
    channel = WhatsAppChannel(store, Workflow(store, Offline()), ChannelHub())
    record = send(channel, channel.start(), "aarav@example.com")
    return store, channel, record


def preview(changes, text="I ordered S but need M for order 5555"):
    store, ch, r = changes
    return send(ch, r, text)


def test_size_change_requires_confirmation_and_updates_same_order_and_audit(changes):
    store, ch, _ = changes
    before = store.order("5555")
    record = preview(changes)
    assert record["messages"][-1]["outcome"] == "SIZE_CHANGE_PREVIEW"
    assert store.order("5555") == before
    record = send(ch, record, "Yes please")
    after = store.order("5555")
    assert (
        record["messages"][-1]["outcome"] == "SIZE_CHANGED"
        and "now size *M*" in record["messages"][-1]["text"]
    )
    assert after["items"][0]["size"] == "M" and after["revision"] == 2
    assert all(
        after[k] == before[k]
        for k in [
            "order_total",
            "payment_status",
            "currency",
            "status",
            "shipping_city",
            "carrier_eta_date",
        ]
    )
    assert after["items"][0]["quantity"] == before["items"][0]["quantity"]
    assert after["items"][0]["unit_price"] == before["items"][0]["unit_price"]
    assert (
        len([a for a in store.all_records("activity") if a["action"] == "size_changed"])
        == 1
    )
    record = send(ch, record, "Confirm size change")
    assert (
        record["messages"][-1]["outcome"] == "NO_SIZE_CHANGE"
        and store.order("5555")["revision"] == 2
    )


def test_order_revision_change_requires_new_preview_and_new_consent(changes):
    store, ch, _ = changes
    record = preview(changes)
    store.revise_order("5555", lambda o: {**o, "notes": "Operator changed this"})
    record = send(ch, record, "Confirm size change")
    assert record["messages"][-1]["outcome"] == "SIZE_CHANGE_PREVIEW"
    assert store.order("5555")["items"][0]["size"] == "S"
    assert record["size_change"]["revision"] == 2
    record = send(ch, record, "Confirm size change")
    assert (
        store.order("5555")["revision"] == 3
        and store.order("5555")["items"][0]["size"] == "M"
    )


def test_fulfilment_race_does_not_change_shipped_item(changes):
    store, ch, _ = changes
    record = preview(changes)

    def ship(o):
        o["status"] = "in_transit"
        o["items"][0]["status"] = "in_transit"
        return o

    store.revise_order("5555", ship)
    record = send(ch, record, "Confirm size change")
    assert record["messages"][-1]["outcome"] == "SIZE_CHANGE_REVIEW"
    assert store.order("5555")["items"][0]["size"] == "S"


def test_disabled_size_is_rechecked_inside_confirmation(changes):
    store, ch, _ = changes
    record = preview(changes)
    with store.connect() as db:
        db.execute(
            "UPDATE product_sizes SET enabled=0 WHERE sku='TL-HOOD-01' AND size='M'"
        )
    record = send(ch, record, "Confirm size change")
    assert store.order("5555")["items"][0]["size"] == "S"
    assert record["size_change"]["step"] == "size"
    assert "M" not in [a["text"] for a in record["messages"][-1]["actions"]]


def test_other_customers_order_is_denied_in_read_and_write(changes):
    store, ch, record = changes
    before = store.order("4901")
    record = send(ch, record, "Change size to M for order 4901")
    assert record["messages"][-1]["outcome"] == "INACCESSIBLE_ORDER"
    assert "Utility Jacket" not in record["messages"][-1]["text"]
    with pytest.raises(KeyError):
        store.amend_order_size("demo-customer-a", "4901", "4901-1", "M", 1)
    assert store.order("4901") == before


def test_size_write_and_audit_roll_back_together(changes):
    store, _, _ = changes
    before = store.order("5555")
    with store.connect() as db:
        db.execute(
            "CREATE TRIGGER block_amend_audit BEFORE INSERT ON activity BEGIN SELECT RAISE(ABORT,'audit unavailable'); END"
        )
    with pytest.raises(sqlite3.IntegrityError):
        store.amend_order_size("demo-customer-a", "5555", "5555-1", "M", 1)
    assert store.order("5555") == before


def test_concurrent_confirms_apply_only_once(changes):
    store, _, _ = changes

    def apply(_):
        try:
            store.amend_order_size("demo-customer-a", "5555", "5555-1", "M", 1)
            return "saved"
        except ValueError:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(apply, range(2)))
    assert sorted(results) == ["conflict", "saved"]
    assert store.order("5555")["revision"] == 2
    assert (
        len([a for a in store.all_records("activity") if a["action"] == "size_changed"])
        == 1
    )


def test_source_outage_blocks_change_and_expiry_requires_new_preview(changes):
    store, ch, _ = changes
    record = preview(changes)
    store.set_setting("order_api_available", False)
    record = send(ch, record, "Confirm size change")
    assert record["messages"][-1]["outcome"] == "ORDER_SERVICE_UNAVAILABLE"
    assert store.order("5555")["items"][0]["size"] == "S"
    store.set_setting("order_api_available", True)
    record["size_change"]["expires_at"] = 0
    store.save_channel(record)
    record = send(ch, record, "Confirm size change")
    assert (
        record["messages"][-1]["outcome"] == "SIZE_CHANGE_PREVIEW"
        and store.order("5555")["revision"] == 1
    )


def test_cancel_keeps_order_and_account_switch_discards_preview(changes):
    store, ch, _ = changes
    record = preview(changes)
    record = send(ch, record, "Cancel size change")
    assert not record.get("size_change") and store.order("5555")["revision"] == 1
    record = send(ch, record, "Change size to M for order 5555")
    record = send(ch, record, "ananya@example.com")
    assert (
        not record.get("size_change") and store.order("5555")["items"][0]["size"] == "S"
    )


@pytest.mark.parametrize(
    "text,target",
    [
        ("I ordered S but actually need M", "M"),
        ("Can I change the size from small to medium?", "M"),
        ("Change it to large please", "L"),
        ("L, please", "L"),
        ("I need size 34", "34"),
        ("I ordered S", None),
        ("I don't want M", None),
    ],
)
def test_destination_size_is_customer_supplied(text, target):
    assert requested_size(text) == target


def test_exchange_review_yes_does_not_answer_an_unrelated_return_question(changes):
    store, ch, record = changes
    record = send(ch, record, "Return order 4813")
    assert record["return_draft"]["step"] == "reason"
    record = send(ch, record, "Change my hoodie to M for order 4812")
    assert record["messages"][-1]["outcome"] == "SIZE_CHANGE_REVIEW"
    record = send(ch, record, "Yes please")
    assert record["messages"][-1]["outcome"] == "HANDOFF_CREATED"
    assert record["return_draft"]["step"] == "reason"
    assert len(store.records("tickets")) == 1


def test_bare_yes_after_a_different_question_does_not_apply_a_size_change(changes):
    store, ch, _ = changes
    record = preview(changes)
    record = send(ch, record, "How long do refunds take?")
    record = send(ch, record, "Yes please")
    assert store.order("5555")["items"][0]["size"] == "S"
    assert not [
        a for a in store.all_records("activity") if a["action"] == "size_changed"
    ]


def test_multi_item_choice_updates_only_the_selected_owned_item(changes):
    store, ch, record = changes

    def two_items(order):
        second = copy.deepcopy(order["items"][0])
        second.update(item_id="5555-2", name="Second Hoodie", size="L")
        order["items"].append(second)
        order["order_total"] *= 2
        return order

    store.revise_order("5555", two_items)
    record = send(ch, record, "Change the size to M for order 5555")
    assert record["messages"][-1]["outcome"] == "SIZE_CHANGE_ITEM"
    record = send(ch, record, "Change item 5555-2")
    assert record["messages"][-1]["outcome"] == "SIZE_CHANGE_PREVIEW"
    record = send(ch, record, "Confirm size change")
    assert [i["size"] for i in store.order("5555")["items"]] == ["S", "M"]


def test_size_followup_keeps_selected_purchase_when_customer_owns_two_hoodies(changes):
    store, ch, _ = changes
    record = preview(changes)
    record = send(ch, record, "Confirm size change")
    record = send(ch, record, "What size is my hoodie now?")
    assert record["selected_order"] == "5555" and record["stage"] == "verified"
    assert "M /" in record["messages"][-1]["text"]
    assert record["latest_trace"]["evidence"]["revision"] == 2
    record = send(ch, record, "What size is my other hoodie?")
    assert record["messages"][-1]["outcome"] == "CHOOSE_ORDER"


def test_new_order_reference_cannot_edit_the_previously_previewed_order(changes):
    store, ch, _ = changes
    record = preview(changes)
    record = send(ch, record, "Change size to L for order 4901")
    assert record["messages"][-1]["outcome"] == "INACCESSIBLE_ORDER"
    assert not record.get("size_change")
    assert store.order("5555")["items"][0]["size"] == "S"
    record = send(ch, record, "Confirm size change")
    assert record["messages"][-1]["outcome"] == "NO_SIZE_CHANGE"
    assert store.order("5555")["revision"] == 1
