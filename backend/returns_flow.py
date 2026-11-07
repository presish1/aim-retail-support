"""Customer return intake: explicit states and verified reads, never LLM-authored facts."""
import re
from .reads import SourceError, read_audit
from .service import iso_now, date_label


def choices(text, options, **extra):
    return {"text": text, "actions": [{"label": label, "text": value} for label, value in options], **extra}


class ReturnFlow:
    def __init__(self, store, workflow):
        self.store, self.workflow = store, workflow

    def records(self, channel):
        customer = self.store.session(channel["id"])["customer"]
        draft = channel["return_draft"]
        order = self.workflow.read_order(customer, draft["order_id"])
        policy = self.workflow.reads.get_policy(order["policy_version"])
        item = next((i for i in order["items"] if i["item_id"] == draft.get("item_id")), None)
        return order, policy, item

    def begin(self, channel, order_id, text):
        customer = self.store.session(channel["id"])["customer"]
        order = self.workflow.read_order(customer, order_id)
        policy = self.workflow.reads.get_policy(order["policy_version"])
        if not policy["create_return_enabled"]:
            return {"text": "Return requests are currently handled by support. I can check the purchase and pass your request to the store.", "actions": [{"label": "Ask support", "text": "Please contact support about return for order #" + order_id}]}
        channel["return_draft"] = {"order_id": order_id, "step": "item", "photos": []}
        named = [i for i in order["items"] if i["item_id"] in text or i["name"].lower() in text.lower()]
        if len(order["items"]) == 1 or len(named) == 1:
            return self.select_item(channel, order, named[0] if named else order["items"][0])
        return choices(f"*Return · Order #{order_id}*\n\nWhich item would you like to return? We'll check it separately, even if the rest of your order is still on the way.", [(i["name"], "Return item " + i["item_id"]) for i in order["items"]])

    def select_item(self, channel, order, item):
        decision = self.workflow.return_result(order, item, "")
        if decision["decision"] in ("existing_return", "ineligible") or decision["reason"] in ("Not delivered", "Already returned"):
            channel.pop("return_draft", None)
            return choices(decision["message"], [("Ask the store to review", "Please contact support about return for order #" + order["order_id"])])
        draft = channel["return_draft"]
        draft.update(item_id=item["item_id"], quantity=1, step="reason", deadline=decision.get("deadline"))
        return choices(f"*Let's arrange your return*\n{item['name']} · {item.get('size', '')} / {item.get('color', '')}\n\n" + (f"Request by {date_label(decision['deadline'])}.\n" if decision.get("deadline") else "") + "What is the main reason?", [("Size or fit", "Size or fit"), ("Changed my mind", "Changed my mind"), ("Damaged / wrong item", "Damaged or wrong item")], product={"image": item.get("image"), "name": item["name"], "variant": " · ".join([item.get("size", ""), item.get("color", "")]), "amount": item["unit_price"], "quantity": item["quantity"]})

    def summary(self, draft, item):
        amount = item["unit_price"] * draft["quantity"]
        exception = draft.get("condition") != "Unworn / only tried on" or draft.get("tags") != "Tags attached" or draft.get("reason") == "Damaged or wrong item"
        draft["review_required"] = exception or not draft["photos"]
        draft["step"] = "confirm"
        return choices(f"*Review your return request*\n\n{item['name']} × {draft['quantity']}\nOrder #{draft['order_id']}\nReason: {draft['reason']}\nCondition: {draft['condition']}\nTags: {draft['tags']}\nPhotos: {len(draft['photos'])} attached\n\n*Pickup address*\n{draft['pickup_address']}\nPreferred window: {draft['pickup_preference']}\n\n*Item value: ₹{amount:,.2f}*\n" + ("The store needs to review the condition or missing photos. " if draft["review_required"] else "") + "Submitting saves a request for review. Pickup and refund are not confirmed yet. Photos are evidence for staff; they have not been automatically assessed.", [("Submit return request", "Submit return request"), ("Edit pickup address", "Edit pickup address"), ("Cancel request", "Cancel return request")])

    def advance(self, channel, text):
        read_audit.set([])
        if re.fullmatch(r"cancel (?:return )?request|stop return", text, re.I):
            channel.pop("return_draft", None)
            return {"text": "I've discarded this draft. No return request or pickup was created."}
        if re.search(r"\b(agent|human|support|person)\b", text, re.I):
            channel.pop("return_draft", None)
            return None
        draft = channel["return_draft"]
        order, policy, item = self.records(channel)
        step = draft["step"]
        if step == "item":
            item = next((i for i in order["items"] if i["item_id"] in text or i["name"].lower() in text.lower()), None)
            if not item:
                return {"text": "Choose one of the items above so I can check the correct purchase."}
            return self.select_item(channel, order, item)
        if not item:
            raise SourceError("ORDER_DATA_INVALID", "This item is no longer available on the order. Please ask support to check it.")
        existing = self.workflow.reads.get_return(order["customer_id"], order["order_id"], item["item_id"])
        if existing and existing["status"] != "declined":
            channel.pop("return_draft", None)
            return {"text": self.workflow.return_result(order, item, "")["message"]}
        if step == "reason":
            reasons = {"Size or fit", "Changed my mind", "Damaged or wrong item"}
            if text not in reasons:
                return {"text": "Please choose a reason above. You can add more detail with your photos."}
            draft.update(reason=text, step="condition")
            return choices("*Item condition · 1 of 3*\n\nHas the item been worn or washed? Trying it on briefly is fine to report as ‘only tried on’. Please describe its actual condition.", [("Unworn / only tried on", "Unworn / only tried on"), ("Worn or washed", "Worn or washed")])
        if step == "condition":
            if text not in ("Unworn / only tried on", "Worn or washed"):
                return {"text": "Please choose the condition above. The store will review any exception."}
            draft.update(condition=text, step="tags")
            return choices("*Tags & packaging · 2 of 3*\n\nAre the original product tags still attached? Removing the outer delivery bag is fine; this question is about the tags on the clothing.", [("Tags attached", "Tags attached"), ("Tags removed / missing", "Tags removed / missing")])
        if step == "tags":
            if text not in ("Tags attached", "Tags removed / missing"):
                return {"text": "Please choose whether the garment tags are attached or removed."}
            draft.update(tags=text, step="photos")
            return choices("*Photos · 3 of 3*\n\nUse the + or camera button to attach a clear photo of the item and its tag. For damage or a wrong item, include the affected area and the product label.\n\nYou can attach up to 3 photos (JPEG, PNG or WebP, 5 MB each). Staff will review them; a photo alone does not approve a return.", [("Continue without a photo", "Continue without a photo")])
        if step == "photos":
            if text not in ("Continue without a photo", "Continue with photos"):
                return choices("Attach a photo using + or the camera, then continue. You can also submit without a photo for staff review.", [("Continue", "Continue with photos"), ("Skip photo", "Continue without a photo")])
            if text == "Continue with photos" and not draft["photos"]:
                return {"text": "I haven't received a photo yet. Please attach one or choose ‘Continue without a photo’."}
            if item["quantity"] > 1:
                draft["step"] = "quantity"
                return choices("How many units of this item are you returning?", [(str(n), "Return quantity " + str(n)) for n in range(1, item["quantity"] + 1)])
            draft["step"] = "address"
            return {"text": "*Pickup details*\n\nPlease send the full pickup address, including the 6-digit PIN code. Avoid adding bank or payment details. We'll save this address with your return request for the store to review."}
        if step == "quantity":
            match = re.fullmatch(r"(?:Return quantity )?(\d+)", text)
            if not match or not 1 <= int(match[1]) <= item["quantity"]:
                return {"text": "Choose a quantity up to the number purchased."}
            draft.update(quantity=int(match[1]), step="address")
            return {"text": "Please send the full pickup address with its 6-digit PIN code."}
        if text == "Edit pickup address":
            draft["step"] = "address"
            return {"text": "Send the corrected pickup address and 6-digit PIN code."}
        if step == "address":
            if len(text) < 15 or len(text) > 500 or not re.search(r"\b[1-9]\d{5}\b", text):
                return {"text": "Please include the building / street, city, and a valid 6-digit PIN code so the store can check pickup availability."}
            draft.update(pickup_address=text, step="window")
            return choices("Which pickup window would you prefer? This is a preference; the store still needs to confirm availability.", [(v, v) for v in policy["pickup_windows"]])
        if step == "window":
            if text not in policy["pickup_windows"]:
                return {"text": "Please choose one of the pickup preferences above."}
            draft["pickup_preference"] = text
            return self.summary(draft, item)
        if step == "confirm":
            if text != "Submit return request":
                return self.summary(draft, item)
            # Recheck live policy, delivery and deadline at submission, not just at intake.
            if not policy["create_return_enabled"]:
                return {"text": "The store has paused return submissions. This draft has not been submitted. Please ask support to help."}
            check = self.workflow.return_result(order, item, "")
            if check["decision"] == "ineligible" or check["reason"] in ("Not delivered", "Already returned"):
                channel.pop("return_draft", None)
                return {"text": "The order changed while we were preparing this request. " + check["message"]}
            record = {"order_id": order["order_id"], "customer_id": order["customer_id"], "item_id": item["item_id"], "item_name": item["name"], "quantity": draft["quantity"], "reason": draft["reason"], "status": "requested", "notes": "", "refund_amount": item["unit_price"] * draft["quantity"], "created_at": iso_now(), "updated_at": iso_now(), "source": "WhatsApp", "condition": draft["condition"], "tags": draft["tags"], "photos": draft["photos"], "pickup_address": draft["pickup_address"], "pickup_preference": draft["pickup_preference"], "review_required": draft["review_required"], "policy_version": policy["version"], "order_revision": order["revision"]}
            saved = self.store.create_return_once(record)
            self.store.log("return", saved["id"], "requested", f"Customer submitted return {saved['id']} for order #{order['order_id']}", actor="WhatsApp customer")
            channel.pop("return_draft", None)
            return choices(f"*Return request saved · {saved['id']}*\n\n{item['name']} × {saved['quantity']}\nItem value: ₹{saved['refund_amount']:,.2f}\n\n*What happens next*\n1. The store reviews your details and photos.\n2. If approved, staff confirms a pickup date and reference.\n3. The returned item is received and inspected.\n4. Staff records the refund after a successful inspection.\n\nYour pickup is not booked yet. You can check progress here at any time.", [("Check return status", "Check return status for order #" + order["order_id"])], receipt={"id": saved["id"], "status": "Awaiting store review", "amount": saved["refund_amount"]})
        return {"text": "Please choose an option above, or cancel the return request."}
