"""Customer-facing delivery facts, rendered only from a validated owned order."""

from zoneinfo import ZoneInfo

from .service import date_label, parse_time


def estimate_state(order, demo_now):
    if order["status"] in ("delivered", "cancelled", "returned"):
        return "not_applicable"
    if not order.get("carrier_eta_date"):
        return "missing"
    today = parse_time(demo_now).astimezone(ZoneInfo("Asia/Kolkata")).date()
    return "past" if parse_time(order["carrier_eta_date"]).date() < today else "current"


def estimate_text(order, demo_now):
    if order["status"] == "delivered":
        dates = [i["delivered_at"] for i in order["items"] if i.get("delivered_at")]
        return (
            "The delivery date on this order is *" + date_label(max(dates)) + "*."
            if dates
            else "This order is marked delivered, but a delivery date isn't available."
        )
    if order["status"] in ("cancelled", "returned"):
        return "There isn't an active delivery estimate for this order."
    eta = order.get("carrier_eta_date")
    if not eta:
        return (
            "I don't have a delivery date to confirm yet. I can ask the store to check."
        )
    today = parse_time(demo_now).astimezone(ZoneInfo("Asia/Kolkata")).date()
    if parse_time(eta).date() < today:
        return f"The last delivery estimate was *{date_label(eta)}*. That date has passed, and there isn't a newer estimate yet."
    return f"*Estimated delivery: {date_label(eta)}.* This is an estimate, so the date may change."
