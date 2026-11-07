# 14 — Data ownership and synchronization

**Core principle:** current operational records supply facts; notifications announce changes; conversation history supplies context. These are three different responsibilities.

## Current data model

SQLite tables in [store.py](../backend/store.py) contain JSON records plus lookup keys:

| Table | Purpose / relationship |
| --- | --- |
| `customers` | Internal ID, display ID, normalized email/phone and synthetic profile |
| `orders` | Order ID → customer; item IDs, status/dates, price/quantity, currency, payment, policy version and revision |
| `sessions` | Random session ID → bound customer and workflow history, retained to the last 20 messages |
| `channel_sessions` | Same session → channel stage, selected order, messages, return draft and latest trace; ordinary handling trims channel history to 120 messages |
| `returns` | RMA → customer/order/item, quantity/value, condition/photos, pickup and lifecycle fields |
| `tickets` | Support request, deduplication key, request/transcript and available evidence |
| `media` | Opaque media token → uploading session and local file path |
| `traces` | Session → available inference, outcome, read/step and evidence record |
| `activity` | Mutable operator/customer event record, actor label and changes |
| `settings` | Fixed demo clock, policy and synthetic source/control configuration |

There is no production multi-tenant retailer boundary, document database or vector index. Records/list APIs are bounded for the small demo; `all_records` uses a 500-record limit and trace/ticket listing a 100-record limit. In particular, a scan-based `return_for_item` is not a production indexed return lookup. Source adapters and a production schema must remove such assumptions.

## Current authority

In this local demo, SQLite is the operational authority, including its synthetic payment and courier fields. `data/*.json` initializes/restores records. Editing a JSON fixture alone does not necessarily change an already-running saved record. Catalogue photo assets illustrate fictional garments; they are not condition evidence.

`demo_now` controls return/staff-hour rules and some demo delivery/booking behavior. Actual wall-clock timestamps also record reads, writes and messages. Explain that distinction in a demo; production must use trusted server/provider clocks rather than a classroom clock control.

## Staff order change → customer answer

```mermaid
sequenceDiagram
    participant U as ERP browser
    participant A as Operations API
    participant D as SQLite
    participant H as In-process hub
    participant C as Customer phone
    U->>A: PATCH with expected revision
    A->>D: BEGIN IMMEDIATE; compare revision; commit revision N+1
    A->>D: Record activity separately
    A->>H: Source changed
    H-->>U: Changed event; browser reloads current state
    H->>D: Read current owned order for eligible chat
    H-->>C: Persist/send source-backed update
    C->>A: Ask for latest status
    A->>D: Independent authorized current read
    A-->>C: Backend-rendered answer
```

The order UI supplies `revision`; conflicts return 409. Item-level changes derive aggregate fulfilment. A return staff edit can supply `updated_at`, and `transition_return` compares the stored prior record within a transaction. `create_return_once` prevents duplicate active requests for the same order/item through a database-locked check. A received/refunded return and its local order/payment projection commit atomically.

Version fields are optional at the API boundary, though normal UIs provide them. Do not describe the entire API as requiring optimistic concurrency from every client. Ticket deduplication uses a database uniqueness key; resolving a ticket releases the active-request key for later requests.

## What live sync does and does not guarantee

| Path | Implemented behavior | Limit |
| --- | --- | --- |
| ERP refresh | Workspace WebSocket invalidation, short debounce, current-state reload; reconnect/focus reload | In-process events are not a durable stream |
| Order push | Connected bound customer, verified stage, selected order; relevant status/ETA/carrier/tracking/item change; fresh read | Not queued for every offline customer; source failure suppresses the push |
| Return progress | Eligible selected-owner channel records receive a persisted update and socket emit after staff transition | No provider delivery guarantee or full agent-ownership coordination |
| Phone reconnect | Resume token retrieves saved channel state; stable IDs help retry messages | A missed order event may never have been saved to that offline conversation; later lookup reads current source |
| Business update | SQLite transactions protect defined revisions/return/payment changes | Business commit, activity row and notification are not universally one atomic unit |
| Model response | Available read evidence can identify revision N | A change may occur after read time; the answer is a snapshot, not a permanent guarantee |

An order commit can succeed just before a process crash and broadcast can be lost. The next source read is still able to return the saved state. Do not call this “exactly-once delivery,” “every customer always notified,” or production distributed consistency. Some notifications/read paths have different trace coverage; not every user-facing event has the same evidence envelope.

## Proposed production source ownership

| Domain fact | Primary authority to confirm | Other representations |
| --- | --- | --- |
| Purchase, item, price/discount/tax, fulfilment mapping | Existing commerce/OMS | Support projection and channel summary |
| Carrier scan, attempt or pickup event | Selected courier's evidence | Normalized shipment projection; customer dispute retained separately |
| Payment/refund processing | Payment provider and finance reconciliation | OMS/local payment projection |
| Garment receipt and inspection | Authorized warehouse/staff workflow | RMA state and customer-safe explanation |
| Policy | Approved versioned retailer policy owner | Structured evaluation fields, approved explanatory passages |
| Message delivery/read/failure | Channel provider callbacks | Conversation transport status |

Authority for one field does not grant permission to overwrite another domain. Courier “delivered” versus customer “not received” is a dispute to investigate, not a conflict to resolve with LLM confidence. Preserve original status, source ID, occurrence time, ingestion time, mapping and normalization version. Do not silently overwrite a newer meaningful event with a late older event.

## Proposed durable event pattern

1. Verify provider-specific signature/account scope and validate schema.
2. Store an inbox entry with provider/event identity and processing state. Enforce uniqueness and account isolation; acknowledge according to that provider's contract after durable intake.
3. Worker applies an allowed transition or records conflict. Use event/version semantics; time alone is not always a safe order. Fetch authoritative state when event order is uncertain.
4. Commit local projection and required outbound work to an outbox together.
5. Sender checks customer permissions, current facts, human takeover and WhatsApp message eligibility; sends and records provider ID/result.
6. Delivery callbacks update transport state. Retries/dead-letter handling and scheduled source reconciliation repair missed events.

Razorpay explicitly documents signature validation, duplicate event identifiers and potentially unordered webhooks in [its webhook guide](https://razorpay.com/docs/webhooks/validate-test/). Those provider properties motivate our proposed inbox/reconciliation design; they do not imply that every provider has the same headers or delivery behavior.

## External writes are not one database transaction

For pickup/refund, persist an authorized command intent and stable business key first. Record approver, amount/address, original payment/shipment and request fingerprint. Call the provider with its supported idempotency mechanism if available. Save the provider reference. If a timeout follows an accepted request, mark the outcome unknown and reconcile before retrying. A local idempotency key alone does not make an external provider idempotent.

No exactly-once guarantee is assumed across services. Reconciliation and staff exception handling are required. A new customer-visible “booked,” “cancelled” or gateway “processed” claim needs the corresponding confirmed evidence. [The production plan](15-production-plan-and-operations.md) sets rollout gates for these capabilities.
