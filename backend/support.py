"""Contextual customer support with retrieved guides and source-rendered facts.

The model plans and phrases the response, and selects relevant guides.
It never supplies transactional values or authorizes writes. One model call at most per turn.
"""

import re
import time
import uuid
from zoneinfo import ZoneInfo

from .model import ModelUnavailable
from .reads import SourceError, read_audit
from .retrieval import guides
from .service import iso_now, date_label, parse_time
from .support_plan import SupportPlan, ReportedSlots, explicit_slots, fallback_plan
from .composition import compile_reply
from .hybrid import HybridRetriever

TOPICS = {
    "identity": ["identity"],
    "order_status": ["order_status"],
    "delivery_delay": ["delivery_delay"],
    "delivery_dispute": ["delivery_dispute"],
    "return_start": ["return_policy"],
    "return_status": ["return_status"],
    "refund_status": ["refund_status"],
    "exchange": ["exchange"],
    "cancel": ["cancel"],
    "address_change": ["address_change"],
    "human": ["human"],
    "catalog": ["catalog"],
    "greeting": ["greeting"],
}
FACET_TOPICS = {
    "eta": "eta",
    "tracking": "tracking",
    "payment": "payment",
    "items": "split_delivery",
    "return_policy": "return_policy",
    "return_process": "return_process",
    "return_condition": "return_condition",
    "return_tags": "return_tags",
    "return_photos": "return_photos",
    "refund_timing": "refund_timing",
    "return_cost": "return_cost",
    "pickup": "pickup",
    "stock": "stock",
    "size_guide": "size_guide",
}
GUIDE_FOR = {
    "identity": "identity_reason",
    "delivery_delay": "late_delivery",
    "delivery_dispute": "delivery_dispute",
    "exchange": "exchange_size",
    "cancel": "cancel_order",
    "address_change": "change_address",
    "human": "support_team",
    "catalog": "catalog_limits",
}
GUIDE_FACET = {
    "return_policy": "return_policy",
    "return_process": "return_steps",
    "return_condition": "try_on",
    "return_tags": "garment_tags",
    "return_photos": "return_photos",
    "refund_timing": "refund_timing",
    "return_cost": "return_cost",
    "pickup": "pickup_preference",
    "size_guide": "exchange_size",
    "stock": "catalog_limits",
}
PURCHASE = {
    "order_status",
    "delivery_delay",
    "delivery_dispute",
    "return_start",
    "return_status",
    "refund_status",
    "exchange",
    "cancel",
    "address_change",
}


def action(label, text):
    return {"label": label, "text": text}


def product(item, order=None):
    return {
        "image": item.get("image"),
        "name": item["name"],
        "variant": " · ".join(filter(None, [item.get("size"), item.get("color")])),
        "amount": item["unit_price"],
        "quantity": item["quantity"],
        **(
            {
                "order_id": order["order_id"],
                "status": order["status"].replace("_", " ").capitalize(),
            }
            if order
            else {}
        ),
    }


def match_items(items, text):
    words = set(re.findall(r"[a-z]+", text.lower()))
    if re.search(r"\bt[ -]?shirt\b", text, re.I):
        words.discard("shirt")
        words.add("tee")
    aliases = {
        "Weekday Hoodie": {"hoodie", "sweatshirt"},
        "Everyday Oxford": {"oxford", "shirt"},
        "Straight-leg Chino": {"chino", "chinos", "trousers", "pants"},
        "Archive Tee": {"tee", "tshirt"},
        "Ribbed Cardigan": {"cardigan", "sweater", "knitwear"},
        "Canvas Overshirt": {"overshirt", "shirt"},
        "Utility Jacket": {"jacket"},
    }
    matched = [
        i
        for i in items
        if i["item_id"] in text
        or words
        & (
            aliases.get(i["name"], set())
            | {w for w in i["name"].lower().split() if len(w) > 4}
        )
    ]
    color_matches = [
        i for i in matched if set(i.get("color", "").lower().split()) & words
    ]
    return color_matches or matched


class SupportConversation:
    def __init__(self, channel):
        self.channel = channel
        self.store, self.workflow = channel.store, channel.workflow
        self.retriever = HybridRetriever(self.workflow.model)

    def context(self, record):
        recent = record["messages"][record.get("context_start", 0) :][-4:]
        return {
            "stage": record["stage"],
            "selected_order": record.get("selected_order"),
            "return_step": (record.get("return_draft") or {}).get("step", ""),
            "last_intent": record.get("last_intent", ""),
            "last_facets": record.get("last_facets", []),
            "pending_offer": record.get("pending_offer"),
            "recent_messages": [
                {"role": m["role"], "text": m["text"][:280]} for m in recent
            ],
        }

    def fact_blocks(self, order=None, catalog_product=None):
        facts = {}
        version = (
            order["policy_version"]
            if order
            else (self.store.setting("policy") or {}).get("version", "")
        )
        try:
            policy = self.workflow.reads.get_policy(version)
            facts["policy_window"] = (
                f"The standard request window is {policy['window_calendar_days_after_item_delivery']} calendar days after the item's delivery, through the end of the deadline day in IST."
            )
            facts["return_conditions"] = (
                "Ordinary returns require an unworn item with its original garment tags attached. Final-sale items and condition exceptions need staff review."
            )
        except SourceError:
            pass
        if order:
            facts.update(
                status=self.order_status_text(order, []),
                eta=self.eta_text(order),
                tracking=(
                    f"Tracking reference: {order['tracking_reference']}\nCarrier: {order['carrier']}"
                    if order.get("tracking_reference")
                    else "A tracking reference isn't available for this purchase yet."
                ),
                payment="The order record shows payment as "
                + order["payment_status"].replace("_", " ")
                + ".",
                total=f"The order total is ₹{order['order_total']:,.2f}.",
                items="\n".join(
                    f"{i['name']} · {i.get('size', '')} / {i.get('color', '')} × {i['quantity']} · {self.status_label(i['status'])}"
                    for i in order["items"]
                ),
                destination="The saved destination is "
                + (order.get("shipping_city") or "not available")
                + ". A full street address is not available in this view.",
            )
        if catalog_product:
            facts["catalog"] = (
                f"{catalog_product['name']} · {catalog_product.get('variant', '')} · ₹{catalog_product['amount']:,.2f} per item."
            )
        return facts

    async def plan(self, record, text, mode):
        context = self.context(record)
        known = None
        session = self.store.session(record["id"])
        reference = self.workflow.explicit_order(text) or record.get("selected_order")
        if reference and session and session["customer"]:
            try:
                known = self.workflow.read_order(session["customer"], reference)
            except SourceError:
                pass
        context["available_fact_blocks"] = list(self.fact_blocks(known))
        if known:
            context["verified_state"] = {
                "fulfilment": known["status"],
                "payment": known["payment_status"],
                "estimate_available": bool(known.get("carrier_eta_date")),
            }
        fallback = fallback_plan(text, context)
        requested = [
            f
            for f in fallback.facets
            if f in ("eta", "tracking", "payment", "total", "items", "destination")
        ]
        if fallback.intent == "policy" and "return_policy" in fallback.facets:
            requested = ["policy_window", "return_conditions"]
        context["requested_fact_blocks"] = requested
        focus_topics = [
            FACET_TOPICS.get(f, f) for f in fallback.facets if f != "summary"
        ]
        preliminary = guides.search(
            text + " " + context["last_intent"],
            topics=focus_topics or TOPICS.get(fallback.intent, []),
            limit=4,
        )
        planning_digest = guides.digest
        canonical = text in {
            "Start a return",
            "My orders",
            "Choose another order",
            "Size or fit",
            "Changed my mind",
            "Damaged or wrong item",
            "Unworn / only tried on",
            "Worn or washed",
            "Tags attached",
            "Tags removed / missing",
            "Continue without a photo",
            "Continue with photos",
            "Continue",
            "Submit return request",
            "Cancel return request",
            "Edit pickup address",
            "Weekday · 10 am–2 pm",
            "Weekday · 2–6 pm",
        } or bool(
            re.fullmatch(
                r"(?:Order #\d{4}|Return item \d{4}-\d+|Return quantity \d+)", text
            )
        )
        # Social turns and exact button contracts don't need inference.
        fast = (
            canonical
            or fallback.intent in ("greeting", "thanks")
            or re.fullmatch(r"\d{1,6}", text.strip())
        )
        used_mode, note = "baseline", None
        usage = {"input_tokens": 0, "output_tokens": 0}
        plan = fallback
        retrieval_details = {"method": "BM25 + approved topic filter"}
        if mode == "model" and not fast:
            try:
                preliminary, retrieval_details = await self.retriever.search(
                    guides,
                    text + " " + context["last_intent"],
                    topics=focus_topics or TOPICS.get(fallback.intent, []),
                    limit=4,
                )
                planner = getattr(self.workflow.model, "plan_support", None)
                if planner is None:
                    raise ModelUnavailable("Planner not configured for this adapter")
                plan, usage = await planner(text, context, preliminary)
                used_mode = "model"
            except ModelUnavailable as exc:
                used_mode, note = "baseline_fallback", str(exc)
        elif mode == "model":
            used_mode = "system"
            note = "Exact UI action or social turn; model call avoided."
        # The model never supplies reported condition/consent fields. Parse the actual message.
        plan.slots = ReportedSlots()
        explicit = explicit_slots(text, context["return_step"])
        for key, value in explicit.model_dump().items():
            if value:
                setattr(plan.slots, key, value)
        # These are deterministic consent/identity boundaries, not model choices.
        if text == "Start a return":
            plan.intent = "return_start"
        if text in ("My orders", "Choose another order"):
            plan.intent = "order_status"
        if record["stage"] == "choose_order" and re.fullmatch(
            r"(?:Order #)?\d{1,4}", text.strip(), re.I
        ):
            pending = record.get("pending_plan") or {}
            plan.intent = pending.get("intent", "order_status")
        if canonical and context["return_step"]:
            plan.intent = "return_answer"
        if fallback.intent == "identity":
            plan.intent, plan.facets = "identity", []
        if fallback.intent == "delivery_dispute":
            plan.intent = "delivery_dispute"
        if fallback.intent == "human":
            plan.intent = "human"
        if fallback.intent == "policy" and fallback.facets:
            plan.intent, plan.facets = "policy", fallback.facets
            plan.interrupts_return = bool(context["return_step"])
        if (
            plan.intent == "order_status"
            and fallback.intent == "order_status"
            and fallback.facets
        ):
            specific = [f for f in fallback.facets if f != "summary"]
            plan.facets = specific or plan.facets or fallback.facets
        if (
            fallback.intent == "order_status"
            and not fallback.facets
            and re.search(
                r"where is (?:my|the) (?:order|parcel)|check(?: it)? again|latest (?:order )?status|order status",
                text,
                re.I,
            )
        ):
            plan.intent, plan.facets = "order_status", ["summary"]
        if (
            context["return_step"]
            and not plan.interrupts_return
            and any(explicit.model_dump().values())
            and fallback.intent == "return_answer"
        ):
            plan.intent = "return_answer"
        question = bool(
            re.search(
                r"\?|^(?:what|why|how|when|where|can|could|should|are|is|does|do)\b",
                text.strip(),
                re.I,
            )
        )
        if context["return_step"] and question:
            topic = (
                "return_tags"
                if re.search(r"\btag", text, re.I)
                else "return_photos"
                if re.search(r"photo|picture|image|upload", text, re.I)
                else "return_condition"
                if re.search(r"worn|wash|try|tried", text, re.I)
                else None
            )
            if topic:
                plan.intent, plan.facets, plan.interrupts_return = (
                    "policy",
                    [topic],
                    True,
                )
            plan.slots = ReportedSlots()
        topics = [
            FACET_TOPICS.get(f, f) for f in plan.facets if f != "summary"
        ] or TOPICS.get(plan.intent, [])
        retrieved = guides.search(
            text + " " + " ".join(plan.facets), topics=topics, limit=4
        )
        meta = {
            "mode": used_mode,
            "note": note,
            "usage": usage,
            "retrieved": retrieved,
            "planning_retrieved": preliminary,
            "planning_digest": planning_digest,
            "planning_revision": known["revision"] if known else None,
            "retrieval_details": retrieval_details,
            "plan": plan,
        }
        return plan, meta

    def finish(self, record, text, result, meta, started):
        result = {"text": result} if isinstance(result, str) else result
        plan = meta["plan"]
        evidence = result.get("_evidence")
        composed = False
        composition_note = None
        eligible = (
            result.get("outcome")
            in (
                "GUIDE_ANSWER",
                "ORDER_STATUS",
                "DELIVERY_EXCEPTION",
                "CATALOG_ANSWER",
                "CLARIFY",
                "OUT_OF_SCOPE",
            )
            or (
                record.get("return_draft")
                and plan.interrupts_return
                and plan.intent in ("policy", "identity")
            )
        ) and not result.pop("_no_composition", False)
        if (
            meta["mode"] == "model"
            and (plan.reply or plan.opening or plan.closing)
            and eligible
        ):
            facts = self.fact_blocks(
                evidence,
                result.get("product")
                if result.get("outcome") == "CATALOG_ANSWER"
                else None,
            )
            required = []
            if result.get("outcome") in ("ORDER_STATUS", "DELIVERY_EXCEPTION"):
                required = [
                    f
                    for f in plan.facets
                    if f
                    in ("eta", "tracking", "payment", "total", "items", "destination")
                ]
                if (
                    not required
                    or "summary" in plan.facets
                    or plan.intent in ("delivery_delay", "delivery_dispute")
                ):
                    required.append("status")
                if (
                    not plan.facets or "summary" in plan.facets
                ) and plan.intent != "delivery_dispute":
                    required.append("eta")
            if "return_policy" in result.get("_guide_ids", []):
                required.extend(["policy_window", "return_conditions"])
            if result.get("outcome") == "CATALOG_ANSWER" and result.get("product"):
                required.append("catalog")
            if result.get("outcome") in (
                "ORDER_STATUS",
                "DELIVERY_EXCEPTION",
                "CATALOG_ANSWER",
            ):
                facts = {key: value for key, value in facts.items() if key in required}
            template = plan.reply or "\n\n".join(
                p
                for p in [
                    plan.opening,
                    *("{{fact:" + key + "}}" for key in required),
                    plan.closing,
                ]
                if p
            )
            guides.refresh()
            available = {d["id"] for d in meta.get("planning_retrieved", [])}
            if meta.get("planning_digest") and meta["planning_digest"] != guides.digest:
                composition_note = "Response guides changed during inference"
            elif (
                evidence
                and meta.get("planning_revision")
                and evidence["revision"] != meta["planning_revision"]
            ):
                composition_note = (
                    "Order changed during inference; source-rendered fresh answer used"
                )
            elif result.get("outcome") == "GUIDE_ANSWER" and not plan.guide_ids:
                composition_note = (
                    "General answer omitted its retrieved guidance citation"
                )
            else:
                generated, composition_note = compile_reply(
                    template, facts, required, plan.guide_ids, available
                )
                if generated:
                    result["text"] = generated
                    if record.get("return_draft") and plan.interrupts_return:
                        result["text"] += (
                            "\n\nYour return draft is still saved. "
                            + self.pending_question(record["return_draft"])
                        )
                    result["_guide_ids"] = plan.guide_ids
                    composed = True
        trace = {
            "id": "run-" + uuid.uuid4().hex[:10],
            "at": iso_now(),
            "mode": meta["mode"],
            "model": self.workflow.model.model if meta["mode"] == "model" else None,
            "provider": self.workflow.model.provider
            if meta["mode"] == "model"
            else None,
            "region": self.workflow.model.region
            if meta["mode"] == "model"
            else "Local support workflow",
            "usage": meta["usage"],
            "latency_ms": round((time.perf_counter() - started) * 1000),
            "outcome": result.get("outcome", "SUPPORT_ANSWER"),
            "note": meta["note"],
            "plan": plan.model_dump(),
            "reads": list(read_audit.get() or []),
            "retrieval": {
                **meta.get(
                    "retrieval_details", {"method": "BM25 + approved topic filter"}
                ),
                "answer_selection": "approved topic/ID lookup after model planning",
                "version": guides.version,
                "chunks": guides.evidence(meta["retrieved"]),
            },
            "steps": [
                {
                    "name": "Understand customer in context",
                    "state": "passed",
                    "detail": plan.intent + " · " + meta["mode"],
                },
                {
                    "name": "Retrieve approved support guidance",
                    "state": "passed" if meta["retrieved"] else "empty",
                    "detail": ", ".join(d["id"] for d in meta["retrieved"])
                    or "No relevant guide; no invented policy",
                },
                {
                    "name": "Render authorized facts and next step",
                    "state": "passed",
                    "detail": "Model understands and phrases; validated source blocks supply facts; return actions stay in code",
                },
            ],
        }
        evidence = result.pop("_evidence", None)
        if evidence:
            trace["evidence"] = evidence
        used = result.pop("_guide_ids", [])
        trace["retrieval"]["used_chunk_ids"] = used
        trace["retrieval"]["planning_chunks"] = guides.evidence(
            meta.get("planning_retrieved", [])
        )
        trace["composition"] = {
            "model_written": composed,
            "validation": "accepted" if composed else "source_renderer",
            "fallback_reason": composition_note,
        }
        trace["decoding"] = {
            **(
                self.workflow.model.decoding()
                if hasattr(self.workflow.model, "decoding")
                else {"temperature": 0.2, "thinking": False}
            ),
            "max_model_calls_per_turn": 1,
            "fact_cache": False,
        }
        record["latest_trace"] = trace
        self.store.save_trace(trace, record["id"])
        session = self.store.session(record["id"])
        if session and session["customer"]:
            history = session["history"]
            history.extend(
                [
                    {"role": "user", "content": text},
                    {
                        "role": "assistant",
                        "content": result["text"],
                        "order_id": record.get("selected_order") or "",
                        "item_id": (record.get("return_draft") or {}).get(
                            "item_id", ""
                        ),
                        "tool": plan.intent,
                    },
                ]
            )
            self.store.save_history(record["id"], history)
        if plan.intent not in ("thanks", "greeting", "return_answer"):
            record["last_intent"], record["last_facets"] = plan.intent, plan.facets
        return result

    def guidance(self, meta, ids):
        # Add only explicitly relevant, approved chunks to the retrieval result.
        out = []
        for chunk_id in dict.fromkeys(ids):
            doc = next((d for d in meta["retrieved"] if d["id"] == chunk_id), None)
            if not doc:
                base = guides.by_id.get(chunk_id)
                if not base:
                    continue
                doc = next(
                    (
                        d
                        for d in guides.search(
                            base["title"],
                            topics=base["topics"],
                            limit=len(guides.documents),
                        )
                        if d["id"] == chunk_id
                    ),
                    None,
                )
                if doc:
                    meta["retrieved"].append(doc)
            if doc:
                out.append(doc)
        return out

    def general(self, record, text, plan, meta):
        if plan.intent == "greeting":
            return {
                "text": guides.by_id["welcome"]["answer"],
                "actions": [
                    action("Track an order", "Where is my order?"),
                    action("Returns & refunds", "What is your return policy?"),
                    action("Speak to the store", "I want to speak to a person"),
                ],
                "outcome": "WELCOME",
            }
        if plan.intent == "thanks":
            return {
                "text": "You're welcome. If you need anything else with the order, just tell me.",
                "outcome": "ACKNOWLEDGED",
            }
        if plan.intent == "out_of_scope":
            return {
                "text": "I'm here for Threadline purchases and product support. Tell me if this is about a delivery, return, payment or something you bought, and I'll help with the next step.",
                "outcome": "OUT_OF_SCOPE",
            }
        ids = [GUIDE_FACET[f] for f in plan.facets if f in GUIDE_FACET]
        if not ids and plan.intent in GUIDE_FOR:
            ids = [GUIDE_FOR[plan.intent]]
        if not ids and plan.intent == "policy":
            ids = ["return_policy"]
        docs = self.guidance(meta, ids[:2])
        paragraphs = []
        if "return_policy" in ids:
            policy = self.workflow.reads.get_policy(
                (self.store.setting("policy") or {}).get("version", "")
            )
            paragraphs.append(
                f"For the store's standard return, the request window is *{policy['window_calendar_days_after_item_delivery']} calendar days after the item's delivery date*, through the end of the deadline day in IST. The item must be unworn with its original garment tags attached.\n\nFinal-sale or condition exceptions need staff review. If you tell me which purchase this is, I can check its actual deadline and help prepare the request."
            )
        paragraphs.extend(d["answer"] for d in docs if d["id"] != "return_policy")
        if not paragraphs:
            return {
                "text": "Tell me a little more about what you need—has a parcel not arrived, is an item wrong, or are you checking a payment or return? I'll focus on that.",
                "actions": [
                    action("Delivery question", "Where is my order?"),
                    action("Return an item", "Start a return"),
                    action("Payment question", "I have a payment question"),
                ],
                "outcome": "CLARIFY",
            }
        actions = []
        if plan.intent == "identity":
            actions = [
                action("Find my order", "Where is my order?"),
                action("Ask about returns", "What is your return policy?"),
            ]
        elif plan.intent == "policy":
            actions = [
                action("Check my purchase", "Start a return"),
                action("Ask the store", "Please ask support about my question"),
            ]
        return {
            "text": "\n\n".join(paragraphs),
            "actions": actions,
            "_guide_ids": [d["id"] for d in docs],
            "outcome": "GUIDE_ANSWER",
        }

    async def respond(self, record, text, mode):
        started = time.perf_counter()
        read_audit.set([])
        record["latest_trace"] = None
        # Keep code verification and exact contact matching outside inference.
        if record["stage"] == "code":
            return await self.channel.legacy_respond(record, text, mode)
        identifier = self.channel.identifier(text)
        pure_contact = identifier and (
            text.strip().lower() == identifier.lower()
            or record["stage"] == "contact"
            or bool(
                re.search(
                    r"(?:my email|my number|switch account|checkout email|contact is)",
                    text,
                    re.I,
                )
            )
        )
        if pure_contact:
            if record["stage"] in ("verified", "choose_order"):
                self.store.bind_customer(record["id"], None)
                record.update(
                    stage="contact",
                    selected_order=None,
                    choices=[],
                    last_intent="",
                    last_facets=[],
                    pending_offer=None,
                    pending_request="Where is my order?",
                )
                record.pop("return_draft", None)
                record.pop("pending_plan", None)
            remainder = text.replace(identifier, "").strip(" ,.;\n")
            if re.search(
                r"order|return|track|parcel|delivery|refund|paid|payment",
                remainder,
                re.I,
            ):
                record["pending_request"] = remainder
            customer = self.store.find_customer(identifier)
            if customer and self.store.setting("verification_mode") == "demo_match":
                return await self.channel.complete_match(
                    record, customer, mode, "demo_contact_match"
                )
            return self.channel.challenge(record, identifier)
        plan, meta = await self.plan(record, text, mode)
        try:
            if record["stage"] == "contact":
                if plan.intent in PURCHASE or (plan.intent == "return_answer"):
                    record["pending_request"] = text
                    record["pending_plan"] = plan.model_dump()
                    return self.finish(
                        record,
                        text,
                        {
                            "text": "I can check that for you. What email address or mobile number did you use at checkout? I'll find the purchase first, then help with your question.",
                            "outcome": "IDENTIFICATION_REQUIRED",
                        },
                        meta,
                        started,
                    )
                if plan.intent == "human":
                    return self.finish(
                        record, text, self.handoff(record, text, None), meta, started
                    )
                if plan.intent == "catalog":
                    return self.finish(
                        record, text, self.catalog(text, plan, meta), meta, started
                    )
                return self.finish(
                    record, text, self.general(record, text, plan, meta), meta, started
                )
            if record.get("return_draft"):
                result = self.handle_draft(record, text, plan, meta)
                if result is not None:
                    return self.finish(record, text, result, meta, started)
            if text in ("Start a return", "My orders", "Choose another order"):
                record.update(stage="verified", selected_order=None, choices=[])
            # A short acceptance of a previously offered handoff is explicit consent.
            if record.get("pending_offer") and re.fullmatch(
                r"(?:yes|yes please|please do|go ahead|do that)[.! ]*", text, re.I
            ):
                plan.intent = "human"
            if plan.intent in (
                "greeting",
                "thanks",
                "identity",
                "policy",
                "out_of_scope",
                "clarify",
            ):
                return self.finish(
                    record, text, self.general(record, text, plan, meta), meta, started
                )
            if plan.intent == "catalog":
                return self.finish(
                    record, text, self.catalog(text, plan, meta), meta, started
                )
            if plan.intent == "human":
                return self.finish(
                    record,
                    text,
                    self.handoff(record, text, record.get("selected_order")),
                    meta,
                    started,
                )
            result = self.purchase(record, text, plan, meta)
            return self.finish(record, text, result, meta, started)
        except SourceError as exc:
            if exc.code == "INACCESSIBLE_ORDER":
                record.update(selected_order=None, choices=[], stage="verified")
            result = {
                "text": exc.message,
                "outcome": exc.code,
                "actions": []
                if exc.code == "INACCESSIBLE_ORDER"
                else [
                    action(
                        "Ask the store to check", "Please ask support to check my order"
                    )
                ],
            }
            return self.finish(record, text, result, meta, started)

    async def after_match(self, record, text, mode):
        # Reuse the already-understood request when identification was the only missing step.
        saved = record.pop("pending_plan", None)
        if saved:
            plan = SupportPlan.model_validate(saved)
            meta = {
                "mode": "system",
                "note": "Resumed understood request after account matching; model call avoided",
                "usage": {"input_tokens": 0, "output_tokens": 0},
                "plan": plan,
                "retrieved": guides.search(
                    text, topics=TOPICS.get(plan.intent, []), limit=4
                ),
            }
            read_audit.set([])
            try:
                result = self.purchase(record, text, plan, meta)
            except SourceError as exc:
                result = {"text": exc.message, "outcome": exc.code}
            return self.finish(record, text, result, meta, time.perf_counter())
        return await self.respond(record, text, mode)

    def select_order(self, record, text, plan):
        session = self.store.session(record["id"])
        explicit = self.workflow.explicit_order(text)
        choice = re.fullmatch(r"\s*(\d)\s*", text)
        if (
            record["stage"] == "choose_order"
            and choice
            and 0 < int(choice[1]) <= len(record.get("choices", []))
        ):
            explicit = record["choices"][int(choice[1]) - 1]
        if explicit:
            order = self.workflow.read_order(session["customer"], explicit)
            record.update(selected_order=explicit, choices=[], stage="verified")
            return order
        # Resolve a newly named item across the account before retaining the old selection.
        owned = self.workflow.reads.list_orders(session["customer"])
        # A model item hint is never enough to silently select a purchase.
        matches = match_items([i for o in owned for i in o["items"]], text)
        matched_ids = {i["item_id"] for i in matches}
        named = [
            o for o in owned if any(i["item_id"] in matched_ids for i in o["items"])
        ]
        if len(named) == 1:
            order = named[0]
            record.update(
                selected_order=order["order_id"], stage="verified", choices=[]
            )
            return order
        if record.get("selected_order") and not named:
            return self.workflow.read_order(
                session["customer"], record["selected_order"]
            )
        candidates = named or owned
        if (
            re.search(r"latest|most recent|last order|newest", text, re.I)
            and candidates
        ):
            order = max(candidates, key=lambda o: o.get("ordered_at", ""))
            record.update(
                selected_order=order["order_id"], stage="verified", choices=[]
            )
            return order
        if plan.intent in ("order_status", "delivery_delay"):
            active = [
                o
                for o in candidates
                if o["status"] not in ("delivered", "cancelled", "returned")
            ]
            candidates = active or candidates
        elif plan.intent == "return_start":
            delivered = [
                o for o in candidates if any(i.get("delivered_at") for i in o["items"])
            ]
            candidates = delivered or candidates
        if len(candidates) == 1:
            order = candidates[0]
            record.update(
                selected_order=order["order_id"], stage="verified", choices=[]
            )
            return order
        record.update(
            stage="choose_order",
            choices=[o["order_id"] for o in candidates],
            pending_request=text,
            pending_plan=plan.model_dump(),
        )
        return candidates

    def purchase(self, record, text, plan, meta):
        # Menu replies resume the pending concern, instead of defaulting every choice to tracking.
        if record["stage"] == "choose_order" and (
            re.fullmatch(r"(?:Order #)?\d{1,4}", text.strip(), re.I)
        ):
            pending = record.get("pending_plan")
            if pending:
                restored = SupportPlan.model_validate(pending)
                meta["plan"] = plan = restored
        selected = self.select_order(record, text, plan)
        if isinstance(selected, list):
            if not selected:
                return {
                    "text": "I couldn't find a purchase on this account. If you were charged or used another checkout contact, tell me and I'll help the store check it.",
                    "actions": [
                        action(
                            "Ask the store", "Please ask support to find my purchase"
                        )
                    ],
                    "outcome": "NO_ORDERS",
                }
            lines = [
                f"*#{o['order_id']}* · {', '.join(i['name'] for i in o['items'])}\n{self.status_label(o['status'])} · ordered {date_label(o['ordered_at'])}"
                for o in selected
            ]
            return {
                "text": "Which purchase is this about? I found these on your account:\n\n"
                + "\n\n".join(lines),
                "actions": [
                    action("Order #" + o["order_id"], "Order #" + o["order_id"])
                    for o in selected
                ],
                "outcome": "CHOOSE_ORDER",
            }
        order = selected
        self.workflow.reads.get_payment(
            order["customer_id"], order["order_id"], order["revision"]
        )
        pending_text = record.get("pending_request", text)
        original = (
            pending_text
            if re.fullmatch(r"(?:Order #)?\d{1,4}", text.strip(), re.I)
            else text
        )
        record.pop("pending_plan", None)
        record["pending_request"] = ""
        if plan.intent == "return_start":
            matched_items = match_items(order["items"], original)
            if len(matched_items) == 1:
                original += "\nReturn item " + matched_items[0]["item_id"]
            result = self.channel.returns.begin(record, order["order_id"], original)
            if record.get("return_draft"):
                # Preserve compound reported condition/reason, then skip only answered fields.
                slots = explicit_slots(original)
                for k, v in plan.slots.model_dump().items():
                    if v and not getattr(slots, k):
                        setattr(slots, k, v)
                result = self.prefill_return(record, result, slots)
            if record.get("return_draft"):
                side_ids = [
                    GUIDE_FACET[f]
                    for f in plan.facets
                    if f in GUIDE_FACET
                    and f
                    not in (
                        "return_policy",
                        "return_condition",
                        "return_tags",
                        "return_photos",
                    )
                ]
                side_docs = self.guidance(meta, side_ids[:1])
                if side_docs:
                    result["text"] = (
                        "\n\n".join(d["answer"] for d in side_docs)
                        + "\n\n"
                        + result["text"]
                    )
                    result["_guide_ids"] = [d["id"] for d in side_docs]
            return {**result, "outcome": "RETURN_INTAKE", "_evidence": order}
        if plan.intent in ("return_status", "refund_status"):
            items = order["items"]
            returns = [
                (
                    i,
                    self.workflow.reads.get_return(
                        order["customer_id"], order["order_id"], i["item_id"]
                    ),
                )
                for i in items
            ]
            existing = [(i, r) for i, r in returns if r]
            if not existing:
                return {
                    "text": f"There isn't a return or refund request recorded for order #{order['order_id']} yet. If you want to return an item, I can check it and help prepare the request.",
                    "actions": [
                        action(
                            "Prepare a return", f"Return order #{order['order_id']}"
                        ),
                        action(
                            "I already sent it back",
                            "Please ask support to investigate my missing return",
                        ),
                    ],
                    "outcome": "NO_RETURN",
                    "_evidence": order,
                }
            lines = [
                self.workflow.return_result(order, i, "")["message"]
                for i, _ in existing
            ]
            docs = self.guidance(
                meta,
                ["refund_timing"]
                if plan.intent == "refund_status"
                and any(r["status"] != "refunded" for _, r in existing)
                else [],
            )
            return {
                "text": "\n\n".join(lines + [d["answer"] for d in docs]),
                "actions": [
                    action(
                        "Ask about this return", "Please ask support about my return"
                    )
                ],
                "outcome": "RETURN_EXISTING_RETURN",
                "_evidence": order,
                "_guide_ids": [d["id"] for d in docs],
            }
        if plan.intent in ("cancel", "address_change", "exchange"):
            docs = self.guidance(meta, [GUIDE_FOR[plan.intent]])
            text_out = self.order_status_text(order, []) + "\n\n" + docs[0]["answer"]
            record["pending_offer"] = {
                "request": original,
                "order_id": order["order_id"],
            }
            return {
                "text": text_out,
                "actions": [
                    action(
                        "Ask the store to help",
                        "Please ask support to help with " + original,
                    )
                ],
                "outcome": "ACTION_REVIEW_REQUIRED",
                "_evidence": order,
                "_guide_ids": [d["id"] for d in docs],
            }
        return self.order_reply(record, order, original, plan, meta)

    @staticmethod
    def status_label(status):
        return {
            "processing": "Being prepared",
            "in_transit": "In transit",
            "delivered": "Delivered",
            "partially_delivered": "Partially delivered",
            "cancelled": "Cancelled",
            "returned": "Returned",
        }.get(status, status)

    def order_status_text(self, order, facets):
        name = order["items"][0]["name"] if len(order["items"]) == 1 else "order"
        status = {
            "processing": "is still being prepared",
            "in_transit": "is on its way",
            "delivered": "is recorded as delivered",
            "partially_delivered": "has been partly delivered",
            "cancelled": "is marked cancelled",
            "returned": "is marked returned",
        }[order["status"]]
        return f"Your {name} from order *#{order['order_id']}* {status}."

    def eta_text(self, order):
        if order["status"] == "delivered":
            dates = [i["delivered_at"] for i in order["items"] if i.get("delivered_at")]
            return (
                "The saved delivery date is *"
                + date_label(max(dates))
                + "*. If you haven't received it, tell me and I'll help report that."
                if dates
                else "It is marked delivered, but a delivery date isn't available."
            )
        if order["status"] in ("cancelled", "returned"):
            return "There isn't an active delivery estimate for this order."
        eta = order.get("carrier_eta_date")
        if not eta:
            return "There isn't a confirmed delivery estimate in the current record. I can ask the store to check dispatch or the courier update."
        today = (
            parse_time(self.store.setting("demo_now"))
            .astimezone(ZoneInfo("Asia/Kolkata"))
            .date()
        )
        if parse_time(eta).date() < today:
            return f"The carrier's last estimate was *{date_label(eta)}*. That date has passed and no newer estimate is saved. I can't give you a reliable new arrival date yet."
        return f"The carrier currently estimates *{date_label(eta)}*. That's an estimate, so I can't guarantee a particular time or an earlier arrival."

    def order_reply(self, record, order, text, plan, meta):
        facets = plan.facets or ["summary"]
        paragraphs = []
        ids = []
        if plan.emotion in ("frustrated", "urgent") or plan.intent in (
            "delivery_delay",
            "delivery_dispute",
        ):
            paragraphs.append(
                "I'm sorry you've had to chase this."
                if plan.emotion != "urgent"
                else "I understand the timing matters. I'll be clear about what I can confirm."
            )
        if "summary" in facets or plan.intent in ("delivery_delay", "delivery_dispute"):
            paragraphs.append(self.order_status_text(order, facets))
            if plan.intent != "delivery_dispute":
                paragraphs.append(self.eta_text(order))
        elif "eta" in facets:
            paragraphs.append(self.eta_text(order))
        if "tracking" in facets:
            paragraphs.append(
                (
                    f"*Tracking reference:* {order['tracking_reference']}\n*Carrier:* {order['carrier']}"
                    if order.get("tracking_reference")
                    else "A tracking reference hasn't been saved for this purchase yet. I can ask the store to check it."
                )
            )
        if "payment" in facets:
            paragraphs.append(
                f"*Payment for #{order['order_id']}:* {order['payment_status'].replace('_', ' ').capitalize()} in the order record."
            )
        if "total" in facets:
            paragraphs.append(f"*Order total:* ₹{order['order_total']:,.2f}.")
        if "destination" in facets:
            paragraphs.append(
                "The saved delivery destination is *"
                + (order.get("shipping_city") or "not available")
                + "*. Full street-address details aren't available in this order view."
            )
        if "items" in facets or (len(order["items"]) > 1 and "summary" in facets):
            paragraphs.append(
                "\n".join(
                    f"*{i['name']}* · {i.get('size', '')} / {i.get('color', '')} × {i['quantity']}\n{self.status_label(i['status'])}"
                    + (
                        " · " + date_label(i["delivered_at"])
                        if i.get("delivered_at")
                        else ""
                    )
                    for i in order["items"]
                )
            )
        if plan.intent == "delivery_dispute":
            ids.append("delivery_dispute")
        elif plan.intent == "delivery_delay":
            if order["status"] == "processing":
                ids.append("preparing_order")
            else:
                paragraphs.append(
                    "The record doesn't include a verified reason for the delay. I can ask the store to investigate rather than guess what's happened."
                )
        docs = self.guidance(meta, ids)
        paragraphs.extend(d["answer"] for d in docs)
        if plan.intent in ("delivery_delay", "delivery_dispute"):
            record["pending_offer"] = {"request": text, "order_id": order["order_id"]}
            actions = [
                action(
                    "Please investigate",
                    "Please ask support to investigate delivery for order #"
                    + order["order_id"],
                ),
                action(
                    "Check latest update",
                    "Check latest status for order #" + order["order_id"],
                ),
            ]
        else:
            actions = [
                action(
                    "Delivery estimate",
                    "When will order #" + order["order_id"] + " arrive?",
                ),
                action("Return an item", "Start a return"),
                action("Other orders", "Choose another order"),
            ]
        result = {
            "text": "\n\n".join(paragraphs),
            "actions": actions,
            "outcome": "DELIVERY_EXCEPTION"
            if plan.intent in ("delivery_delay", "delivery_dispute")
            else "ORDER_STATUS",
            "_evidence": order,
            "_guide_ids": [d["id"] for d in docs],
        }
        if "summary" in facets:
            result["product"] = product(order["items"][0], order)
        return result

    def handoff(self, record, text, order_id):
        offer = record.pop("pending_offer", None)
        if offer:
            order_id = order_id or offer.get("order_id")
            text = offer["request"] + "\nCustomer asked the store to help: " + text
        explicit = self.workflow.explicit_order(text)
        result = self.workflow.make_ticket(
            self.store.session(record["id"]),
            explicit or order_id or "",
            text,
            self.store.session(record["id"])["history"],
        )
        if result["outcome"] != "HANDOFF_CREATED":
            return {"text": result["message"], "outcome": result["outcome"]}
        ticket = result["card"]
        record["last_ticket"] = ticket["id"]
        return {
            "text": f"I've saved your request as *{ticket['id']}* for the store team"
            + (f" on order #{ticket['order_id']}" if ticket.get("order_id") else "")
            + ". Your question and the available order details are attached, so you won't need to start from scratch.\n\n"
            + ticket["queue_message"],
            "outcome": "HANDOFF_CREATED",
            "actions": [action("Check my order", "Where is my order?")]
            if order_id
            else [],
            "_evidence": ticket.get("evidence"),
        }

    def catalog(self, text, plan, meta):
        from .erp import CATALOG

        docs = self.guidance(
            meta, ["exchange_size" if "size_guide" in plan.facets else "catalog_limits"]
        )
        terms = set(re.findall(r"[a-z]+", text.lower()))
        named = [
            p
            for p in CATALOG
            if any(w in terms for w in p["name"].lower().split() if len(w) > 4)
        ]
        if not named:
            return {
                "text": "Our saved catalogue includes "
                + ", ".join(p["name"] for p in CATALOG)
                + ".\n\n"
                + docs[0]["answer"],
                "outcome": "CATALOG_ANSWER",
                "_guide_ids": [d["id"] for d in docs],
            }
        p = named[0]
        return {
            "text": f"*{p['name']}* is listed at *₹{p['price']:,.2f}* in {p['color']}.\n\n"
            + docs[0]["answer"],
            "product": product({**p, "unit_price": p["price"], "quantity": 1}),
            "outcome": "CATALOG_ANSWER",
            "_guide_ids": [d["id"] for d in docs],
        }

    def prefill_return(self, record, result, slots):
        draft = record.get("return_draft")
        if not draft:
            return result
        for key in ("reason", "condition", "tags"):
            value = getattr(slots, key)
            if value:
                draft.setdefault("reported", {})[key] = value
        for _ in range(3):
            current = draft["step"]
            answer = draft.get("reported", {}).get(current)
            if current not in ("reason", "condition", "tags") or not answer:
                break
            result = self.channel.returns.advance(record, answer)
        return result

    def handle_draft(self, record, text, plan, meta):
        draft = record["return_draft"]
        if re.fullmatch(
            r"(?:cancel (?:return )?request|stop return|cancel this return|discard (?:the )?draft)",
            text,
            re.I,
        ):
            return self.channel.returns.advance(record, "Cancel return request")
        if plan.intent == "human":
            # Keep the draft for a later resumption; a support question must not erase answers.
            return self.handoff(record, text, draft["order_id"])
        if (
            plan.intent
            in (
                "policy",
                "identity",
                "catalog",
                "order_status",
                "return_status",
                "refund_status",
                "delivery_delay",
                "cancel",
                "address_change",
                "exchange",
            )
            and plan.interrupts_return
        ):
            if plan.intent in ("policy", "identity"):
                result = self.general(record, text, plan, meta)
            elif plan.intent == "catalog":
                result = self.catalog(text, plan, meta)
            elif plan.intent in ("return_status", "refund_status"):
                result = {
                    "text": "This return is still a draft. It hasn't been submitted to the store, so there isn't a saved return or refund request from this conversation yet.",
                    "outcome": "RETURN_DRAFT_STATUS",
                }
            elif plan.intent in ("cancel", "address_change", "exchange"):
                docs = self.guidance(meta, [GUIDE_FOR[plan.intent]])
                result = {
                    "text": docs[0]["answer"],
                    "_guide_ids": [d["id"] for d in docs],
                    "outcome": "ACTION_REVIEW_REQUIRED",
                }
            else:
                order = self.workflow.read_order(
                    self.store.session(record["id"])["customer"], draft["order_id"]
                )
                result = self.order_reply(record, order, text, plan, meta)
            if "return_photos" in plan.facets and re.search(
                r"(?:did|have).*receiv|(?:did|have).*get|uploaded.*(?:yet|received)",
                text,
                re.I,
            ):
                count = len(draft.get("photos", []))
                result["text"] = (
                    f"I've received {count} photo{'s' if count != 1 else ''} for this return draft."
                    if count
                    else "I haven't received a photo for this draft yet. Use + or the camera to attach one, or continue without it for staff review."
                )
                result["_no_composition"] = True
            result["text"] += (
                "\n\nYour return draft is still saved. " + self.pending_question(draft)
            )
            result["actions"] = self.pending_actions(draft)
            return result
        if plan.intent == "thanks":
            return {
                "text": "Of course. " + self.pending_question(draft),
                "actions": self.pending_actions(draft),
                "outcome": "RETURN_INTAKE",
            }
        # Natural language answers map to the same validated state-machine choices.
        slots = plan.slots
        step = draft["step"]
        canonical = text
        if step == "item":
            order, _, _ = self.channel.returns.records(record)
            matches = match_items(order["items"], text)
            if len(matches) == 1:
                canonical = "Return item " + matches[0]["item_id"]
        if (
            step == "condition"
            and not slots.condition
            and re.search(r"(?:not|never|haven't|hasn't).*(?:wash)", text, re.I)
        ):
            return {
                "text": "Got it, it hasn't been washed. Has it only been tried on, or has it been worn for longer?",
                "actions": self.pending_actions(draft),
                "outcome": "RETURN_INTAKE",
            }
        if step in ("reason", "condition", "tags") and getattr(slots, step):
            canonical = getattr(slots, step)
        elif step == "photos" and slots.photo_choice:
            canonical = (
                "Continue without a photo"
                if slots.photo_choice == "skip"
                else "Continue with photos"
            )
        elif step == "quantity" and slots.quantity:
            canonical = "Return quantity " + str(slots.quantity)
        elif step == "window" and slots.window:
            windows = self.workflow.reads.get_policy(
                self.store.order(draft["order_id"])["policy_version"]
            )["pickup_windows"]
            canonical = windows[0] if slots.window == "morning" else windows[-1]
        # A clear correction can update prior reported slots, never submit/approve.
        corrections = []
        if step != "item":
            for key in ("reason", "condition", "tags"):
                value = getattr(slots, key)
                if key != step and key in draft and value and draft.get(key) != value:
                    draft[key] = value
                    draft.setdefault("reported", {})[key] = value
                    corrections.append(value)
        if (
            corrections
            and canonical == text
            and text not in ("Submit return request", "Edit pickup address")
        ):
            return {
                "text": "I've updated the draft: "
                + "; ".join(corrections)
                + ". The store will review the condition.\n\n"
                + self.pending_question(draft),
                "actions": self.pending_actions(draft),
                "outcome": "RETURN_INTAKE",
            }
        result = self.channel.returns.advance(record, canonical)
        if result is None:
            return None
        result = self.prefill_return(record, result, slots)
        if (
            not record.get("return_draft")
            and "request saved" in result.get("text", "").lower()
        ):
            return {**result, "outcome": "RETURN_REQUESTED"}
        return {**result, "outcome": "RETURN_INTAKE"}

    @staticmethod
    def pending_question(draft):
        return {
            "item": "Which item would you like to return?",
            "reason": "What's the main reason for the return?",
            "condition": "Has the item been worn or washed, or only tried on?",
            "tags": "Are the original garment tags still attached?",
            "photos": "Would you like to attach a photo, or continue without one?",
            "quantity": "How many units of this item are you returning?",
            "address": "What is the full pickup address, including the 6-digit PIN?",
            "window": "Would you prefer the morning or afternoon pickup window?",
            "confirm": "Review the details above and choose Submit return request when you're ready.",
        }.get(draft["step"], "Tell me how you'd like to continue.")

    @staticmethod
    def pending_actions(draft):
        mapping = {
            "reason": ["Size or fit", "Changed my mind", "Damaged or wrong item"],
            "condition": ["Unworn / only tried on", "Worn or washed"],
            "tags": ["Tags attached", "Tags removed / missing"],
            "photos": ["Continue with photos", "Continue without a photo"],
            "confirm": [
                "Submit return request",
                "Edit pickup address",
                "Cancel return request",
            ],
        }
        return [action(x, x) for x in mapping.get(draft["step"], [])]
