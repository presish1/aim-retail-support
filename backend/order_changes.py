"""Confirmed same-SKU size amendments for owned, unfulfilled synthetic orders.

Configured size options are not warehouse stock. The only write is an explicit,
revision-checked size change; price, quantity, payment and fulfilment stay unchanged.
"""

import json
import re
import time

SIZE = r"(?:extra small|extra large|double extra large|small|medium|large|XXL|XS|XL|S|M|L|28|30|32|34|36)"
ALIASES = {
    "extra small": "XS",
    "small": "S",
    "medium": "M",
    "large": "L",
    "extra large": "XL",
    "double extra large": "XXL",
}


def requested_size(text):
    value = text.strip().rstrip(".!?").strip()
    short = re.fullmatch(
        r"(?:size\s+)?(" + SIZE + r")(?:[, ]+please|[, ]+thanks)?", value, re.I
    )
    if short:
        return ALIASES.get(short[1].lower(), short[1].upper())
    # Only extract the requested destination, never the originally ordered size.
    matches = list(
        re.finditer(
            r"\b(?:to|need|want|prefer|but(?: actually)?)\s+(?:it\s+in\s+|a\s+|an\s+|size\s+)?("
            + SIZE
            + r")\b",
            text,
            re.I,
        )
    )
    if not matches or re.search(
        r"\b(?:don't|do not|not)\s+(?:need|want|change|switch)\b", text, re.I
    ):
        return None
    raw = matches[-1][1]
    return ALIASES.get(raw.lower(), raw.upper())


def choices(text, options, **extra):
    return {
        "text": text,
        "actions": [{"label": label, "text": value} for label, value in options],
        **extra,
    }


class OrderChanges:
    def __init__(self, store, workflow, resolve_items):
        self.store, self.workflow, self.resolve_items = store, workflow, resolve_items

    def read(self, record):
        customer = self.store.session(record["id"])["customer"]
        return self.workflow.read_order(customer, record["size_change"]["order_id"])

    def start(self, record, order, text):
        record["pending_offer"] = None
        record["size_change"] = {
            "order_id": order["order_id"],
            "step": "item",
            "target": requested_size(text),
        }
        if order["status"] != "processing":
            return self.review(record, order, text)
        matches = self.resolve_items(order["items"], text)
        if len(order["items"]) == 1 or len(matches) == 1:
            item = matches[0] if matches else order["items"][0]
            record["size_change"]["item_id"] = item["item_id"]
            return self.preview(record, order)
        return choices(
            "Which item would you like to change?",
            [
                (f"{i['name']} · {i.get('size', '')}", "Change item " + i["item_id"])
                for i in order["items"]
            ],
            outcome="SIZE_CHANGE_ITEM",
            _evidence=order,
        )

    def review(self, record, order, request):
        record.pop("size_change", None)
        status = order["status"].replace("_", " ")
        record["pending_offer"] = {
            "request": request,
            "order_id": order["order_id"],
            "kind": "size_change_review",
        }
        options = [("Ask the store about an exchange", "Yes please")]
        if any(i.get("delivered_at") and not i.get("returned") for i in order["items"]):
            options.append(("Prepare a return", "Return order #" + order["order_id"]))
        return choices(
            f"Order *#{order['order_id']}* is recorded as *{status}*. A size change now needs the store's help; I haven't changed the item. Would you like them to check an exchange?",
            options,
            outcome="SIZE_CHANGE_REVIEW",
            _evidence=order,
        )

    def preview(self, record, order, preamble=""):
        draft = record["size_change"]
        item = next(
            (i for i in order["items"] if i["item_id"] == draft.get("item_id")), None
        )
        if not item:
            record.pop("size_change", None)
            return {
                "text": "That item is no longer on this order. Please choose the purchase again.",
                "outcome": "SIZE_CHANGE_ITEM_MISSING",
            }
        if (
            order["status"] != "processing"
            or item["status"] != "processing"
            or item.get("returned")
        ):
            return self.review(record, order, "Change the size of " + item["name"])
        sizes = self.workflow.reads.get_product_sizes(item.get("sku", ""))
        target = draft.get("target")
        if not target or target not in sizes:
            draft["step"] = "size"
            note = (
                f"Size *{target}* isn't an offered option for this item. "
                if target
                else ""
            )
            return choices(
                preamble
                + note
                + f"What size would you like for *{item['name']}*? Your order currently has *{item.get('size', '')}*.",
                [(size, size) for size in sizes],
                outcome="SIZE_CHANGE_SIZE",
                _evidence=order,
            )
        if target == item.get("size"):
            record.pop("size_change", None)
            return {
                "text": f"Your *{item['name']}* is already size *{target}* in order *#{order['order_id']}*. No change is needed.",
                "outcome": "SIZE_UNCHANGED",
                "_evidence": order,
            }
        draft.update(
            step="confirm",
            revision=order["revision"],
            old_size=item.get("size", ""),
            expires_at=time.time() + 600,
        )
        return choices(
            preamble
            + f"I can change *{item['name']}* in order *#{order['order_id']}* from *{item.get('size', '')} → {target}* ({item['quantity']} item{'s' if item['quantity'] != 1 else ''}).\n\nYour price and quantity stay the same. Shall I make that change?",
            [
                ("Confirm size change", "Confirm size change"),
                ("Keep original size", "Cancel size change"),
            ],
            outcome="SIZE_CHANGE_PREVIEW",
            _evidence=order,
        )

    def handle(self, record, text):
        draft = record.get("size_change")
        if not draft:
            return (
                {
                    "text": "There's no size change waiting for confirmation. Tell me which item and size you want, and I'll check it.",
                    "outcome": "NO_SIZE_CHANGE",
                }
                if text == "Confirm size change"
                else None
            )
        explicit = self.workflow.explicit_order(text)
        if explicit and explicit != draft["order_id"]:
            # Never apply a new reference's request to the previously previewed order.
            record.pop("size_change", None)
            return None
        if re.fullmatch(
            r"(?:cancel (?:size )?change|keep original size|no thanks|not now)[.! ]*",
            text,
            re.I,
        ):
            record.pop("size_change", None)
            return {
                "text": "No problem. I've cancelled that size-change request.",
                "outcome": "SIZE_CHANGE_CANCELLED",
            }
        order = self.read(record)
        if re.search(r"\b(?:what|which|show).*\bsizes\b", text, re.I) and draft.get(
            "item_id"
        ):
            draft["target"] = None
            return self.preview(record, order)
        if draft["step"] == "item":
            matches = self.resolve_items(order["items"], text)
            if len(matches) == 1:
                draft["item_id"] = matches[0]["item_id"]
                return self.preview(record, order)
            return None
        target = requested_size(text)
        if target:
            draft["target"] = target
            return self.preview(record, order)
        confirm = text == "Confirm size change" or bool(
            re.fullmatch(
                r"(?:yes[, ]+change it|yes please[, ]+change it|go ahead[, ]+change it)[.! ]*",
                text,
                re.I,
            )
        )
        # Bare yes is accepted only directly after the exact server-rendered preview.
        last = next(
            (m for m in reversed(record["messages"]) if m["role"] == "assistant"), {}
        )
        confirm = confirm or (
            last.get("outcome") == "SIZE_CHANGE_PREVIEW"
            and bool(re.fullmatch(r"(?:yes|yes please|sure|okay)[.! ]*", text, re.I))
        )
        if not confirm:
            return None
        if draft["step"] != "confirm":
            return self.preview(record, order)
        if (
            draft.get("expires_at", 0) < time.time()
            or order["revision"] != draft["revision"]
        ):
            return self.preview(
                record,
                order,
                "The order changed or the preview expired. Please check the current details before confirming.\n\n",
            )
        customer = self.store.session(record["id"])["customer"]
        try:
            _, after = self.store.amend_order_size(
                customer,
                order["order_id"],
                draft["item_id"],
                draft["target"],
                draft["revision"],
            )
        except ValueError as exc:
            if str(exc) == "source_unavailable":
                return {
                    "text": "I can't verify the order service right now, so I haven't made the change. Please try again shortly.",
                    "outcome": "SIZE_CHANGE_SOURCE_UNAVAILABLE",
                }
            if str(exc) == "unsupported_size":
                record["size_change"]["target"] = None
            return self.preview(
                record,
                self.read(record),
                "The order or size options changed. Let's check them again before making a change.\n\n",
            )
        item = next(i for i in after["items"] if i["item_id"] == draft["item_id"])
        old = draft["old_size"]
        record.pop("size_change", None)
        # A successful commit receipt remains valid if a subsequent source refresh fails.
        # Keep the already-authorized public projection, applying only the committed delta.
        fresh = json.loads(json.dumps(order))
        next(i for i in fresh["items"] if i["item_id"] == item["item_id"])["size"] = (
            item["size"]
        )
        fresh.update(
            revision=after["revision"],
            source_updated_at=after["source_updated_at"],
            fetched_at=after["source_updated_at"],
        )
        self.workflow.reads.log(
            "change_order_size", after["order_id"], revision=after["revision"]
        )
        return {
            "text": f"You're all set. *{item['name']}* in order *#{after['order_id']}* is now size *{item['size']}* (previously {old}).\n\nYour price and quantity are unchanged.",
            "outcome": "SIZE_CHANGED",
            "_evidence": fresh,
        }
