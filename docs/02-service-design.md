# 02 · Service & experience design

**Early design rationale, not a current feature inventory.** The implemented v0.5 journey is in [document 10](10-grounded-india-returns.md); presentation content is in [the team briefing](PRESENTATION_BRIEF.md). See [the documentation map](README.md) for status definitions.

## Experience principle

**One reliable answer. One clear next step.**

The customer experience should be calm, brief, and specific. Keep operational evidence inspectable by the agent and evaluator; give customers only the facts and context that help them act.

## Three views with three distinct jobs

### Customer conversation

Mobile-first, familiar chat rhythm. Start with “Track an order”, “Check a return”, and “Talk to support”, plus a free-text field. Clearly introduce the automated assistant. Preserve the user's original question across verification.

Show a compact order card only after verification: order number, current status, last order-system check, carrier update time where relevant, and one action. “Checked just now” means the system was queried; a separate carrier-update timestamp reveals when the underlying delivery information last changed.

Avoid percentage confidence scores, model names, tool syntax, or dashboards in the customer's flow. For identity verification, use an existing authenticated session or a link/code delivered to an already registered contact. A demo selector must explicitly say **Simulated verified customer**.

### Live order console — classroom view

This is an evaluator control, separate from the customer experience. Select a synthetic order, change delivery status/ETA, simulate an API outage or lagging feed, and inspect saved state. Show a fixed demo date and an “API-backed synthetic system” label.

The console proves the answer follows the current record. It must persist changes through the backend, not change a canned response in the browser.

### Human handoff inbox

Show why a person is needed, the original request, verification state, relevant order and item facts, policy version, attempted steps, and a brief transcript. A handoff summary can be generated, but structured evidence remains authoritative.

Use readable categories such as **Delivery exception**, **Policy exception**, and **Order service unavailable**. Show queue status honestly. A ticket acknowledgement can promise a reply time only if the configured service commitment supports it.

## Customer journey and service blueprint

| Step | Customer sees / does | Service does | Failure or recovery |
| --- | --- | --- | --- |
| Arrive | Asks a question or selects an action | Identifies supported intent | Clarify once, then offer a person |
| Verify | Uses sign-in or a secure verification step | Binds session to customer | No purchase information before verification |
| Locate | Selects one owned order and, if needed, an item | Authorizes each lookup | Ambiguous order: present owned choices only |
| Check | Sees a short checking state | Reads order API; applies policy if relevant | Timeout/lag: explain uncertainty and offer handoff |
| Answer | Gets status or eligibility with next action | Renders validated facts | Missing ETA stays missing; no invented date |
| Continue | Opens tracking / existing returns portal | Uses trusted link from backend | Invalid or missing link: handoff |
| Escalate | Gets a ticket reference and queue state | Attaches evidence, suppresses duplicate ticket | Queue failure: say it failed; offer configured contact route |
| Close | Confirms usefulness or asks another question | Records outcome; allows reopening | User can request a person at every stage |

## Example conversations

Examples use the synthetic fixtures and a fixed demo time of **7 November 2026, 12:00 UTC**. They illustrate desired behavior; they are not model outputs.

**Routine tracking**

> Customer: Where's order 4812?
>
> Assistant, after verification: Order #4812 is in transit. The carrier estimates delivery on 9 November. Its latest update was 7 November at 10:30 UTC. [Track package]

If the console changes the record to “delivered”, the next answer must say “delivered” after a fresh read.

**Return eligibility**

> Customer: The shirt is too big. Can I send it back?
>
> Assistant: Which item would you like to return?
>
> Customer: The Everyday Oxford, order 4813. It's unworn with tags.
>
> Assistant, after checking: The Everyday Oxford meets the initial return conditions. Your request deadline is 24 November. Start the request in the returns portal; the retailer checks the item's condition. [Open returns portal]

The deadline and initial eligibility come from backend rules using the policy bound to that purchase. A customer statement about condition is not an inspection or a refund approval.

**Outside the window**

> Assistant: The standard return request deadline for this item was 31 October. I can ask support to review your request. [Ask support to review]

**No current information**

> Assistant: I can't check your order right now because the order service is unavailable. I can pass your question to support. [Contact support]

**ETA already passed**

> Assistant: The carrier's last delivery estimate has passed, and no newer estimate is available. I can ask support to investigate. [Contact support]

**Another customer's order**

> Assistant: I couldn't find an accessible order with those details. Check the number or contact support.

Use the same generic response for nonexistent and unauthorized order numbers, so the reply does not reveal whether another customer's purchase exists.

## Design direction

Working identity: **Threadline**. Editorial apparel-service aesthetic: warm ivory, dark ink, muted forest green, fine rules, generous whitespace. Pair a restrained serif headline with a readable sans-serif body. Keep text contrast and visible keyboard focus; pair all status colors with words. Respect reduced-motion preferences.

Desktop: customer conversation is the primary panel, order console is an explicitly labeled evaluator panel, and handoff is a separate view. Mobile: stack or switch views; never shrink three desktop panels into unreadable columns. Use 44px minimum practical touch targets, clear labels, and polite announcements for asynchronous replies.

## States to design before coding

Unauthenticated; verification pending/failed/expired; multiple owned orders; ambiguous item; checking; current answer; carrier data lagging; no ETA; partially delivered; eligible pending condition; outside window; final sale; damaged-item exception; API unavailable; handoff creating/created/failed; after-hours queue; and user-requested human support.

For an after-hours exception, acknowledge the queue and show the next staffed period in the configured business timezone. The automated service can respond after hours; human resolution still depends on staffing.
