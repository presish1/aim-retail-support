# 01 · Project definition

## Owner recommendation

Pilot a supervised post-purchase support service for routine order tracking and return questions. Connect it to the existing order system, measure whether natural-language understanding improves on a menu-and-rules workflow, and expand only after the service demonstrates reliable answers and useful economics.

The management decision is **where automation can safely remove waiting and repetitive work**. Model selection supports that decision.

## What we know, and what we are assuming

| Input | Status | Design implication |
| --- | --- | --- |
| D2C apparel retailer; 400 queries/day | Assignment fact | Design for repetitive post-purchase support |
| Order status and returns dominate | Assignment fact; exact mix unspecified | Prioritize two intents; do not invent their percentage |
| Answers must use a live order system | Assignment requirement | Each order-specific answer needs a fresh authorized read |
| Actionable advice for an owner, demonstrated by a prototype | Assignment requirement | Show feasibility, costs, tradeoffs, and operating ownership |
| India store; INR; WhatsApp; detailed customer replies | User product decisions after the draft | Supersede the draft's US locale; use Asia/Kolkata and INR |
| English; median 20-word incoming message | Draft assumptions | English-first channel adapter; message length unmeasured |
| Five agents; Mon–Sat 09:00–18:00 | Draft assumption; business timezone unknown | Queue design and explicit after-hours state |
| First response usually 14–20 hours; peaks 48 hours | Draft estimate, unmeasured | Validate with ticket timestamps before claiming improvement |
| 25% follow-ups; 35% outside business hours | Draft estimates | Measure cases and messages separately; percentages can overlap |
| 45 normal / 55 peak agent-hours daily | Draft estimate | Validate handle times; scheduled hours differ from productive capacity |
| Cost sensitivity and earlier open-weight preference | Early draft; provider choice superseded by Gemini | Evaluate cost/portability; use document 19 for the current provider |
| Return window, ERP vendor, available API, identity flow | Unknown | Use labeled demo assumptions; verify before production |

The supplied report is a preliminary team draft. Its figures are inputs to investigate, not additional instructor requirements. Personal names, student IDs, and the original attachment are not needed in the public design package.

## Design insight

A customer asking “Where is my order?” wants certainty and a next step. The retailer's bottleneck is repeated access to operational information. A fluent answer with an outdated delivery date fails this job. A short answer with a current status, a clearly labeled estimate, and a useful action succeeds.

## People and jobs to be done

| Person | Job | What success feels like |
| --- | --- | --- |
| Customer waiting for a parcel | Know what is happening and what to do next | “I know the current status and whether I need help.” |
| Customer returning apparel | Know whether this item qualifies and start the correct process | “I understand the rule and my next step.” |
| Support agent | Resolve exceptions without repeating identity and order questions | “The facts and attempted steps are already here.” |
| Retail owner / support lead | Improve service without unpredictable expense or unmanaged risk | “I can see quality, workload, costs, and when to stop.” |

## Three ideas considered

| Direction | Value | Weakness | Decision |
| --- | --- | --- | --- |
| Agent copilot | Drafts replies after a lookup; person reviews | Customers still wait when nobody is working | Useful pilot mode and fallback |
| Customer order & returns concierge | Immediate verified answers for routine requests; exceptions go to staff | Requires reliable integration and identity controls | **Recommended concept** |
| Proactive delivery companion | Sends updates before customers ask | Adds outbound messaging, consent, and notification complexity | Later experiment after inbound evidence |

An order-status menu with deterministic rules is the comparison baseline. If it matches customer success at lower total cost, recommend that narrower solution; the class project should demonstrate the model's incremental contribution through paraphrases, ambiguous intent, and multi-turn clarification.

## Scope

**First prototype:** current order status, carrier-provided ETA when available, item-level return eligibility, explanation of the relevant policy, customer-requested handoff, and system-failure handoff.

**Subsequent pilot options:** agent-assisted return requests and measured after-hours coverage.

**Deferred:** issuing refunds, changing addresses, cancelling purchases, approving policy exceptions, generating real shipping labels, recommendations, voice, multilingual service, and proactive campaigns.

## Hypotheses to test

These are proposed hypotheses, not results or promises.

1. For supported, verified order-status questions, median useful-answer time is at least 50% lower than the measured manual baseline, with no increase in incorrect factual claims.
2. On paraphrased and mixed-intent questions, the LLM workflow improves end-to-end task success by at least 10 percentage points over the menu/rules baseline, while keeping the agreed cost ceiling.
3. Among cases automated during the pilot, at least 50% are resolved without a human reply **and without reopening within 48 hours**.
4. Handoffs with attached context reduce median exception handling time by at least 20% against comparable manual cases.

A useful-answer timer stops when the customer receives the requested fact or an appropriate next action. A greeting or “checking” message does not qualify. An honest outage response is appropriate failure handling, not a successful status resolution.

## Fixes to make in the draft

- Replace “ask for order number or phone number” with “identify the order, then verify that the customer can access it.” A typed phone number proves nothing about ownership.
- Explain that open weights improve portability but do not remove hosting, integration, or operations dependence.
- Evaluate the selected processing region at the **deployment/provider level**. The current store is in India; model choice alone does not establish a data boundary.
- Separate monthly messages, unique cases, model calls, and resolved cases before costing.
- Five people × nine hours gives 45 scheduled person-hours. Breaks, meetings, and occupancy affect productive capacity. The implied 6.75 minutes per query from 45 hours / 400 queries is a consistency check, not a measured handle time.
- Treat additional evening/weekend staffing as a costed alternative. The draft's assertion that hiring cannot address after-hours service is too strong; scheduling can change coverage.
- Correct the sample delivery response: use coherent dates, make carrier ETA an estimate, and never present a stale ETA as a promise.

## Questions to settle during implementation discovery

Which system is the order source of truth? Can it provide fresh data, ownership binding, item details, delivery timestamps, and authenticated return links? Which return policy applies to each purchase? What are the actual channel and business timezone? Which hosted inference terms and processing location are acceptable? What monthly spending ceiling and escalation response commitment can the owner support? Does the full assignment rubric add requirements beyond the supplied scenario image?
