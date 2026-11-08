"""Conversation quality, retrieval provenance and generated-response grounding."""

import asyncio
import json
import uuid

import pytest

from backend.composition import compile_reply
from backend.model import ModelUnavailable
from backend.retrieval import GuideIndex
from backend.service import Workflow
from backend.store import Store
from backend.support_plan import SupportPlan, explicit_slots
from backend.whatsapp import ChannelHub, WhatsAppChannel


class Offline:
    model = "test-qwen"
    provider = "test"
    region = "local"

    async def plan_support(self, *args):
        raise ModelUnavailable("Forced planner outage")


@pytest.fixture
def support(tmp_path):
    store = Store(tmp_path / "support.db")
    ch = WhatsAppChannel(store, Workflow(store, Offline()), ChannelHub())
    return store, ch


def send(ch, record, text, mode="baseline"):
    asyncio.run(ch.handle(record["id"], uuid.uuid4().hex, text, mode))
    return ch.store.channel(record["id"])


def account(support, order="4812"):
    _, ch = support
    record = send(ch, ch.start(), "aarav@example.com")
    return send(ch, record, order)


def return_draft(support):
    _, ch = support
    record = account(support)
    return send(ch, record, "Return the Oxford in order 4813")


@pytest.mark.parametrize(
    "question,guide",
    [
        ("What is your return policy?", "return_policy"),
        ("Why do you need my email?", "identity_reason"),
        ("How long do refunds take?", "refund_timing"),
        ("Is return pickup free?", "return_cost"),
        ("What do you mean by tags?", "garment_tags"),
        ("How do I upload a photo?", "return_photos"),
    ],
)
def test_general_help_does_not_require_identity(support, question, guide):
    store, ch = support
    record = send(ch, ch.start(), question)
    assert (
        record["stage"] == "contact" and store.session(record["id"])["customer"] is None
    )
    assert record["messages"][-1]["outcome"] == "GUIDE_ANSWER"
    assert guide in record["latest_trace"]["retrieval"]["used_chunk_ids"]
    assert "what email address" not in record["messages"][-1]["text"].lower()
    assert not store.records("tickets")


def test_greeting_and_button_do_not_call_model(support):
    _, ch = support

    class Spy(Offline):
        calls = 0

        async def plan_support(self, *args):
            self.calls += 1
            raise ModelUnavailable("No call needed")

    ch.workflow.model = Spy()
    record = send(ch, ch.start(), "Hello", "model")
    assert ch.workflow.model.calls == 0
    assert record["latest_trace"]["mode"] == "system"


def test_pending_question_survives_identity_and_order_choice(support):
    _, ch = support
    record = send(ch, ch.start(), "What is the tracking number for my order?")
    record = send(ch, record, "aarav@example.com")
    record = send(ch, record, "4812")
    assert "DEMO4812IN" in record["messages"][-1]["text"]
    assert "₹" not in record["messages"][-1]["text"]


def test_focused_followup_and_independent_fresh_source(support):
    store, ch = support
    record = account(support)
    record = send(ch, record, "Just the tracking number please")
    assert "DEMO4812IN" in record["messages"][-1]["text"]
    assert "November" not in record["messages"][-1]["text"] and not record["messages"][
        -1
    ].get("product")
    store.revise_order("4812", lambda o: {**o, "carrier_eta_date": "2026-11-12"})
    record = send(ch, record, "When will it arrive?")
    assert "12 November" in record["messages"][-1]["text"]
    assert "9 November" not in record["messages"][-1]["text"]
    store.set_setting("order_api_available", False)
    record = send(ch, record, "Can you check again?")
    assert record["messages"][-1]["outcome"] == "ORDER_SERVICE_UNAVAILABLE"
    assert "evidence" not in record["latest_trace"]


def test_compound_factual_question_answers_each_requested_detail(support):
    _, ch = support
    record = account(support)
    record = send(
        ch, record, "What did I order, how much was the total and is payment paid?"
    )
    text = record["messages"][-1]["text"]
    assert "Weekday Hoodie" in text and "₹1,999.00" in text and "Paid" in text


def test_late_delivery_offers_real_handoff_and_yes_preserves_concern(support):
    store, ch = support
    record = account(support)
    record = send(ch, record, "My parcel is late and I need it for a wedding")
    assert "wedding" in record["pending_offer"]["request"]
    assert not store.records("tickets")
    record = send(ch, record, "yes please")
    assert record["messages"][-1]["outcome"] == "HANDOFF_CREATED"
    ticket = store.records("tickets")[0]
    assert "wedding" in ticket["request"] and "yes please" in ticket["request"]
    assert store.session(record["id"])["history"][-2]["content"] == "yes please"


def test_natural_return_answers_and_compound_slots_are_not_repeated(support):
    _, ch = support
    record = return_draft(support)
    record = send(ch, record, "the shirt is too tight for me")
    assert record["return_draft"]["step"] == "condition"
    record = send(ch, record, "I only tried it on and the tags are still attached")
    assert record["return_draft"]["condition"] == "Unworn / only tried on"
    assert record["return_draft"]["tags"] == "Tags attached"
    assert record["return_draft"]["step"] == "photos"


def test_all_reported_details_in_first_return_request_prefill(support):
    _, ch = support
    record = account(support)
    record = send(
        ch, record, "Return Oxford order 4813, too tight, unworn with tags attached"
    )
    assert record["return_draft"]["step"] == "photos"
    assert record["return_draft"]["reason"] == "Size or fit"


@pytest.mark.parametrize(
    "question,guide",
    [
        ("What do you mean by tags?", "garment_tags"),
        ("Is pickup free?", "return_cost"),
        ("How long do refunds take?", "refund_timing"),
    ],
)
def test_side_question_keeps_return_answers_and_pending_step(support, question, guide):
    _, ch = support
    record = return_draft(support)
    record = send(ch, record, "Size or fit")
    before = dict(record["return_draft"])
    record = send(ch, record, question)
    assert record["return_draft"] == before
    assert guide in record["latest_trace"]["retrieval"]["used_chunk_ids"]
    assert "draft is still saved" in record["messages"][-1]["text"]


def test_question_does_not_become_reported_condition(support):
    _, ch = support
    record = return_draft(support)
    record = send(ch, record, "Size or fit")
    record = send(ch, record, "Should the tags be attached?")
    assert record["return_draft"]["step"] == "condition"
    assert "tags" not in record["return_draft"]


def test_no_washing_is_not_assumed_to_mean_unworn(support):
    _, ch = support
    record = return_draft(support)
    record = send(ch, record, "Size or fit")
    record = send(ch, record, "It hasn't been washed")
    assert record["return_draft"]["step"] == "condition"
    assert "worn for longer" in record["messages"][-1]["text"]


def test_correcting_tags_updates_same_draft_and_staff_review_flag(support):
    store, ch = support
    record = return_draft(support)
    for t in [
        "Size or fit",
        "Unworn / only tried on",
        "Tags attached",
        "Actually I removed the tag",
        "I don't have a photo",
        "14 Lake Road Bengaluru 560001",
        "afternoon please",
    ]:
        record = send(ch, record, t)
    assert (
        record["return_draft"]["step"] == "confirm"
        and record["return_draft"]["review_required"]
    )
    assert record["return_draft"]["tags"] == "Tags removed / missing"
    record = send(ch, record, "yes")
    assert not store.all_records("returns")
    record = send(ch, record, "Submit return request")
    assert len(store.all_records("returns")) == 1
    assert store.all_records("returns")[0]["tags"] == "Tags removed / missing"


def test_human_handoff_preserves_return_draft(support):
    store, ch = support
    record = return_draft(support)
    record = send(ch, record, "Size or fit")
    before = dict(record["return_draft"])
    record = send(ch, record, "I need a person to help")
    assert record["return_draft"] == before and len(store.records("tickets")) == 1
    record = send(ch, record, "It is unworn")
    assert record["return_draft"]["step"] == "tags"


def test_partial_order_understands_item_nickname(support):
    _, ch = support
    record = account(support)
    record = send(ch, record, "Return order 4816")
    record = send(ch, record, "the cardigan please")
    assert record["return_draft"]["item_id"] == "4816-1"
    assert record["return_draft"]["step"] == "reason"


def test_final_sale_damage_is_review_not_change_of_mind_denial(support):
    store, ch = support
    record = account(support)
    record = send(ch, record, "Return the damaged tee from order 4815")
    assert record.get("return_draft")
    for t in [
        "Unworn / only tried on",
        "Tags attached",
        "Continue without a photo",
        "14 Lake Road Bengaluru 560001",
        "morning please",
        "Submit return request",
    ]:
        record = send(ch, record, t)
    assert store.all_records("returns")[0]["review_required"]
    assert store.all_records("returns")[0]["reason"] == "Damaged or wrong item"


def test_ambiguous_shirt_does_not_reuse_previous_hoodie(support):
    _, ch = support
    record = account(support)
    record = send(ch, record, "I'd like to return the shirt")
    assert record["stage"] == "choose_order"
    assert set(record["choices"]) == {"4813", "4816"}


def test_general_policy_uses_current_policy_and_provenance(support):
    store, ch = support
    policy = store.setting("policy")
    policy["window_calendar_days_after_item_delivery"] = 45
    store.set_setting("policy", policy)
    record = send(ch, ch.start(), "What is your return policy?")
    assert "45 calendar days" in record["messages"][-1]["text"]
    trace = record["latest_trace"]
    assert trace["retrieval"]["version"] == "threadline-support-v1"
    assert trace["retrieval"]["used_chunk_ids"] == ["return_policy"]


def test_model_language_uses_locked_current_fact_and_only_one_call(support):
    store, ch = support
    record = account(support)

    class Writer(Offline):
        calls = 0

        async def plan_support(self, text, context, retrieved):
            self.calls += 1
            store.revise_order(
                "4812", lambda o: {**o, "carrier_eta_date": "2026-11-12"}
            )
            return SupportPlan(
                intent="order_status",
                facets=["eta"],
                reply="I checked the latest estimate for you.\n\n{{fact:eta}}",
            ), {"input_tokens": 10, "output_tokens": 20}

    writer = Writer()
    ch.workflow.model = writer
    record = send(ch, record, "When should I expect this parcel?", "model")
    assert writer.calls == 1
    assert not record["latest_trace"]["composition"]["model_written"]
    assert "Order changed" in record["latest_trace"]["composition"]["fallback_reason"]
    assert "12 November" in record["messages"][-1]["text"]


def test_unsupported_generated_claim_falls_back_without_order_write(support):
    store, ch = support
    record = account(support)
    before = store.order("4812")

    class BadWriter(Offline):
        async def plan_support(self, *args):
            return SupportPlan(
                intent="order_status",
                facets=["eta"],
                reply="It will arrive tomorrow and your refund is approved. {{fact:eta}}",
            ), {"input_tokens": 1, "output_tokens": 1}

    ch.workflow.model = BadWriter()
    record = send(ch, record, "When will it come?", "model")
    assert not record["latest_trace"]["composition"]["model_written"]
    assert "approved" not in record["messages"][-1]["text"]
    assert store.order("4812") == before


def test_valid_generated_wording_accepted_with_verified_facts(support):
    _, ch = support
    record = account(support)

    class Writer(Offline):
        async def plan_support(self, *args):
            return SupportPlan(
                intent="order_status",
                facets=["tracking"],
                reply="Here are the parcel details you asked for:\n\n{{fact:tracking}}",
            ), {"input_tokens": 10, "output_tokens": 20}

    ch.workflow.model = Writer()
    record = send(ch, record, "Just the tracking number please", "model")
    assert record["latest_trace"]["composition"]["model_written"]
    assert "DEMO4812IN" in record["messages"][-1]["text"]
    assert "parcel details you asked for" in record["messages"][-1]["text"]


def test_structured_wording_cannot_omit_requested_factual_paragraph(support):
    _, ch = support
    record = account(support)

    class Writer(Offline):
        async def plan_support(self, *args):
            return SupportPlan(
                intent="order_status",
                facets=["tracking"],
                opening="Here are the parcel details you asked for.",
                closing="I can ask the store to investigate if you need help with the delivery.",
            ), {"input_tokens": 10, "output_tokens": 20}

    ch.workflow.model = Writer()
    record = send(ch, record, "Just the tracking number please", "model")
    reply = record["messages"][-1]["text"]
    assert record["latest_trace"]["composition"]["model_written"]
    assert "DEMO4812IN" in reply and "parcel details" in reply
    assert "November" not in reply and "₹" not in reply


def test_unrequested_model_fact_is_not_added_to_focused_answer(support):
    _, ch = support
    record = account(support)

    class Writer(Offline):
        async def plan_support(self, *args):
            return SupportPlan(
                intent="order_status",
                facets=["tracking"],
                reply="Here are the details:\n\n{{fact:tracking}}\n\n{{fact:eta}}",
            ), {"input_tokens": 10, "output_tokens": 20}

    ch.workflow.model = Writer()
    record = send(ch, record, "Just the tracking number please", "model")
    assert not record["latest_trace"]["composition"]["model_written"]
    assert "DEMO4812IN" in record["messages"][-1]["text"]
    assert "November" not in record["messages"][-1]["text"]


def test_general_order_location_question_always_includes_source_status(support):
    _, ch = support
    record = account(support)

    class Writer(Offline):
        async def plan_support(self, *args):
            return SupportPlan(
                intent="order_status",
                facets=["eta", "tracking"],
                opening="Here are the latest details.",
            ), {"input_tokens": 1, "output_tokens": 1}

    ch.workflow.model = Writer()
    record = send(ch, record, "Where is my order?", "model")
    assert "is on its way" in record["messages"][-1]["text"]
    assert "9 November" in record["messages"][-1]["text"]


def test_model_cannot_choose_item_through_unmentioned_hint(support):
    _, ch = support

    class Guess(Offline):
        async def plan_support(self, *args):
            return SupportPlan(intent="order_status", item_hint="Oxford"), {
                "input_tokens": 1,
                "output_tokens": 1,
            }

    ch.workflow.model = Guess()
    record = send(ch, ch.start(), "aarav@example.com", "model")
    assert record["stage"] == "choose_order" and record["selected_order"] is None


def test_model_failure_is_labeled_and_still_helpful(support):
    _, ch = support
    record = send(ch, ch.start(), "How long do refunds take?", "model")
    assert record["latest_trace"]["mode"] == "baseline_fallback"
    assert "bank-credit timeline" in record["messages"][-1]["text"]


@pytest.mark.parametrize(
    "text",
    [
        "Your refund is approved.",
        "It will arrive in 2 days.",
        "Pickup is free.",
        "We have booked your pickup.",
        "It is in stock.",
        "Your parcel is delayed because of weather.",
        "Share your bank OTP with me.",
        "See https://made-up.test/track.",
        "{{fact:invented}}",
        "Offer to ask the store to confirm charges. Never promise free pickup.",
        "Returns are allowed within {{fact:policy_window}}.",
        "Delivery worry => I'm sorry you're having to chase this.",
        "I can't promise a date, but it will arrive soon.",
        "I'll let you know as soon as the estimated arrival changes.",
    ],
)
def test_composition_rejects_unverified_claims(text):
    reply, error = compile_reply(text, {}, guide_ids=[], available_guides=[])
    assert reply is None and error


def test_generated_policy_requires_retrieved_citation():
    reply, error = compile_reply(
        "Here is the policy.\n\n{{fact:policy_window}}",
        {"policy_window": "30 days"},
        guide_ids=["unretrieved"],
        available_guides=["return_policy"],
    )
    assert reply is None and error == "Unretrieved guidance reference"


def test_negative_guarantee_is_not_a_positive_delivery_promise():
    text = "I can't promise when the money will reach your account. I can check the return's progress for you."
    assert compile_reply(text, {}) == (text, None)


@pytest.mark.parametrize(
    "text,field,expected",
    [
        ("I wore it once", "condition", "Worn or washed"),
        ("I washed it but it is otherwise unworn", "condition", "Worn or washed"),
        ("Only tried it on", "condition", "Unworn / only tried on"),
        ("I have not removed the tags", "tags", "Tags attached"),
        ("The tag is not attached", "tags", "Tags removed / missing"),
        ("I haven't washed it", "condition", ""),
    ],
)
def test_condition_negation_and_missing_evidence(text, field, expected):
    assert getattr(explicit_slots(text, "condition"), field) == expected


def test_bm25_retrieval_and_hot_reload(tmp_path):
    source = {
        "version": "v1",
        "documents": [
            {
                "id": "tag_help",
                "title": "Tags",
                "topics": ["return_tags"],
                "questions": ["tag removed bag"],
                "answer": "Garment tags and outer packaging differ.",
            },
            {
                "id": "refund_help",
                "title": "Refund",
                "topics": ["refund_timing"],
                "questions": ["refund bank timeline"],
                "answer": "Bank timing is unknown.",
            },
        ],
    }
    path = tmp_path / "guides.json"
    path.write_text(json.dumps(source))
    index = GuideIndex(path)
    assert index.search("is my garment tag removed", limit=1)[0]["id"] == "tag_help"
    assert [
        d["id"] for d in index.search("refund bank timeline", topics=["return_tags"])
    ] == ["tag_help"]
    old = index.digest
    source["version"] = "v2"
    source["documents"][1]["answer"] = "Ask staff for confirmed refund timing."
    path.write_text(json.dumps(source))
    result = index.search("refund bank timeline", limit=1)
    assert result[0]["version"] == "v2" and index.digest != old


def test_account_switch_does_not_pass_old_account_context_to_model(support):
    _, ch = support
    record = account(support)

    class Spy(Offline):
        def __init__(self):
            self.seen = []

        async def plan_support(self, text, context, retrieved):
            self.seen.append(context)
            return SupportPlan(intent="order_status", facets=["summary"]), {
                "input_tokens": 1,
                "output_tokens": 1,
            }

    spy = Spy()
    ch.workflow.model = spy
    record = send(ch, record, "ananya@example.com", "model")
    assert spy.seen
    assert not spy.seen[-1]["recent_messages"]
    assert "Aarav" not in json.dumps(spy.seen[-1])
