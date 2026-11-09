# 13 — Tools, business systems and real-life scenarios

**Presentation point:** AI understands the request; business tools supply evidence; rules and people control actions. A “tool” is not automatically an unrestricted API connection.

## A. Current phone orchestration and legacy model tools

In v0.8 the phone uses a typed Gemini support plan from [support_plan.py](../backend/support_plan.py). [support.py](../backend/support.py) runs hybrid retrieval and dispatches authorized reads or guarded workflows. The model does not emit a free-running API sequence. Its fields are intent, facets, emotion, literal item hint, guide IDs, conversational opening/closing and an optional delivery-investigation offer. The server inserts factual paragraphs between them. Reported return answers and consent are parsed separately. [Document 19](19-gemini-hybrid-live-data.md) specifies the current path.

The following four model-callable schemas remain in the **legacy HTTP chat path**, not the new phone's generation contract:

Defined in [model.py](../backend/model.py), executed by [service.py](../backend/service.py).

| Name | Model arguments | Server behavior | Writes? |
| --- | --- | --- | --- |
| `get_order_status` | `order_id: string` | Use explicit/confirmed reference, inject bound customer, validate current order/payment reads, render status | No commercial write |
| `list_my_orders` | None | Read only bound customer's validated orders | No commercial write |
| `check_return_eligibility` | `order_id`, optional `item_id` | Resolve owned item, applicable policy and condition context; or read existing return | No commercial write |
| `create_support_ticket` | `order_id` | Save original request, relevant history, available evidence and queue state; deduplicate active handoff | Support ticket only |

There is no model-callable refund, pickup booking, arbitrary HTTP/SQL, image inspection, address change, stock reservation or policy-edit tool. A proposal containing an unknown name/property/type is rejected. Valid model proposals can still misinterpret intent, which must be evaluated separately.

## B. Internal read functions

| Python function | Used for | Checks / projection |
| --- | --- | --- |
| `LiveReads.get_customer` | Account context and order listing | Existing customer; public account fields, excluding internal notes |
| `LiveReads.list_orders` | Owned purchase selection | Customer plus source health; validated reads of that customer's orders |
| `LiveReads.get_order` | Current purchase facts | Ownership, source/feed health, strict source schema, amounts/dates/selected consistency checks |
| `LiveReads.get_payment` | Current payment projection | Owned order reread; optional expected revision |
| `LiveReads.get_policy` | Bound return rules | Exact version and supported structured policy shape |
| `LiveReads.get_product_sizes` | Size amendment choices | Healthy source; enabled SKU options, not stock or reservation |
| `LiveReads.get_return` | Existing RMA/refund status | Owned order; return status, quantity/value and customer-safe fields |

Source: [reads.py](../backend/reads.py). Audit names include `list_my_orders` and `get_return_policy`; the model does not thereby gain those internal Python methods as separate free-running tools. Current phone orchestration invokes these methods through the application controller. Guide search in [retrieval.py](../backend/retrieval.py) supplies approved explanatory text; it never establishes live order/payment state.

## C. Deterministic commands currently implemented

The customer can submit a return draft explicitly and confirm a same-SKU size change on an owned unfulfilled order. `Store.amend_order_size` rechecks ownership, health, expected revision, fulfilment and enabled size inside a transaction; size, revision and activity commit together. [Document 20](20-delivery-and-order-actions.md) describes the preview/consent and conflict rules. Staff can create/edit synthetic customers/orders, change fulfilment, transition returns and update support tickets. These are validated workflow/API commands, not unconstrained LLM actions. Local record changes do not call external payment or carrier systems. See [API reference](16-api-and-data-reference.md).

## D. Proposed business adapters

Actual retailer vendors are unknown. Integrate existing services where possible; do not buy every example below. The names in backticks are **proposed internal contracts, not implemented functions or provider endpoint names**.

| Business capability | Example system, if relevant | Proposed internal read/command | Authority / gate |
| --- | --- | --- | --- |
| Purchase/fulfilment | Existing OMS; Shopify as one example | `read_order`, `list_customer_orders`, `read_fulfilment` | Commerce identity and line ownership; least-privilege read credentials |
| Shipment evidence | Existing courier/aggregator; Shiprocket as one example | `read_tracking(order_id, shipment_id)` | Resolve shipment/AWB from authorized OMS mapping; validate carrier event/time |
| Reverse serviceability | Courier/aggregator | `check_reverse_serviceability(rma_id, address)` | Read availability for that address/item/parcel; not a booking |
| Pickup booking | Courier/aggregator | `request_reverse_pickup(approved_rma_id, command_id)` | Staff-approved request, eligibility, validated address and provider confirmation |
| Refund status | Existing gateway; Razorpay as one example | `read_refund_status(order_id, refund_id)` | Server resolves original payment/refund mapping; provider's actual state |
| Refund execution | Existing finance/payment workflow | `request_refund(approved_rma_id, command_id)` | Separate finance authority, original payment destination, amount cap and reconciliation |
| Helpdesk | Retailer's current support system | `create_case`, `read_case`, `assign_case` | Persist only authorized context; track write failure and human ownership |
| Inventory/exchange | Existing inventory/WMS | `read_variant_stock`, later `reserve_replacement` | A read is not a reservation; reservation needs a separate confirmed workflow |
| Identity | Existing account/verification service | `link_channel_account`, `verify_access` | Verifiable proof; channel sender and typed email alone are insufficient |
| Media | Private object storage | `store_evidence`, `read_authorized_evidence` | Account/RMA access, file controls, retention and audited access |

Shopify documents [order and fulfilment reads](https://shopify.dev/docs/api/admin-graphql/latest/queries/order). Shiprocket's [API reference](https://apidocs.shiprocket.in/?version=latest) includes tracking, return/pickup-related capabilities and tracking webhooks; its webhook setup describes an `x-api-key` security token. Razorpay provides a [refund-by-ID read](https://razorpay.com/docs/api/refunds/fetch-with-id/). These references support feasibility, not selected vendor compatibility or tested account permissions. Each adapter needs an explicit endpoint/version/field/error contract in the selected sandbox.

## Proposed read result contract

This envelope is a design for future adapters, **not the MVP's existing JSON response schema**:

```json
{
  "request_id": "synthetic-example",
  "outcome": "OK",
  "source_system": "selected-courier",
  "source_entity_id": "mapped-shipment-id",
  "fetched_at": "2026-11-07T12:00:00Z",
  "source_event_at": "2026-11-07T11:30:00Z",
  "source_version": "provider-version-if-available",
  "freshness": "current",
  "data": {"normalized_status": "in_transit", "eta_date": null}
}
```

Proposed outcomes include `OK`, `NOT_FOUND`, `FORBIDDEN`, `UNAVAILABLE`, `INVALID_SOURCE`, `STALE` and `CONFLICT`. Missing ETA stays null. Preserve raw provider status separately from the normalized status. Do not invent a version/event ID when the provider does not supply one. Financial adapters must declare currency/units and normalize rounding explicitly; the current MVP's simple full-item INR arithmetic is not a complete production refund calculator.

## Real-life scenario playbook

| Case | Evidence and workflow | Boundary |
| --- | --- | --- |
| Routine order tracking | **MVP:** owned current order and payment reads; **future:** mapped shipment read if extra detail is needed | Repeat the source's estimate as an estimate; no fabricated location or date |
| ETA passed | **MVP:** explain that the old estimate passed and offer investigation; **future:** courier exception read | No automatic new arrival promise |
| Split order | **MVP:** item statuses/dates and selection; **future:** separate package mappings | One parcel delivered does not mean every item arrived or every return window started |
| Courier says delivered; customer says missing | **Future:** courier event/POD access plus helpdesk dispute | “Carrier reports delivered at X; you report non-receipt.” Restrict POD/address access; do not blame the customer |
| Failed delivery/NDR | **Future:** authorized non-delivery evidence and supported staff action | Distinguish alleged attempt, customer explanation and confirmed reattempt; never invent a visit |
| PIN not serviceable for return | **Future:** reverse serviceability read | Keep the RMA and offer staff alternatives; no pickup confirmation from a syntactically valid PIN |
| Damage or tag removed | **MVP:** evidence/condition flag and staff review; **future:** retailer exception workflow | A standard-rule restriction is not an AI determination of the claim or customer rights |
| Pickup request times out | **Future:** command intent + provider lookup/reconciliation | Timeout means unknown, not necessarily failed. Do not create a second pickup blindly |
| Refund marked internally but gateway pending/failed | **Future:** mapped refund read and finance escalation | Report both states and references; no “money is in your bank” without supporting confirmation |
| Paid but no order | **Future:** original payment/commerce mapping reads | An unmatched payment needs reconciliation; a screenshot is not authorization to create/mark a paid order |
| Size before dispatch | **MVP:** owned order and enabled SKU-size read, exact preview and explicit confirmation | Same SKU, unchanged price/quantity; processing order/item only; configured range is not stock |
| Exchange size | **Future:** variant read, then separate staff/customer-approved exchange/reservation | Available stock can change. No confirmed replacement before reservation/order evidence |
| Address change after dispatch | **Future:** shipment state, carrier restrictions and authorized staff command | Identity, consent and external acceptance before claiming change |
| Cancellation request | **MVP:** handoff; **future:** OMS cancellation eligibility/read and approved command | No model-only cancellation or refund, especially once dispatched |
| Provider outage | **MVP:** source controls demonstrate refusal to guess; **future:** real timeout/circuit-breaker and queue handling | Rules fallback helps language routing, not unavailable business facts |

## Three useful presentation walkthroughs

**Tracking with conflicting evidence:** read purchase → map shipment → fetch courier event → show status and event time → detect conflict with OMS/customer report → save a case. The model can choose the tracking intent; it must not reconcile physical truth by speculation.

**A return from a remote PIN:** submit a pending request → check reverse serviceability → staff approves a viable option → persist booking intent → call provider → reconcile/confirm reference → notify with permitted WhatsApp format. RMA creation and pickup booking are different states.

**Refund follow-up:** read the owned return and original payment mapping → query the actual gateway refund → normalize its status → report verified state/reference → escalate mismatch. Inspection passed, refund requested, gateway processed and bank credit are different milestones.

The roadmap should add one narrowly scoped integration at a time. These scenarios make the architecture concrete; they are not additional features already working in the MVP.
