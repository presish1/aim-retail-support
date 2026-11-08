"""Local WhatsApp-style channel: real WebSocket transport, synthetic identity inbox.

No messages are sent to WhatsApp, email, or SMS. Verification codes are delivered
only to the evaluator's local demo inbox, outside the phone UI.
"""
import asyncio
import hashlib
import hmac
import re
import secrets
import time
import uuid

from starlette.websockets import WebSocketDisconnect

from .service import date_label, iso_now
from .reads import SourceError, read_audit
from .returns_flow import ReturnFlow, choices
from .support import SupportConversation


class ChannelHub:
    def __init__(self):
        self.connections = {}
        self.locks = {}
        self.admin_connections = set()

    async def studio_changed(self, entity="workspace", entity_id=None):
        for socket in list(self.admin_connections):
            try:
                await socket.send_json({"type": "changed", "entity": entity, "id": entity_id, "at": iso_now()})
            except (RuntimeError, OSError, WebSocketDisconnect):
                self.admin_connections.discard(socket)

    def add(self, session_id, socket):
        self.connections.setdefault(session_id, set()).add(socket)

    def remove(self, session_id, socket):
        self.connections.get(session_id, set()).discard(socket)

    async def emit(self, session_id, event):
        for socket in list(self.connections.get(session_id, set())):
            try:
                await socket.send_json(event)
            except (RuntimeError, OSError, WebSocketDisconnect):
                self.remove(session_id, socket)

    async def source_changed(self, store, order_id=None, workflow=None, before=None, notify=False):
        order = store.order(order_id) if order_id else None
        for session_id in list(self.connections):
            session = store.session(session_id)
            if not session or not session["customer"]:
                continue
            if order and session["customer"] != order["customer_id"]:
                continue
            await self.emit(session_id, {"type": "source_changed", "order_id": order_id, "at": iso_now()})
            if not (notify and workflow and order and before):
                continue
            changed = any(before.get(key) != order.get(key) for key in ("status", "carrier_eta_date", "carrier", "tracking_reference", "items"))
            if not changed:
                continue
            async with self.locks.setdefault(session_id, asyncio.Lock()):
                record = store.channel(session_id)
                if not record or record["stage"] != "verified" or record.get("selected_order") != order_id:
                    continue
                try:
                    fresh = workflow.read_order(session["customer"], order_id)
                except Exception:
                    continue
                text = "*Order update · #" + order_id + "*\n\n" + workflow.status_reply(fresh)["message"]
                if len(fresh["items"]) > 1:
                    text += "\n\n" + "\n".join(i["name"] + ": " + i["status"].replace("_", " ") for i in fresh["items"])
                if fresh.get("tracking_reference") and before.get("tracking_reference") != fresh["tracking_reference"]:
                    text += "\nTracking reference: " + fresh["tracking_reference"]
                trace = {"id": "run-" + uuid.uuid4().hex[:10], "at": iso_now(), "mode": "system", "model": None, "provider": None, "region": "Local system", "usage": {"input_tokens": 0, "output_tokens": 0}, "latency_ms": 0, "outcome": "ORDER_UPDATED", "note": None, "evidence": fresh, "steps": [{"name": "Read current order", "state": "passed", "detail": "Saved order revision " + str(fresh.get("revision", 1))}, {"name": "Send order update", "state": "passed", "detail": "Source-backed notification; no model inference"}]}
                message = WhatsAppChannel.bot_message(text, outcome="ORDER_UPDATED")
                record["messages"].append(message)
                record["latest_trace"] = trace
                store.save_channel(record)
                store.save_trace(trace, session_id)
                await self.emit(session_id, {"type": "message", "message": message, "stage": record["stage"], "selected_order": order_id})
        await self.studio_changed("orders", order_id)


class WhatsAppChannel:
    def __init__(self, store, workflow, hub):
        self.store, self.workflow, self.hub = store, workflow, hub
        self.returns = ReturnFlow(store, workflow)
        self.support = SupportConversation(self)

    @staticmethod
    def bot_message(text, **extra):
        return {"id": "wa-" + uuid.uuid4().hex[:14], "role": "assistant", "text": text, "at": iso_now(), **extra}

    def start(self, token=None):
        if token and self.store.channel(token) and self.store.session(token):
            record = self.store.channel(token)
            if record["stage"] == "code" and not record.get("candidate_customer"):
                record.update(stage="contact", code_hash=None, demo_code=None)
                record["messages"].append(self.bot_message("I couldn't find a matching customer account. Please check your checkout email or phone number and try again."))
                self.store.save_channel(record)
            return record
        token = secrets.token_urlsafe(28)
        self.store.new_session(token, None)
        record = {"id": token, "reference": "CON-" + uuid.uuid4().hex[:6].upper(), "created_at": iso_now(), "stage": "contact", "pending_request": "", "candidate_customer": None,
                  "code_hash": None, "demo_code": None, "expires_at": 0, "attempts": 0,
                  "selected_order": None, "choices": [], "latest_trace": None,
                  "messages": [self.bot_message("Hi there! 👋 Welcome to Threadline.\n\nI can help track an order or check a return. What can I help you with today?")]}
        self.store.save_channel(record)
        return record

    def snapshot(self, record):
        session = self.store.session(record["id"])
        customer = self.store.customer(session["customer"]) if session and session["customer"] else None
        return {"type": "session", "session_id": record["id"], "stage": record["stage"],
                "messages": [{k: v for k, v in m.items() if k != "handled"} for m in record["messages"]],
                "customer_name": customer["first_name"] if customer else None,
                "selected_order": record["selected_order"]}

    @staticmethod
    def identifier(text):
        customer_id = re.search(r"\b(?:CUS-?\d{4,}|demo-customer-[ab])\b", text, re.I)
        if customer_id:
            return customer_id[0]
        email = re.search(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", text, re.I)
        if email:
            return email[0]
        international = re.search(r"\+\d[\d ().\-]{7,22}\d", text)
        if international and 10 <= len(re.sub(r"\D", "", international[0])) <= 15:
            return international[0]
        phone = re.search(r"(?<!\w)(?:\+?91[\s.\-]?)?[6-9]\d{4}[\s.\-]?\d{5}(?!\d)", text)
        return phone[0] if phone else None

    @staticmethod
    def code_digest(code):
        return hashlib.sha256(code.encode()).hexdigest()

    def challenge(self, record, identifier):
        customer = self.store.find_customer(identifier)
        if not customer:
            record.update(stage="contact", candidate_customer=None, code_hash=None, demo_code=None, expires_at=0, attempts=0)
            return "I couldn't find a customer account with those details. Please check the email or phone number you used at checkout, or send your customer ID."
        code = f"{secrets.randbelow(1000000):06d}"
        record.update(stage="code", candidate_customer=customer["customer_id"] if customer else None,
                      code_hash=self.code_digest(code), demo_code=code if customer else None,
                      expires_at=time.time() + 300, attempts=0)
        return "Before I open any order details, please enter the 6-digit verification code for that email or phone number."

    def demo_inbox(self, record):
        customer = self.store.customer(record["candidate_customer"]) if record["candidate_customer"] else None
        return {"stage": record["stage"], "code": record["demo_code"] if record["stage"] == "code" else None,
                "recipient": customer["email"] if customer and record["stage"] == "code" else None,
                "expires_in": max(0, round(record["expires_at"] - time.time())) if record["stage"] == "code" else 0,
                "synthetic": True, "delivery": "Local demo inbox only; no email or SMS is sent."}

    async def handle(self, session_id, client_id, text, mode="model"):
        lock = self.hub.locks.setdefault(session_id, asyncio.Lock())
        async with lock:
            record = self.store.channel(session_id)
            if not record:
                await self.hub.emit(session_id, {"type": "reset_required"})
                return
            existing = next((m for m in record["messages"] if m["id"] == client_id), None)
            if existing and (existing["role"] != "user" or existing.get("handled")):
                await self.hub.emit(session_id, self.snapshot(record))
                return
            if not existing:
                existing = {"id": client_id, "role": "user", "text": text, "at": iso_now(), "handled": False}
                record["messages"].append(existing)
                self.store.save_channel(record)
                await self.hub.studio_changed("conversations", record.get("reference"))
            await self.hub.emit(session_id, {"type": "ack", "id": client_id, "at": existing["at"]})
            await self.hub.emit(session_id, {"type": "typing", "active": True, "stage": "understanding"})
            try:
                reply = await self.respond(record, text, mode)
                if isinstance(reply, str):
                    reply = {"text": reply}
                message = self.bot_message(**reply, in_reply_to=client_id)
                record["messages"].append(message)
                existing["handled"] = True
                record["messages"] = record["messages"][-120:]
                self.store.save_channel(record)
                await self.hub.studio_changed("conversations", record.get("reference"))
                await self.hub.emit(session_id, {"type": "message", "message": message, "stage": record["stage"],
                                                 "selected_order": record["selected_order"],
                                                 "customer_name": self.snapshot(record)["customer_name"]})
            except Exception:
                # Leave the request unhandled so a reconnect can retry with its original ID.
                await self.hub.emit(session_id, {"type": "error", "message": "The request couldn't finish. Reconnect to retry it safely.", "retryable": True})
            finally:
                await self.hub.emit(session_id, {"type": "typing", "active": False})

    async def respond(self, record, text, mode):
        return await self.support.respond(record, text, mode)

    async def legacy_respond(self, record, text, mode):
        record["latest_trace"] = None
        if record.get("return_draft"):
            try:
                result = self.returns.advance(record, text)
                if result:
                    await self.hub.studio_changed("returns")
                    return self.record_read_trace(record, result, "RETURN_INTAKE")
            except SourceError as exc:
                return self.record_read_trace(record, {"text": exc.message, "actions": [{"label": "Ask support", "text": "Please contact support about my return"}]}, exc.code)
        identifier = self.identifier(text)
        if identifier and record["stage"] in ("verified", "choose_order"):
            record.update(stage="contact", selected_order=None, choices=[], pending_request="Where is my order?")
            record.pop("return_draft", None)
            self.store.bind_customer(record["id"], None)
        if record["stage"] == "contact":
            if identifier:
                remainder = text.replace(identifier, "").strip(" \n,.;:")
                if re.search(r"\b(order|return|track|parcel|delivery|size|damaged|refund)\b", remainder, re.I):
                    record["pending_request"] = remainder
                customer = self.store.find_customer(identifier)
                if customer and self.store.setting("verification_mode") == "demo_match":
                    return await self.complete_match(record, customer, mode, "demo_contact_match")
                return self.challenge(record, identifier)
            record["pending_request"] = text
            return "Of course — what email address or mobile number did you use at checkout? I'll use it to find your orders."

        if record["stage"] == "code":
            if identifier:
                customer = self.store.find_customer(identifier)
                if customer and self.store.setting("verification_mode") == "demo_match":
                    return await self.complete_match(record, customer, mode, "demo_contact_match")
                return self.challenge(record, identifier)
            if time.time() > record["expires_at"] or record["attempts"] >= 5:
                record.update(stage="contact", demo_code=None, code_hash=None, candidate_customer=None)
                return "That verification has expired. Please share your checkout email or phone number again for a new code."
            record["attempts"] += 1
            supplied = re.fullmatch(r"\s*(\d{6})\s*", text)
            correct = supplied and hmac.compare_digest(self.code_digest(supplied[1]), record["code_hash"] or "")
            if not correct or not record["candidate_customer"]:
                return "I couldn't verify that code. Please try again, or send the checkout email or phone number again."
            return await self.complete_match(record, self.store.customer(record["candidate_customer"]), mode, "demo_code")

        if record["stage"] == "choose_order":
            choices = record["choices"]
            number = re.fullmatch(r"\s*(\d)\s*", text)
            explicit = self.workflow.explicit_order(text)
            if re.search(r"\b(support|person|agent|human|refund|cancel|address|damaged|faulty)\b", text, re.I):
                record["stage"] = "verified"
                return await self.run_workflow(record, text, mode)
            if number and 0 < int(number[1]) <= len(choices):
                explicit = choices[int(number[1]) - 1]
            if explicit:
                record.update(stage="verified", selected_order=explicit, choices=[])
                question = text if re.search(r"\b(return|track|where|refund|delivery|status)\b", text, re.I) else record["pending_request"]
                return await self.run_workflow(record, question + f"\nOrder reference: #{explicit}.", mode)
            if re.search(r"\b(support|person|agent|human)\b", text, re.I):
                record["stage"] = "verified"
                return await self.run_workflow(record, text, mode)
            return "Please choose one of the orders above, or reply with its order number."

        if re.fullmatch(r"\s*(thank(s| you)( so much)?|great|perfect|awesome)[!. 🙏]*\s*", text, re.I):
            return "You're very welcome! 😊 Message us any time you need help with your order."
        if re.fullmatch(r"\s*\d{6}\s*", text):
            return "Your account is already connected. What would you like to know about your order?"
        return await self.route_verified(record, text, mode)

    async def complete_match(self, record, customer, mode, method):
        self.store.bind_customer(record["id"], customer["customer_id"])
        record["context_start"] = len(record["messages"])
        record.update(stage="verified", verification_method=method, candidate_customer=customer["customer_id"], demo_code=None, code_hash=None, expires_at=0, attempts=0)
        question = record["pending_request"] or "Where is my order?"
        if re.fullmatch(r"\s*(hi|hello|hey|hi there|hello there)[!. 👋]*\s*", question, re.I):
            question = "Where is my order?"
        record["pending_request"] = question
        self.store.log("customer", customer["customer_id"], "matched", f"{customer['first_name']} matched in WhatsApp", actor="Customer channel")
        result = await self.support.after_match(record, question, mode)
        prefix = f"Thanks, {customer['first_name']}. I found your account.\n\n"
        if isinstance(result, str):
            return prefix + result
        result["text"] = prefix + result["text"]
        return result

    async def route_verified(self, record, text, mode):
        session = self.store.session(record["id"])
        if not session or not session["customer"]:
            record["stage"] = "contact"
            return "Let's reconnect your account. What email address or mobile number did you use at checkout?"
        if text in ("Choose another order", "Start a return", "My orders"):
            record.update(selected_order=None, choices=[])
            self.store.save_history(record["id"], [])
            text = "Return an item" if text == "Start a return" else "List my orders"
        if re.search(r"\b(support|person|agent|human|refund|address|damaged|faulty|cancel)\b", text, re.I) and not self.workflow.is_return_status(text):
            return await self.run_workflow(record, text, mode)
        explicit = self.workflow.explicit_order(text)
        if explicit or record["selected_order"]:
            selected = explicit or record["selected_order"]
            return await self.run_workflow(record, text + (f"\nOrder reference: #{selected}." if not explicit else ""), mode)
        if not self.store.setting("order_api_available"):
            return {"text": "I can't reach the order system right now, so I can't confirm your orders. Would you like me to ask support to help?", "actions": [{"label": "Contact support", "text": "Please contact support about my order."}]}
        if self.store.setting("feed_health") != "healthy":
            return {"text": "Our delivery feed is delayed. I can't confirm the latest order details right now. Support can help check.", "actions": [{"label": "Contact support", "text": "Please contact support about my order."}]}
        try:
            owned = self.workflow.reads.list_orders(session["customer"])
        except SourceError as exc:
            return {"text": exc.message}
        returns = re.search(r"return|refund|size|too (big|small)|send.*back", text, re.I)
        named = [o for o in owned if any(any(w in text.lower() for w in i["name"].lower().split() if len(w) > 4) for i in o["items"])]
        candidates = named or ([o for o in owned if o["status"] not in ("delivered", "cancelled")] if not returns else owned)
        candidates = candidates or owned
        if not candidates:
            return {"text": "I couldn't find orders on this account. I can ask support to check the purchase details.", "actions": [{"label": "Contact support", "text": "Please contact support."}]}
        if len(candidates) == 1:
            record["selected_order"] = candidates[0]["order_id"]
            return await self.run_workflow(record, text + f"\nOrder reference: #{record['selected_order']}.", mode)
        record.update(stage="choose_order", choices=[o["order_id"] for o in candidates], pending_request=text)
        lines = [f"{n}. *#{o['order_id']}* — {', '.join(i['name'] for i in o['items'])}\n    {o['status'].replace('_', ' ').capitalize()}" for n, o in enumerate(candidates, 1)]
        label = "orders" if returns else "active orders"
        return {"text": f"I found {len(candidates)} {label} on your account:\n\n" + "\n\n".join(lines) + "\n\nWhich one would you like help with?", "actions": [{"label": f"Order #{o['order_id']}", "text": f"Order #{o['order_id']}"} for o in candidates]}

    async def run_workflow(self, record, text, mode):
        if re.search(r"\breturn\b", text, re.I) and not self.workflow.is_return_status(text) and not re.search(r"\b(support|person|agent|human)\b", text, re.I):
            order_id = self.workflow.explicit_order(text) or record.get("selected_order")
            if order_id:
                try:
                    read_audit.set([])
                    result = self.returns.begin(record, order_id, text)
                    record["selected_order"] = order_id
                    return self.record_read_trace(record, result, "RETURN_INTAKE")
                except SourceError as exc:
                    if exc.code == "INACCESSIBLE_ORDER":
                        record["selected_order"] = None
                    return self.record_read_trace(record, {"text": exc.message}, exc.code)
        await self.hub.emit(record["id"], {"type": "typing", "active": True, "stage": "checking_order_system"})
        reply = await self.workflow.chat(record["id"], text, mode)
        record["latest_trace"] = reply["trace"]
        card = reply.get("card")
        if card and card.get("order_id"):
            record["selected_order"] = card["order_id"]
        if reply["outcome"] == "INACCESSIBLE_ORDER":
            record["selected_order"] = None
        message = reply["message"]
        product = None
        if card and card["type"] == "order":
            details = []
            for item in card["items"]:
                if len(card["items"]) == 1:
                    continue  # The catalog preview already shows this item's variant and quantity.
                variant = " · ".join(str(item[k]) for k in ("size", "color") if item.get(k))
                delivery = item["status"].replace("_", " ").capitalize() + (" · " + date_label(item["delivered_at"]) if item.get("delivered_at") else "")
                details.append(f"*{item['name']}* × {item.get('quantity', 1)}" + ("\n" + variant if variant else "") + "\n" + delivery)
            details.append("*Carrier:* " + (card["carrier"] or "Not assigned yet"))
            if card.get("tracking_reference"):
                details.append("*Tracking ref:* " + card["tracking_reference"])
            if card.get("ordered_at"):
                details.append("*Ordered:* " + date_label(card["ordered_at"]))
            if card.get("order_total") is not None:
                details.append(f"*Order total:* ₹{card['order_total']:,.2f}")
            details.append("*Payment:* " + card["payment_status"].replace("_", " ").capitalize())
            if card.get("shipping_city"):
                details.append("*Delivering to:* " + card["shipping_city"])
            message += "\n\n" + "\n".join(details)
            first = card["items"][0]
            product = {"image": first.get("image"), "name": first["name"], "variant": " · ".join([first.get("size", ""), first.get("color", "")]), "amount": first["unit_price"], "quantity": first["quantity"], "order_id": card["order_id"], "status": card["status"].replace("_", " ").capitalize()}
        actions = reply.get("actions", [])
        if card and card["type"] == "order":
            actions = [{"label": "Refresh order", "text": "Check latest status for order #" + card["order_id"]}, {"label": "Start a return", "text": "Start a return"}, {"label": "Other orders", "text": "Choose another order"}]
        return {"text": message, "product": product, "actions": actions, "outcome": reply["outcome"]}

    def record_read_trace(self, record, reply, outcome):
        trace = {"id": "run-" + uuid.uuid4().hex[:10], "at": iso_now(), "mode": "system", "model": None, "provider": None, "region": "Local system", "usage": {"input_tokens": 0, "output_tokens": 0}, "latency_ms": 0, "outcome": outcome, "reads": read_audit.get() or [], "steps": [{"name": "Validated return workflow", "state": "passed" if outcome == "RETURN_INTAKE" else "blocked", "detail": "Explicit customer answers; fresh ownership and policy reads; no model-written facts" if outcome == "RETURN_INTAKE" else outcome}]}
        record["latest_trace"] = trace
        self.store.save_trace(trace, record["id"])
        return {**reply, "outcome": outcome}
