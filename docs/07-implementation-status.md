# 07 · Implementation status — v0.2

Built and checked locally on 7 November 2026. The design documents remain the rationale; this page records the implemented scope.

## Actual model

**Qwen3-8B through Ollama**, tag `qwen3:8b`, downloaded model ID prefix `500a1f067a9f`, Q4-sized download approximately 5.2 GB. The adapter sends `think: false`, temperature 0, a 4,096-token context limit, and a 180-token output limit for a single bounded tool-selection call. Source: [Qwen model card](https://huggingface.co/Qwen/Qwen3-8B), [Ollama tool calling](https://docs.ollama.com/capabilities/tool-calling), [Ollama thinking controls](https://docs.ollama.com/capabilities/thinking).

It recognizes intent and proposes a tool. Transactional responses use backend templates populated from current records and deterministic eligibility rules. The interface identifies actual model mode, baseline mode, and explicit fallback. It never labels canned responses as model inference.

This is an implementation choice for a synthetic local demonstration, not the final vendor/deployment recommendation. Local inference does not establish US processing for a future retailer pilot. An environment-configured compatible API adapter is included but has not been tested against a hosted provider in this version.

## What works

- Responsive customer desk, separate order console, and agent inbox.
- Synthetic customer sessions with per-tool ownership checks; unverified and cross-customer requests are denied.
- Current reads from persistent SQLite; separately authorized console updates affect the next answer.
- Item-level return rules, policy-version checks, condition clarification, inclusive local-time deadlines, final-sale restrictions, and exception review.
- Known feed-lag and source-outage responses that do not reuse earlier facts as current.
- Persistent deduplicated tickets with transcript, available evidence, source-failure reason, and a staffed-hours queue message.
- Failure toggles for order availability, carrier feed, and ticket storage.
- Inspectable model/tool proposals, evidence, elapsed time, token usage, actual mode, and fallback notes.
- A deterministic baseline using the same tools, rules, and response templates.

The implemented model tools are `get_order_status`, `check_return_eligibility`, `create_support_ticket`, and `list_my_orders`. Applicable policy information is returned with eligibility; there is no separate model-callable policy tool yet. The order API and support workflow share one application service and database, rather than requiring an additional network service or ERP installation.

## Verification evidence

**29 backend tests pass.** They cover changed source data, stale-history avoidance during an outage, cross-customer denial, no private facts before verification, return conditions, local-time deadline boundaries, partial delivery, policy mismatch, final sale, damaged-item escalation, failed ticket writes, persistent/concurrent deduplication, after-hours queues, explicit model failure, console permissions, and blocked cross-origin writes.

**12 focused integration scenarios pass in model mode, and the same 12 pass in baseline mode.** Each has one authored input, one run, a fresh synthetic database, and a fixed demo clock. The recorded [JSON results](../evaluation/results/local-qwen3-smoke.json) retain each input, proposed tool, reply, outcome, timing, and usage. This is a development smoke check, not a held-out or statistical benchmark. It does not demonstrate the model's incremental business value.

The first development run exposed a noncanonical item argument: Qwen sometimes supplied “Oxford” rather than an item ID. The backend now discards noncanonical labels and resolves the customer's words against owned items, with clarification when ambiguous. Generic access denial is also applied independently of whether the model proposes a lookup or refuses the request. Dedicated tests cover both changes.

Browser checks use genuine model calls and include tracking, a saved status change followed by a changed answer, a return-condition question and follow-up, an order-system outage, persisted handoff into the inbox, and mobile layouts. The build passes TypeScript and Vite production compilation. Local warm response times are recorded per smoke run; cold starts, long conversations, concurrent use, and production p95 latency need separate measurement.

## Limits and next work

The simulated customer selector and locally obtainable evaluator capability are classroom controls, not real authentication. The server binds to loopback. A future hosted release must replace those controls and connect the actual retailer systems.

No real WhatsApp integration, retailer ERP, return portal, label generation, commercial write action, or refund approval is connected. Eligible customers can ask staff to start a return; the prototype creates a support ticket rather than presenting a nonworking portal link. Policy, staffing schedule, customers, and orders remain illustrative.

The 30 scenarios in `scenarios.csv` remain a broader planned evaluation inventory. Create a separate held-out set of paraphrases and multi-turn conversations, evaluate model versus baseline, quantify operating cost and uncertainty, and collect the final slide evidence. Production readiness, model superiority, and financial savings have not been established by these local checks.
