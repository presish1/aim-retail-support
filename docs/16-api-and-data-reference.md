# 16 — Actual API, protocol and data reference

**Local MVP v0.5.** Routes below exist in [app.py](../backend/app.py), [erp.py](../backend/erp.py) and [media.py](../backend/media.py). They are not the future Meta/courier/gateway endpoints. The application version and tool/record schemas are visible in source; generated FastAPI schema is available locally at `/openapi.json`.

## Boundary conventions

- Normal frontend requests use the same origin; Vite proxies `/api` to port 8000 in development.
- `X-Demo-Admin` carries the local evaluator capability for staff routes. `/api/studio/bootstrap` returns it without real staff authentication. Do not deploy this as a production security mechanism.
- `X-Demo-Session` identifies a stored synthetic customer session for legacy HTTP and photo upload. Server binding supplies customer identity; it is not accepted from model arguments.
- Relevant browser origin checks accept loopback hosts; `/api` HTTP responses use `Cache-Control: no-store`. This is not a complete authentication/CSRF/security perimeter.
- Most HTTP validation failures use FastAPI `detail`; source GET failures use a `detail` object with code/message. Workflow `/api/chat` returns an outcome object, including failures, rather than one universal HTTP error envelope.

## Implemented route inventory

| Method/path | Boundary and result |
| --- | --- |
| `GET /api/health` | Local health, synthetic clock and configured model readiness; not a source/provider end-to-end health guarantee |
| `POST /api/session` | Legacy synthetic persona selection (`a`, `b`, `guest`); not real sign-in |
| `GET /api/orders` | Session's owned validated minimal order choices; simulated customer required |
| `GET /api/orders/{order_id}` | Session-owned validated current order; 404 for inaccessible and 503 for other source failure categories |
| `POST /api/chat` | Legacy session workflow: message + `model`/`baseline`; one in-flight request per local session lock |
| `GET /api/traces` | Session-scoped stored traces; not intended as a public production evidence API |
| `WS /api/whatsapp/ws` | Browser customer transport with loopback-origin check and resume/session events |
| `POST /api/whatsapp/photo` | Bound channel/session at photo step; raw JPEG/PNG/WebP body; returns local media reference |
| `GET /api/media/{token}` | Opaque local media capability; no per-view customer/staff login check |
| `GET /api/studio/bootstrap` | Local demo capability bootstrap |
| `GET /api/studio/state` | Admin capability; current workspace records/catalogue/settings; not the customer projection |
| `WS /api/studio/ws` | Loopback origin + initial admin capability; change invalidation events |
| `GET /api/studio/whatsapp` | Admin plus channel session header; evaluator code inbox |
| `POST /api/studio/customers` | Admin; validated synthetic profile creation, unique contact fields |
| `PATCH /api/studio/customers/{customer_id}` | Admin; profile edit and contact normalization |
| `POST /api/studio/orders` | Admin; existing customer/catalogue items, calculated INR total |
| `PATCH /api/studio/orders/{order_id}` | Admin; order/line fulfilment fields and optional expected revision; returns saved order |
| `POST /api/studio/returns` | Admin; delivered item, quantity/value and duplicate checks |
| `PATCH /api/studio/returns/{return_id}` | Admin; allowed lifecycle transition, optional expected update time and required booking/refund/decline fields |
| `PATCH /api/studio/tickets/{ticket_id}` | Admin; status, assignee and internal note |
| `GET /api/studio/conversations/{reference}` | Admin; history, latest trace and optional demo code |
| `POST /api/studio/conversations/{reference}/reset` | Admin; remove that channel and signal reset |
| `PATCH /api/studio/controls` | Admin; synthetic source, verification and inference controls |
| `POST /api/studio/reset` | Admin; restore samples and clear subsequent local demo records; not a production operation |

## Browser WebSocket protocol

Illustrative initial client message, matching the actual protocol:

```json
{"type": "resume", "session_id": null}
```

The server replies with `type: session`, random `session_id`, stage, public messages, matched first name if available and selected order. The client then sends:

```json
{"type": "message", "id": "stable-client-request-id", "text": "Track order #4812"}
```

The event ID must be 8–80 characters; text is 1–2,000 nonblank characters. Optional mode is `model` or `baseline`; normal UI relies on the server setting. Client events also include `reset` and `ping`. Server events include `session`, `ack`, `typing`, `message`, `source_changed`, `error`, `reset_required` and `pong`.

Customer messages can contain backend-created `actions`, a `product`, a return `receipt` or `media`, depending on the path. Traces and demo codes are excluded from the phone's public snapshot/message event. The staff socket instead receives an initial `{ "key": "demo-capability" }`, then `ready`/`changed` events; the browser reloads state. These sockets do not implement Meta webhooks or provider delivery receipts.

## Core records and states

| Object | Important fields / states |
| --- | --- |
| Customer | `customer_id`, display ID, first/last name, email, phone, city; local normalization adds `+91` to ten-digit numbers |
| Order | Owner, policy version, item lines, status, carrier/estimate/reference, ordered/update times, currency `INR`, total, payment state and revision |
| Item | ID, SKU/name, variant/image, quantity/unit price, status, delivered time, final-sale and returned flags |
| Order status | `processing`, `in_transit`, `partially_delivered`, `delivered`, `cancelled`, `returned` |
| Payment state | `paid`, `pending`, `partially_refunded`, `refunded`; local ledger, not confirmed gateway state |
| Channel stage | `contact`, `code`, `choose_order`, `verified`; “verified” is the code's stage label, not a production authentication claim |
| Return draft step | Item, reason, condition, tags, photos, optional quantity, address, window, confirm |
| RMA | Owner/order/item, quantity/reason/value, condition/tags/photos, address/preference, policy/revision evidence and status |
| RMA status | `requested`, `approved`, `pickup_scheduled`, `received`, `refunded`, `declined`; allowed transition table in `erp.py` |
| Ticket | Saved customer request/transcript, reason, order if known, available evidence, status/assignee and queue message |
| Trace | Mode/model/provider metadata, steps, usage, outcome, latency and available source/read evidence; path-dependent fields |

Current supported explicit order IDs use a four-digit parser; do not reuse this assumption for a retailer with arbitrary/long IDs. Schema validation is tailored to this demo. Real order totals may need discounts, shipping, tax and rounding fields rather than the current “sum of item prices” check.

## Defined failure categories

Customer reads can produce `VERIFICATION_REQUIRED`, `INACCESSIBLE_ORDER`, `ORDER_SERVICE_UNAVAILABLE`, `ORDER_DATA_LAGGING`, `ORDER_DATA_INVALID`, `ORDER_CHANGED`, `POLICY_UNAVAILABLE` or `RETURN_DATA_INVALID`. Workflow outcomes additionally describe choices, status, eligibility, handoff creation and ticket write failure. See the actual branches in [service.py](../backend/service.py); do not assume every internal error category uses the same transport/status code.

## Configuration and storage

| Setting | Meaning |
| --- | --- |
| `THREADLINE_MODEL` | Default `qwen3:8b` |
| `THREADLINE_MODEL_PROVIDER` | Default `ollama`; optional `compatible` chat-completions adapter |
| `THREADLINE_MODEL_URL` | Default local Ollama URL; compatible endpoint configured separately |
| `THREADLINE_MODEL_API_KEY` | Optional backend-only endpoint secret; never frontend/Git/prompt |
| `THREADLINE_MODEL_REGION` | Descriptive operator metadata, not technical proof of processing location |
| `THREADLINE_DB` | Optional local SQLite path; default `artifacts/local/threadline.db` |
| `demo_now` / business timezone | Fixed rules clock / `Asia/Kolkata` |
| `verification_mode` | `demo_match` or optional local `code` |
| `inference_mode` | `model` or `baseline`; actual fallback is separately recorded |
| Source controls | Order API available, feed healthy/lagging, ticket store available |

The policy fixture is [`data/return-policy.json`](../data/return-policy.json). Photo files live beside the DB in `return-photos`; they are outside Git. Secrets and local runtime artifacts are ignored. Ignoring a file in Git is not encryption or a retention/access-control policy.

The future normalized provider envelope and business tool names in [document 13](13-business-tools-and-scenarios.md) are proposals. None of those placeholder contracts should be mistaken for an existing endpoint here.
