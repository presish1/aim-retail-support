# 15 — From MVP to a supervised pilot

**This is a proposed plan, not implemented infrastructure or a production launch commitment.** For the current presentation, the deliverable is an MVP feasibility demonstration and a conditional management recommendation.

## What to establish before choosing products

| Discovery question | Why it changes the design |
| --- | --- |
| Which commerce/ERP, courier/aggregator, gateway and helpdesk are already used? | Prefer their supported APIs/workflows rather than invent a parallel business ledger |
| Are 400 queries distinct cases or individual messages; what are peaks and languages? | Average daily volume is not peak model concurrency or staffing load |
| How are guest checkout, shared numbers and changed contacts verified? | Determines purchase access and account recovery |
| Which policy version applies; how do discounts, tax, fees, COD and partial returns work? | The demo's full-item arithmetic is insufficient for production finance |
| Who can approve an exception, booking, address change, cancellation or refund? | Must become staff permissions and approval records |
| Which source events/identifiers exist, and how reliable are they? | Determines mapping, freshness, conflict handling and reconciliation |
| What data handling, retention, processing region and budget are approved? | Determines provider/hosting/storage choices; no legal compliance claim is assumed |
| Does the current helpdesk already provide the needed automation? | Integration/configuration may be better than building a new operating UI |

## Staged scope and exit evidence

| Stage | Scope | Exit evidence / decision |
| --- | --- | --- |
| 0. Current MVP | Synthetic records, model/rules routing, current reads, return workflow, local ERP | Repeatable demo and defined test results; no real customer deployment |
| 1. Discovery and contracts | Name source/policy/security owners; map IDs, fields, events, errors and permissions | Signed-off architecture assumptions, source access and baseline measures |
| 2. Secure read-only shadow | Real identity/staff auth, OMS reads, private media/logging controls, source validation; replies internal | Ownership tests, source reconciliation, security review and held-out intent/item evaluation |
| 3. WhatsApp sandbox | Verified provider ingress, outbound mapping/templates, media, consent/window state and human takeover | Provider contract, duplicate/out-of-order/failure/restart tests pass |
| 4. Limited customer pilot | Narrow status/eligibility scope; reliable queue, staffed escalation and daily review | Owner-approved quality/cost/latency thresholds met; no critical disclosure/action/fabrication incidents |
| 5. Additional read adapters | Courier tracking, refund status or inventory where measured gaps justify them | Correct mapping/freshness/conflict behavior; support benefit demonstrated |
| 6. Supervised external writes | Approved pickup/refund commands with limits, original destination and reconciliation | Sandbox + failure tests, finance/support approval and recoverable unknown outcomes |

Do not quote dates before access, deadline and team capacity are confirmed. Do not enable real payments merely because the MVP can record a refund reference. Shadow mode and human takeover are proposed capabilities to build, not existing feature toggles.

## Production controls to implement

Keep the application modular initially. Use authenticated HTTPS ingress, genuine staff/customer identity, scoped adapter credentials, private media storage, managed durable state/work delivery, secret storage, backups and observability. Replace/remove the public demo bootstrap, persona endpoint, evaluator code inbox and reset/failure controls from real customer deployments.

A relational database such as managed PostgreSQL and a durable queue/outbox are options; a specific vendor, Redis or Kubernetes is not required by this proposal. Multiple workers need shared conversation coordination and event distribution. The current SQLite/in-process hub is not evidence of multi-instance readiness.

Agree timeouts, payload limits, retry budgets, backoff, provider rate limits, concurrency and circuit-breaker behavior for each adapter. Retry safe reads deliberately; reconcile uncertain writes before retrying. Separate source outage, model outage, queue delay and outbound delivery failure in the operating interface.

Protect histories, traces, addresses and images according to approved policy. Define retention/deletion including abandoned drafts, media files, replicas and backups. Add verified audit actors, access reviews and secure exports. This document is an engineering plan, not a jurisdiction-specific compliance assessment.

## Operational ownership

| Owner role | Responsibility |
| --- | --- |
| Retail/business owner | Approve scope, budget, risk limits and expand/stop decisions |
| Support lead | Review exceptions, staffing capacity, human takeover and customer outcomes |
| Integration engineer | Source contracts, IDs, webhook verification, reconciliation and recovery |
| Warehouse/returns lead | Receipt/inspection evidence, condition exceptions and stock disposition |
| Finance owner | Refund amount/destination rules, approval and provider/ledger reconciliation |
| Security/data owner | Identity/permissions, secrets, data access/retention and incident response |
| Model/evaluation owner | Unseen test set, routing/ambiguity performance, prompt/model changes and regression review |

These are responsibilities to assign, not additional employees automatically required.

## Metrics and decision gates

Measure correct intent/order/item outcome, source-to-answer factual matching, private-data access failures, unauthorized actions, useful-answer latency, source freshness, notification delivery, unresolved/reopened cases, staff handling time and total cost. Review confidence/ambiguity behavior through examples; the MVP has no calibrated model confidence score.

Use a held-out multi-turn set separate from development/test prompts. Compare model and rules on the same records, clock, supported scope and failure conditions. Record fallback separately so model failure is not counted as successful model inference. Run provider sandbox and peak-load/restart tests separately from language evaluation.

Proposed targets in [the evaluation plan](06-evaluation-and-handoff.md) are design inputs, not measured results or assignment requirements. A single verified disclosure, unauthorized commercial action, fabricated fact or duplicate external payment is a release blocker. Daily supervision and notification/source failure alerts must exist before relying on them.

## Economics without invented savings

Use an owner-approved INR budget; obtain dated vendor quotes and document currency conversion if a provider bills in another currency. No current tariff or exchange rate is asserted here.

`monthly cost = channel charges + inference usage + hosting/storage/workers + integration/support effort + supervision/security + exception handling`

`capacity value = verified minutes avoided per resolved case × eligible case count × productive-time value`

Track query, message and resolved-case counts separately. A return can require many messages but no model calls for its fixed questions. Four hundred queries/day does not establish how many tokens, messages or concurrent requests occur. Capacity freed may improve response times without reducing payroll; cash savings require an actual staffing/expense change. The older business-case arithmetic remains illustrative.

## Incident and rollback plan — proposed

Detect → pause the affected automation → route to people → preserve evidence → determine source/identity/model/rule/transport cause → reconcile external actions → repair and regression-test → obtain owner approval to resume. Pause model routing separately from source-backed deterministic reads when appropriate; a model fallback cannot repair an unreliable source.

For recovery exercises test lost webhooks, duplicate events, accepted-but-timed-out refunds, incorrect mapping, leaked/revoked credentials, unavailable media, queue backlog, restore from backup and agent takeover. Agree RTO/RPO, alert thresholds and staffed escalation before launch rather than invent numerical commitments in the presentation.
