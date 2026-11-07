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


class ChannelHub:
    def __init__(self):
        self.connections = {}
        self.locks = {}

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

    async def source_changed(self, store, order_id=None):
        order = store.order(order_id) if order_id else None
        for session_id in list(self.connections):
            session = store.session(session_id)
            if not session or not session["customer"]:
                continue
            if order and session["customer"] != order["customer_id"]:
                continue
            await self.emit(session_id, {"type": "source_changed", "order_id": order_id, "at": iso_now()})


class WhatsAppChannel:
    def __init__(self, store, workflow, hub):
        self.store, self.workflow, self.hub = store, workflow, hub

    @staticmethod
    def bot_message(text, **extra):
        return {"id": "wa-" + uuid.uuid4().hex[:14], "role": "assistant", "text": text, "at": iso_now(), **extra}

    def start(self, token=None):
        if token and self.store.channel(token) and self.store.session(token):
            return self.store.channel(token)
        token = secrets.token_urlsafe(28)
        self.store.new_session(token, None)
        record = {"id": token, "stage": "contact", "pending_request": "", "candidate_customer": None,
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
                "selected_order": record["selected_order"], "latest_trace": record["latest_trace"]}

    @staticmethod
    def identifier(text):
        email = re.search(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", text, re.I)
        if email:
            return email[0]
        phone = re.search(r"(?<!\w)(?:\+?1[\s.\-]?)?\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}(?!\d)", text)
        return phone[0] if phone else None

    @staticmethod
    def code_digest(code):
        return hashlib.sha256(code.encode()).hexdigest()

    def challenge(self, record, identifier):
        customer = self.store.find_customer(identifier)
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
                await self.hub.emit(session_id, {"type": "message", "message": message, "stage": record["stage"],
                                                 "latest_trace": record["latest_trace"], "selected_order": record["selected_order"],
                                                 "customer_name": self.snapshot(record)["customer_name"]})
            except Exception:
                # Leave the request unhandled so a reconnect can retry with its original ID.
                await self.hub.emit(session_id, {"type": "error", "message": "The request couldn't finish. Reconnect to retry it safely.", "retryable": True})
            finally:
                await self.hub.emit(session_id, {"type": "typing", "active": False})

    async def respond(self, record, text, mode):
        record["latest_trace"] = None
        identifier = self.identifier(text)
        if record["stage"] == "contact":
            if identifier:
                remainder = text.replace(identifier, "").strip(" \n,.;:")
                if re.search(r"\b(order|return|track|parcel|delivery|size|damaged|refund)\b", remainder, re.I):
                    record["pending_request"] = remainder
                return self.challenge(record, identifier)
            record["pending_request"] = text
            return "Of course — what email address or mobile number did you use at checkout? I'll use it to find your orders."

        if record["stage"] == "code":
            if identifier:
                return self.challenge(record, identifier)
            if time.time() > record["expires_at"] or record["attempts"] >= 5:
                record.update(stage="contact", demo_code=None, code_hash=None, candidate_customer=None)
                return "That verification has expired. Please share your checkout email or phone number again for a new code."
            record["attempts"] += 1
            supplied = re.fullmatch(r"\s*(\d{6})\s*", text)
            correct = supplied and hmac.compare_digest(self.code_digest(supplied[1]), record["code_hash"] or "")
            if not correct or not record["candidate_customer"]:
                return "I couldn't verify that code. Please try again, or send the checkout email or phone number again."
            self.store.bind_customer(record["id"], record["candidate_customer"])
            record.update(stage="verified", demo_code=None, code_hash=None, expires_at=0, attempts=0)
            question = record["pending_request"] or "Where is my order?"
            if re.fullmatch(r"\s*(hi|hello|hey|hi there|hello there)[!. 👋]*\s*", question, re.I):
                question = "Where is my order?"
            record["pending_request"] = question
            result = await self.route_verified(record, question, mode)
            customer = self.store.customer(self.store.session(record["id"])["customer"])
            if isinstance(result, str):
                return f"Thanks, {customer['first_name']} — you're verified. ✅\n\n" + result
            result["text"] = f"Thanks, {customer['first_name']} — you're verified. ✅\n\n" + result["text"]
            return result

        if record["stage"] == "choose_order":
            choices = record["choices"]
            number = re.fullmatch(r"\s*(\d)\s*", text)
            explicit = self.workflow.explicit_order(text)
            if number and 0 < int(number[1]) <= len(choices):
                explicit = choices[int(number[1]) - 1]
            if explicit:
                record.update(stage="verified", selected_order=explicit, choices=[])
                return await self.run_workflow(record, record["pending_request"] + f"\nOrder reference: #{explicit}.", mode)
            if re.search(r"\b(support|person|agent|human)\b", text, re.I):
                record["stage"] = "verified"
                return await self.run_workflow(record, text, mode)
            return "Please choose one of the orders above, or reply with its order number."

        if re.fullmatch(r"\s*(thank(s| you)( so much)?|great|perfect|awesome)[!. 🙏]*\s*", text, re.I):
            return "You're very welcome! 😊 Message us any time you need help with your order."
        if re.fullmatch(r"\s*\d{6}\s*", text):
            return "You're already verified. What would you like to know about your order?"
        return await self.route_verified(record, text, mode)

    async def route_verified(self, record, text, mode):
        session = self.store.session(record["id"])
        if not session or not session["customer"]:
            record["stage"] = "contact"
            return "Let's reconnect your account. What email address or mobile number did you use at checkout?"
        if re.search(r"\b(support|person|agent|human|refund|address|damaged|faulty|cancel)\b", text, re.I):
            return await self.run_workflow(record, text, mode)
        explicit = self.workflow.explicit_order(text)
        if explicit or record["selected_order"]:
            selected = explicit or record["selected_order"]
            return await self.run_workflow(record, text + (f"\nOrder reference: #{selected}." if not explicit else ""), mode)
        if not self.store.setting("order_api_available"):
            return {"text": "I can't reach the order system right now, so I can't confirm your orders. Would you like me to ask support to help?", "actions": [{"label": "Contact support", "text": "Please contact support about my order."}]}
        if self.store.setting("feed_health") != "healthy":
            return {"text": "Our delivery feed is delayed. I can't confirm the latest order details right now. Support can help check.", "actions": [{"label": "Contact support", "text": "Please contact support about my order."}]}
        owned = self.store.orders(session["customer"])
        returns = re.search(r"return|size|too (big|small)|send.*back", text, re.I)
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
        await self.hub.emit(record["id"], {"type": "typing", "active": True, "stage": "checking_order_system"})
        reply = await self.workflow.chat(record["id"], text, mode)
        record["latest_trace"] = reply["trace"]
        card = reply.get("card")
        if card and card.get("order_id"):
            record["selected_order"] = card["order_id"]
        if reply["outcome"] == "INACCESSIBLE_ORDER":
            record["selected_order"] = None
        message = reply["message"]
        if card and card["type"] == "order":
            details = []
            for item in card["items"]:
                variant = " · ".join(str(item[k]) for k in ("size", "color") if item.get(k))
                details.append(f"*{item['name']}* × {item.get('quantity', 1)}" + ("\n" + variant if variant else ""))
            details.append("*Carrier:* " + card["carrier"])
            if card.get("tracking_reference"):
                details.append("*Tracking ref:* " + card["tracking_reference"])
            if card.get("ordered_at"):
                details.append("*Ordered:* " + date_label(card["ordered_at"]))
            if card.get("order_total") is not None:
                details.append(f"*Order total:* {card.get('currency', 'USD')} {card['order_total']:.2f}")
            if card.get("shipping_city"):
                details.append("*Delivering to:* " + card["shipping_city"])
            message += "\n\n" + "\n".join(details)
        return {"text": message, "actions": reply.get("actions", []), "outcome": reply["outcome"]}
