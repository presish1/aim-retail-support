"""Read boundary for customer facts. No model output is accepted as source data."""
import re
import math
from contextvars import ContextVar
from datetime import date, datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

read_audit = ContextVar("read_audit", default=None)


class SourceError(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message


class ItemRecord(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)
    item_id: str
    name: str = Field(min_length=1, max_length=120)
    quantity: int = Field(ge=1)
    unit_price: float | int = Field(ge=0)
    status: Literal["processing", "in_transit", "delivered", "cancelled", "returned"]
    delivered_at: str | None
    final_sale: bool
    returned: bool
    size: str = ""
    color: str = ""
    sku: str = ""
    image: str | None = None


class OrderRecord(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)
    order_id: str
    customer_id: str
    policy_version: str
    status: Literal["processing", "in_transit", "delivered", "partially_delivered", "cancelled", "returned"]
    carrier: str
    carrier_eta_date: str | None
    tracking_reference: str = ""
    ordered_at: str
    source_updated_at: str
    shipping_city: str = ""
    currency: Literal["INR"]
    order_total: float | int = Field(ge=0)
    payment_status: Literal["paid", "pending", "partially_refunded", "refunded"]
    revision: int = Field(ge=1)
    items: list[ItemRecord] = Field(min_length=1)


class PolicyRecord(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)
    version: str
    timezone: Literal["Asia/Kolkata"]
    window_calendar_days_after_item_delivery: int = Field(ge=0, le=365)
    deadline_inclusive_end_of_local_day: Literal[True]
    required_condition: list[str]
    final_sale_ordinary_return_allowed: Literal[False]
    damaged_or_faulty_item_action: Literal["human_review"]
    create_return_enabled: bool
    pickup_windows: list[str] = Field(min_length=1, max_length=3)


class LiveReads:
    def __init__(self, store):
        self.store = store

    def log(self, function, reference, **extra):
        call = {"function": function, "reference": reference,
                "read_at": datetime.now(timezone.utc).isoformat(), **extra}
        if read_audit.get() is not None:
            read_audit.get().append(call)
        return call

    def healthy(self):
        if not self.store.setting("order_api_available"):
            raise SourceError("ORDER_SERVICE_UNAVAILABLE", "I can't check the order system right now. I haven't reused an earlier status. I can ask support to check.")
        if self.store.setting("feed_health") != "healthy":
            raise SourceError("ORDER_DATA_LAGGING", "The delivery feed is delayed, so I can't confirm the latest details. I can ask support to check.")

    def get_customer(self, customer_id):
        customer = self.store.customer(customer_id) if customer_id else None
        if not customer:
            raise SourceError("VERIFICATION_REQUIRED", "Please reconnect your checkout email or mobile number.")
        self.log("get_customer", customer_id)
        return {k: customer.get(k, "") for k in ("customer_id", "first_name", "last_name", "email", "phone", "city")}

    def get_order(self, customer_id, order_id):
        raw = self.store.order(order_id)
        if not customer_id or not raw or raw["customer_id"] != customer_id:
            raise SourceError("INACCESSIBLE_ORDER", "I couldn't find an accessible order with those details. Check the number or contact support.")
        self.healthy()
        try:
            order = OrderRecord.model_validate(raw).model_dump()
            for value in (order["ordered_at"], order["source_updated_at"], *[i["delivered_at"] for i in order["items"] if i["delivered_at"]]):
                if datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is None:
                    raise ValueError("Timezone required")
            if order["carrier_eta_date"]:
                date.fromisoformat(order["carrier_eta_date"])
            if any(not re.fullmatch(r"[\w-]+", i["item_id"]) for i in order["items"]):
                raise ValueError("Invalid item ID")
            if abs(sum(i["unit_price"] * i["quantity"] for i in order["items"]) - order["order_total"]) > .01:
                raise ValueError("Inconsistent total")
            if any(not math.isfinite(v) for v in [order["order_total"], *[i["unit_price"] for i in order["items"]]]):
                raise ValueError("Non-finite amount")
            if any(i["status"] == "delivered" and not i["delivered_at"] for i in order["items"]):
                raise ValueError("Delivery date missing")
            if order["status"] == "delivered" and any(i["status"] not in ("delivered", "returned") for i in order["items"]):
                raise ValueError("Order and item statuses disagree")
        except (ValidationError, ValueError, TypeError):
            raise SourceError("ORDER_DATA_INVALID", "Some order details are incomplete or inconsistent. I can't confirm them safely. Support needs to check the record.")
        call = self.log("get_order", order_id, revision=order["revision"])
        return {**order, "fetched_at": call["read_at"], "source": "Synthetic order API / SQLite"}

    def list_orders(self, customer_id):
        self.get_customer(customer_id)
        self.healthy()
        orders = [self.get_order(customer_id, o["order_id"]) for o in self.store.orders(customer_id)]
        self.log("list_my_orders", customer_id, count=len(orders))
        return orders

    def get_policy(self, version):
        try:
            policy = PolicyRecord.model_validate(self.store.setting("policy")).model_dump()
            if policy["version"] != version or policy["required_condition"] != ["unworn", "tags_attached"] or any(not window.strip() or len(window) > 80 for window in policy["pickup_windows"]):
                raise ValueError()
        except (ValidationError, ValueError, TypeError):
            raise SourceError("POLICY_UNAVAILABLE", "I can't verify the return policy for this purchase. Support needs to review it.")
        self.log("get_return_policy", version)
        return policy

    def get_return(self, customer_id, order_id, item_id):
        order = self.get_order(customer_id, order_id)
        record = self.store.return_for_item(order_id, item_id)
        if record and (record.get("customer_id") != customer_id or record.get("status") not in ("requested", "approved", "pickup_scheduled", "received", "refunded", "declined")):
            raise SourceError("RETURN_DATA_INVALID", "I can't verify the return record. Support needs to check it.")
        if record and (not isinstance(record.get("refund_amount"), (int, float)) or not math.isfinite(record["refund_amount"]) or record["refund_amount"] < 0):
            raise SourceError("RETURN_DATA_INVALID", "The recorded refund amount cannot be verified. Support needs to check it.")
        if record:
            item = next((i for i in order["items"] if i["item_id"] == item_id), None)
            quantity = record.get("quantity")
            if not item or type(quantity) is not int or not 1 <= quantity <= item["quantity"] or abs(record["refund_amount"] - quantity * item["unit_price"]) > .01:
                raise SourceError("RETURN_DATA_INVALID", "The return quantity or value doesn't match the purchase. Support needs to check it.")
        self.log("get_return", order_id + "/" + item_id)
        return {k: record[k] for k in ("id", "order_id", "item_id", "item_name", "quantity", "status", "refund_amount", "created_at", "updated_at", "pickup_slot", "pickup_city", "refund_reference", "public_reason") if k in record} if record else None

    def get_payment(self, customer_id, order_id, expected_revision=None):
        order = self.get_order(customer_id, order_id)
        if expected_revision is not None and order["revision"] != expected_revision:
            raise SourceError("ORDER_CHANGED", "This order changed while I was reading it. Please refresh to get a consistent update.")
        self.log("get_payment", order_id)
        return {k: order[k] for k in ("payment_status", "order_total", "currency")}
