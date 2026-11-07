"""One-time relocation of the synthetic USD samples. Prices are chosen INR fixtures, not FX conversion."""
import json

PRICES = {"Weekday Hoodie": 1999, "Everyday Oxford": 1799, "Straight-leg Chino": 2199,
          "Archive Tee": 699, "Ribbed Cardigan": 2499, "Canvas Overshirt": 2799, "Utility Jacket": 3499}
SKUS = dict(zip(PRICES, ["TL-HOOD-01", "TL-OXFD-02", "TL-CHIN-03", "TL-TEE-04", "TL-CARD-05", "TL-OVER-06", "TL-JACK-07"]))
PHOTOS = dict(zip(PRICES, ["hoodie", "oxford", "chino", "tee", "cardigan", "overshirt", "jacket"]))
COLORS = dict(zip(PRICES, ["Ecru", "White", "Stone", "White", "Mustard", "Olive", "Indigo"]))


def enrich_order(order):
    if order.get("currency") == "USD" and any(i["name"] not in PRICES for i in order["items"]):
        # Unknown historical products need an explicit INR price; never guess an FX rate.
        order["migration_review_required"] = True
        return order
    for item in order["items"]:
        item["sku"] = item.get("sku") or SKUS.get(item["name"], "")
        item["image"] = "/products/" + PHOTOS[item["name"]] + ".jpg" if item["name"] in PHOTOS else None
        if order.get("currency") == "USD":
            item["unit_price"] = PRICES[item["name"]]
    if order.get("currency") == "USD":
        order["currency"] = "INR"
        order["order_total"] = sum(i["unit_price"] * i["quantity"] for i in order["items"])
        order["tracking_reference"] = order.get("tracking_reference", "").removesuffix("US") + "IN"
        if order.get("carrier") == "Demo Carrier":
            order["carrier"] = "Threadline Logistics (demo)"
    return order


def migrate(store, root):
    if not store.setting("catalog_photography_v1"):
        for order in store.orders():
            for item in order["items"]:
                if item["name"] in COLORS:
                    item["color"] = COLORS[item["name"]]
            store.save_order(order)
        store.set_setting("catalog_photography_v1", True)
    if store.setting("india_store_v1"):
        return
    samples = json.loads((root / "data/customers.json").read_text())
    city_map = {"Austin, TX": "Bengaluru, Karnataka", "Seattle, WA": "Mumbai, Maharashtra", "Portland, OR": "Pune, Maharashtra", "Denver, CO": "New Delhi, Delhi", "Chicago, IL": "Hyderabad, Telangana", "Boston, MA": "Chennai, Tamil Nadu", "San Diego, CA": "Ahmedabad, Gujarat", "New York, NY": "Kolkata, West Bengal"}
    for customer in store.all_records("customers"):
        sample = next((c for c in samples if c["customer_id"] == customer["customer_id"]), None)
        if sample and customer["phone"].startswith("+1202555"):
            store.save_customer({**customer, **sample})
        elif customer.get("city") in city_map:
            customer["city"] = city_map[customer["city"]]
            store.save_customer(customer)
    for order in store.orders():
        order["shipping_city"] = city_map.get(order.get("shipping_city"), order.get("shipping_city", ""))
        store.save_order(enrich_order(order))
    for record in store.all_records("returns"):
        order = store.order(record["order_id"])
        item = next((i for i in order["items"] if i["item_id"] == record["item_id"]), None) if order else None
        if item:
            record["refund_amount"] = item["unit_price"] * record["quantity"]
            store.save_return(record)
    store.set_setting("business_timezone", "Asia/Kolkata")
    store.set_setting("policy", json.loads((root / "data/return-policy.json").read_text()))
    store.set_setting("india_store_v1", True)
