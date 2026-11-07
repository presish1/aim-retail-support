import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .model import ModelUnavailable


def iso_now():
    return datetime.now(timezone.utc).isoformat()


def parse_time(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def date_label(value):
    return datetime.fromisoformat(value[:10]).strftime("%d %B").lstrip("0")


class SourceError(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message


class Workflow:
    def __init__(self, store, model):
        self.store, self.model = store, model

    def read_order(self, customer, order_id):
        # Ownership is checked in the service, never by the model.
        order = self.store.order(order_id)
        if not customer or not order or order["customer_id"] != customer:
            raise SourceError("INACCESSIBLE_ORDER", "I couldn't find an accessible order with those details. Check the number or contact support.")
        if not self.store.setting("order_api_available"):
            raise SourceError("ORDER_SERVICE_UNAVAILABLE", "I can't check your order right now because the order service is unavailable. I can pass your question to support.")
        if self.store.setting("feed_health") == "lagging":
            raise SourceError("ORDER_DATA_LAGGING", "The order system is responding, but its delivery feed is delayed. I can't confirm the latest status. I can ask support to check.")
        return {**order, "fetched_at": iso_now(), "source": "Synthetic order API / SQLite"}

    def baseline(self, message, context, history):
        text = message.lower()
        order_id = self.explicit_order(message) or context.get("order_id", "")
        if self.is_return_status(text):
            name = "check_return_eligibility"
        elif re.search(r"\b(agent|human|person|support|review|refund|cancel|address|damag\w*|faulty|broken)\b", text):
            name = "create_support_ticket"
        elif re.search(r"\b(return\w*|send\s+\w*\s*back|too (big|small)|size|tags?|unworn|worn|deadline|eligible|eligibility)\b", text):
            name = "check_return_eligibility"
        elif re.search(r"\b(where|track\w*|order|parcel|shipment|shipping|delivery|arriv\w*|hoodie|check again|latest|status|update)\b", text):
            name = "get_order_status"
        elif re.search(r"\b(yes|no|this|that|again)\b", text) and context.get("tool"):
            name = context["tool"]
        elif history and context.get("tool") == "check_return_eligibility":
            name = "check_return_eligibility"
        else:
            name = "clarify"
        return {"name": name, "arguments": {"order_id": order_id}, "usage": {"input_tokens": 0, "output_tokens": 0}}

    @staticmethod
    def is_return_status(text):
        return bool(re.search(r"refund\s+(?:status|update)|(?:where|when|has|check|status|update).*\brefund\b|return\s+status|status.*\breturn\b", text, re.I))

    @staticmethod
    def explicit_order(message):
        match = re.search(r"(?<!\d)(\d{4})(?:-\d+)?(?!\d)", message)
        return match[1] if match else ""

    def return_result(self, order, item, customer_words):
        customer_words = customer_words.replace("never worn", "unworn")
        policy = self.store.setting("policy")
        existing = self.store.return_for_item(order["order_id"], item["item_id"])
        if existing:
            summaries = {"requested": "is awaiting review", "approved": "has been approved", "declined": "was declined", "received": "has been received by the store", "refunded": "has a refund recorded in the order system"}
            message = f"Return {existing['id']} for {item['name']} {summaries[existing['status']]}."
            return {"decision": "existing_return", "reason": "Return " + existing["status"], "message": message, "policy_version": order["policy_version"], "return_id": existing["id"], "return_status": existing["status"], "deadline": None, "item_id": item["item_id"], "item_name": item["name"]}
        if order["policy_version"] != policy["version"]:
            return {"decision": "review_required", "reason": "Policy version unavailable", "message": "I can't verify which return policy applies to this purchase. Support needs to review it.", "policy_version": order["policy_version"]}
        result = {"policy_version": policy["version"], "deadline": None, "item_id": item["item_id"], "item_name": item["name"]}
        if re.search(r"\b(damaged?|faulty|broken|defective)\b", customer_words):
            return {**result, "decision": "review_required", "reason": "Damaged item", "message": "I'm sorry the item arrived damaged. Support should review this, including any final-sale restriction. I can pass along the details."}
        if item["returned"]:
            return {**result, "decision": "review_required", "reason": "Already returned", "message": "This item is already marked as returned. Support can check the existing return for you."}
        if item["final_sale"]:
            return {**result, "decision": "ineligible", "reason": "Final sale", "message": "This item is marked final sale and doesn't qualify for an ordinary change-of-mind return. Support can review an exception or a damaged-item claim."}
        if not item["delivered_at"]:
            return {**result, "decision": "needs_information", "reason": "Not delivered", "message": "This item isn't marked as delivered yet, so its return window hasn't started. I can help you check its delivery status."}
        zone = ZoneInfo(policy["timezone"])
        delivered = parse_time(item["delivered_at"]).astimezone(zone).date()
        deadline = delivered + timedelta(days=policy["window_calendar_days_after_item_delivery"])
        result["deadline"] = str(deadline)
        now = parse_time(self.store.setting("demo_now")).astimezone(zone)
        if now.date() > deadline:
            return {**result, "decision": "ineligible", "reason": "Outside return window", "message": f"The standard return request deadline for {item['name']} was {date_label(str(deadline))}. I can ask support to review your request."}
        negative = re.search(r"\b(worn|used|washed)\b|\b(no|without|missing|removed)\b.{0,15}\btags?\b|\bnot\s+unworn\b", customer_words)
        if negative:
            return {**result, "decision": "review_required", "reason": "Condition requires review", "message": "The ordinary return policy requires an unworn item with tags attached. Based on what you've shared, support needs to review its condition."}
        unworn = re.search(r"\b(unworn|never worn)\b", customer_words)
        tags = re.search(r"\btags?\s+(?:are\s+|still\s+)?attached\b|\bwith\s+(?:the\s+)?tags\b", customer_words)
        if not (unworn and tags):
            return {**result, "decision": "needs_information", "reason": "Confirm condition", "message": f"{item['name']} is within its return window, through {date_label(str(deadline))}. Is it unworn with the tags attached?"}
        return {**result, "decision": "eligible", "reason": "Initial conditions met", "message": f"{item['name']} meets the initial return conditions. Your request deadline is {date_label(str(deadline))}. The retailer still needs to inspect the item's condition. Support can help you start the request."}

    def next_staffed(self):
        zone = ZoneInfo(self.store.setting("business_timezone"))
        now = parse_time(self.store.setting("demo_now")).astimezone(zone)
        schedule = self.store.setting("staff_schedule")
        opens = int(schedule["opens_at"][:2])
        closes = int(schedule["closes_at"][:2])
        for offset in range(8):
            candidate = now + timedelta(days=offset)
            if candidate.strftime("%A").lower() not in schedule["days"] or str(candidate.date()) in schedule["holidays"]:
                continue
            if offset == 0 and opens <= now.hour < closes:
                return "Support is currently within its configured staffed hours; your request is queued for review."
            candidate = candidate.replace(hour=opens, minute=0, second=0, microsecond=0)
            if candidate > now:
                return f"Support next opens {candidate.strftime('%A, %d %B at %H:%M')} {candidate.tzname()}. Your request will wait in the queue."
        return "Your request is queued for the next staffed period."

    def make_ticket(self, session, order_id, message, history):
        if not self.store.setting("ticket_store_available"):
            return {"message": "I couldn't save the support request, so no ticket has been created. Please try again shortly or use the retailer's existing support contact.", "outcome": "TICKET_WRITE_FAILED", "card": None, "actions": []}
        evidence = None
        failure = None
        if order_id:
            try:
                evidence = self.read_order(session["customer"], order_id)
            except SourceError as exc:
                if exc.code == "INACCESSIBLE_ORDER":
                    return {"message": exc.message, "outcome": exc.code, "card": None, "actions": []}
                failure = exc.code
        relevant = [m["content"] for n, m in enumerate(history) if m["role"] == "user" and n + 1 < len(history) and history[n + 1].get("order_id") == order_id]
        words = " ".join(relevant[-4:]) + " " + message
        reason = "CUSTOMER_REQUESTED"
        if failure:
            reason = failure
        elif re.search(r"damag|broken|faulty", words, re.I):
            reason = "DAMAGED_ITEM"
        elif re.search(r"return|deadline|window", words, re.I):
            reason = "RETURN_EXCEPTION"
        elif re.search(r"delivery|late|arrive|shipment", words, re.I):
            reason = "DELIVERY_EXCEPTION"
        ticket = {
            "id": "TL-" + uuid.uuid4().hex[:6].upper(), "order_id": order_id or None,
            "reason": reason, "status": "queued", "created_at": iso_now(),
            "customer": session["customer"], "verification": "simulated_verified" if session["customer"] else "not_verified",
            "request": message, "transcript": [{"role": m["role"], "content": m["content"]} for m in history[-8:]] + [{"role": "user", "content": message}],
            "evidence": evidence, "source_failure": failure, "queue_message": self.next_staffed(),
        }
        key = ":".join([session["customer"] or session["id"], order_id or "general", reason])
        ticket = self.store.save_ticket(ticket, session["id"], key)
        return {"message": f"Your request is saved as {ticket['id']}. The original question and available verified context are attached. {ticket['queue_message']}", "outcome": "HANDOFF_CREATED", "card": {"type": "ticket", **ticket}, "actions": []}

    async def chat(self, session_id, message, mode):
        started = time.perf_counter()
        session = self.store.session(session_id)
        if not session:
            raise ValueError("Session expired. Start a new demo session.")
        history = session["history"]
        previous = next((m for m in reversed(history) if m["role"] == "assistant"), {})
        context = {k: previous.get(k, "") for k in ("order_id", "item_id", "tool")}
        trace = {"id": "run-" + uuid.uuid4().hex[:10], "at": iso_now(), "requested_mode": mode,
                 "mode": mode, "model": self.model.model if mode == "model" else None, "provider": self.model.provider if mode == "model" else None,
                 "region": self.model.region if mode == "model" else "No inference", "steps": [], "usage": {"input_tokens": 0, "output_tokens": 0}, "note": None}
        order_id = self.explicit_order(message) or context["order_id"]
        item_id = ""
        tool = "verify"
        if not session["customer"]:
            result = {"message": "Please choose a simulated verified customer above to access purchase information. An order number alone doesn't verify ownership. This prototype's customer selector simulates verification; it isn't real sign-in.", "outcome": "VERIFICATION_REQUIRED", "card": None, "actions": []}
            trace["steps"].append({"name": "Verify customer", "state": "blocked", "detail": "No private lookup performed"})
        else:
            trace["steps"].append({"name": "Verify customer", "state": "passed", "detail": "Simulated customer session; ownership enforced per tool"})
            proposal = self.baseline(message, context, history)
            if mode == "model":
                try:
                    proposal = await self.model.propose(message, history, context)
                    trace["steps"].append({"name": "Understand request", "state": "passed", "detail": self.model.model + " / non-thinking tool selection"})
                except ModelUnavailable as exc:
                    trace["mode"] = "baseline_fallback"
                    trace["note"] = str(exc) + " The rules baseline handled this request."
                    trace["steps"].append({"name": "Understand request", "state": "fallback", "detail": trace["note"]})
            else:
                trace["steps"].append({"name": "Understand request", "state": "passed", "detail": "Deterministic keyword/menu baseline; no LLM"})
            trace["usage"] = proposal["usage"]
            trace["proposal"] = {"name": proposal["name"], "arguments": proposal["arguments"]}
            tool = proposal["name"]
            args = proposal["arguments"]
            # Explicit references take precedence over model guesses and prior context.
            order_id = self.explicit_order(message) or args.get("order_id") or context["order_id"]
            item_id = args.get("item_id", "")
            # All commercial writes and damage claims go to human review even if misrouted.
            if self.is_return_status(message):
                tool = "check_return_eligibility"
            elif re.search(r"\b(refund|cancel|address|damaged|faulty|broken)\b", message, re.I):
                tool = "create_support_ticket"
            if order_id and not re.fullmatch(r"\d{4}", str(order_id)):
                tool = "clarify"
                order_id = ""
            if order_id:
                candidate = self.store.order(order_id)
                if not candidate or candidate["customer_id"] != session["customer"]:
                    # Apply the same server response even when a model refuses to call a tool.
                    tool = "get_order_status"
            if tool == "create_support_ticket":
                result = self.make_ticket(session, order_id, message, history)
                trace["steps"].append({"name": "Persist handoff", "state": "passed" if result["outcome"] == "HANDOFF_CREATED" else "blocked", "detail": result["outcome"]})
            elif tool in ("get_order_status", "check_return_eligibility", "list_my_orders"):
                if not order_id or tool == "list_my_orders":
                    if not self.store.setting("order_api_available"):
                        result = self.source_failure("ORDER_SERVICE_UNAVAILABLE", "I can't read the order system right now. I can pass your question to support.", "")
                    else:
                        owned = self.store.orders(session["customer"])
                        result = {"message": "Which order would you like help with?", "outcome": "CHOOSE_ORDER", "card": None,
                                  "actions": [{"label": "#" + o["order_id"] + " · " + o["items"][0]["name"], "text": ("Check return for " if tool == "check_return_eligibility" else "Track ") + "order #" + o["order_id"]} for o in owned]}
                else:
                    try:
                        order = self.read_order(session["customer"], order_id)
                        trace["steps"].append({"name": "Authorize & read live", "state": "passed", "detail": f"Order #{order_id} · {order['source']}", "fetched_at": order["fetched_at"]})
                        trace["evidence"] = order
                        if tool == "get_order_status":
                            result = self.status_reply(order)
                        else:
                            items = order["items"]
                            if item_id and item_id not in {i["item_id"] for i in items}:
                                trace["steps"].append({"name": "Validate item reference", "state": "passed", "detail": "Discarded a noncanonical model item label; resolving from the customer's words and owned items"})
                                item_id = ""
                            explicit_item = re.search(r"\b\d{4}-\d+\b", message)
                            if explicit_item:
                                item_id = explicit_item[0]
                            if not item_id:
                                named = next((i for i in items if i["name"].lower() in message.lower() or any(word in message.lower() for word in i["name"].lower().split() if len(word) > 4)), None)
                                item_id = named["item_id"] if named else context["item_id"] if order_id == context["order_id"] else ""
                            if not item_id and len(items) == 1:
                                item_id = items[0]["item_id"]
                            item = next((i for i in items if i["item_id"] == item_id), None)
                            if not item:
                                result = {"message": "Which item would you like to return?", "outcome": "CHOOSE_ITEM", "card": None, "actions": [{"label": i["name"], "text": f"Check return for {i['name']} ({i['item_id']}) on order #{order_id}"} for i in items]}
                            else:
                                # Condition statements belong to this item/order, not unrelated past purchases.
                                relevant = [m["content"] for n, m in enumerate(history) if m["role"] == "user" and n + 1 < len(history) and history[n + 1].get("order_id") == order_id and history[n + 1].get("item_id") == item_id]
                                words = " ".join([*relevant[-3:], message]).lower()
                                decision = self.return_result(order, item, words)
                                trace["steps"].append({"name": "Apply return rules", "state": "passed", "detail": decision["reason"] + " / " + decision["policy_version"]})
                                actions = [{"label": "Ask support to review", "text": f"Please ask support to review return for order #{order_id}."}]
                                if decision["reason"] == "Confirm condition":
                                    actions = [{"label": "Unworn, tags attached", "text": f"The {item['name']} ({item_id}) in order #{order_id} is unworn with tags attached."}, {"label": "It has been worn", "text": f"The {item['name']} ({item_id}) in order #{order_id} has been worn."}]
                                if decision["decision"] == "eligible":
                                    actions = [{"label": "Get help starting a return", "text": f"Please ask support to help start a return for order #{order_id}."}]
                                result = {"message": decision.pop("message"), "outcome": "RETURN_" + decision["decision"].upper(), "card": {"type": "return", **decision, "order_id": order_id, "fetched_at": order["fetched_at"]}, "actions": actions}
                    except SourceError as exc:
                        trace["steps"].append({"name": "Authorize & read live", "state": "blocked", "detail": exc.code})
                        result = self.source_failure(exc.code, exc.message, order_id)
            else:
                result = {"message": "I can help with an order's delivery status, return eligibility, or contacting support. What would you like to do?", "outcome": "CLARIFY", "card": None, "actions": [{"label": "Track an order", "text": "Where is my order?"}, {"label": "Check a return", "text": "Can I return an item?"}, {"label": "Talk to support", "text": "I want to talk to support."}]}
        trace["outcome"] = result["outcome"]
        if result["outcome"] == "INACCESSIBLE_ORDER":
            order_id, item_id = "", ""
        trace["latency_ms"] = round((time.perf_counter() - started) * 1000)
        trace["steps"].append({"name": "Render validated response", "state": "passed", "detail": "Transactional values are rendered by the backend; no model-written facts"})
        history.extend([{"role": "user", "content": message}, {"role": "assistant", "content": result["message"], "order_id": order_id, "item_id": item_id, "tool": tool}])
        self.store.save_history(session_id, history)
        self.store.save_trace(trace, session_id)
        return {**result, "trace": trace}

    @staticmethod
    def source_failure(code, message, order_id):
        return {"message": message, "outcome": code, "card": None, "actions": [] if code == "INACCESSIBLE_ORDER" else [{"label": "Pass this to support", "text": "Please contact support" + (f" about order #{order_id}." if order_id else ".")}]}

    def status_reply(self, order):
        status = order["status"].replace("_", " ")
        message = f"Order #{order['order_id']} is {status}."
        eta = order.get("carrier_eta_date")
        now = parse_time(self.store.setting("demo_now")).astimezone(ZoneInfo(self.store.setting("business_timezone"))).date()
        delayed = False
        if order["status"] not in ("delivered", "cancelled"):
            if eta and datetime.fromisoformat(eta).date() < now:
                message += " The carrier's last delivery estimate has passed, and no newer estimate is available. Support can investigate."
                delayed = True
            elif eta:
                message += f" The carrier estimates delivery on {date_label(eta)}. This is an estimate, not a guarantee."
            else:
                message += " A delivery estimate isn't available yet."
        return {"message": message, "outcome": "DELIVERY_EXCEPTION" if delayed else "ORDER_STATUS", "card": {"type": "order", **order}, "actions": [{"label": "Ask support to investigate", "text": f"Please contact support about delivery for order #{order['order_id']}"}] if delayed else [{"label": "Check return eligibility", "text": f"Can I return an item from order #{order['order_id']}?"}]}
