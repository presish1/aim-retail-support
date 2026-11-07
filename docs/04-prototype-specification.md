# 04 · Prototype specification

**Original build plan.** This page records early intended scope, not a current implementation checklist. Use [the system guide](../SYSTEM_GUIDE.md), [current architecture](03-architecture.md) and [evidence register](17-evidence-and-faq.md) for present-tense claims.

## What this prototype needs to prove

**A small language model can help route real customer language into controlled tools, while current operational records determine the answer.**

The prototype demonstrates integration feasibility and bounded service behavior. It does not establish production reliability, authenticate real customers, or prove financial benefits without a pilot.

## Minimum build

| Component | Required behavior | Evidence |
| --- | --- | --- |
| Customer chat | Preset intents and natural language; simulated verified identity; owned order/item selection | Customer-facing flow and verification boundary |
| Order API + database | Persist six synthetic orders; authorized reads and separate demo updates | Network trace and changed saved record |
| Intent / tool layer | Real LLM adapter and a separately labeled menu/rules baseline | Model ID, mode, tool proposals, actual tool calls |
| Returns rules | Versioned policy, item delivery dates, condition checks, explicit boundary | Deadline and reason reproduce from fixtures |
| Response renderer | Transactional facts supplied through templates | Answer values match source evidence |
| Handoff | Persistent local tickets with verified context and duplicate prevention | Ticket appears in inbox with reference |
| Failure controls | API outage, lagging feed, no ETA, model failure | Appropriate uncertainty / recovery |
| Evaluation trace | Redacted evidence, latency, tokens and outcome per case | Reproducible results for comparison |

Import the JSON fixtures into SQLite once, then read through the API. Reloading a JSON constant on the chat page is not the live-system demonstration.

## Recommended construction order

1. **Walking skeleton:** select a simulated customer, fetch an owned order through the backend, render current facts, and update the order from the separate console. Verify changed answers and denied cross-customer access.
2. **Rules and recovery:** implement the return policy, deadlines, outage handling, and persistent handoff. Exercise exact deadline boundaries.
3. **Real model:** connect one approved endpoint to intent/tool selection. Keep all permissions and transactional rendering unchanged. Display mode honestly; canned replies never count as LLM results.
4. **Comparison and polish:** add the deterministic baseline, run the same scenarios for both modes, inspect failed cases, and refine the three views for demo clarity.
5. **Evidence pack:** export measured results, capture screenshots and a short backup recording, and prepare the presentation team's handoff.

If inference is unavailable, the deterministic mode remains a useful integration demo. Label the limitation explicitly and do not claim the LLM hypothesis has been tested.

## Acceptance criteria

- [ ] Before verification, the customer sees no private order or ownership information.
- [ ] Order 4812 is read through the API and rendered with its source timestamps.
- [ ] Change 4812 to delivered through the console; the next request shows delivered.
- [ ] Turn the order API off; the previous status is never reused as current.
- [ ] Known carrier-feed lag produces uncertainty, even when the API itself responds.
- [ ] The 4813 deadline is 24 November under policy `demo-returns-v1` and the fixed clock.
- [ ] Order 4814 is outside the ordinary window; 4815 is final sale; damage is routed for review.
- [ ] Order 4816 evaluates each delivered item separately; an undelivered item gets no invented delivery date.
- [ ] Customer A cannot discover or read customer B's 4901 record by typing the number.
- [ ] A repeated escalation reuses an active ticket rather than creating duplicate work.
- [ ] A failed ticket write is reported honestly without a made-up ticket reference.
- [ ] Both modes run the same evaluation inputs; real model ID, endpoint region verification status, latency, tokens, and failures are recorded.

## Five-minute classroom demonstration

| Time | Show | What it proves |
| --- | --- | --- |
| 0:00–0:35 | The owner problem and three views; synthetic mode and fixed date | Business framing and transparent scope |
| 0:35–1:30 | Ask about 4812; inspect API evidence; change status; ask again | Live data drives the reply |
| 1:30–2:20 | Ask in natural language about the oversized shirt in 4813 | Intent understanding and deterministic return calculation |
| 2:20–3:05 | Ask for a window exception or damaged item | Bounded automation and helpful escalation |
| 3:05–3:45 | Disable the API; attempt another customer's order | Honest failure and access boundary |
| 3:45–4:20 | Open the created ticket and attached context | Human operational fit |
| 4:20–5:00 | Show measured baseline/model comparison and cost sensitivity | Owner recommendation grounded in evidence |

The final segment remains a placeholder until evaluation is actually run. Retain the fixed demo date in every recording; return eligibility otherwise changes as time passes.

## Keep the implementation small

Use one application service, one local database, an API boundary for operational data, and a replaceable model adapter. Integrate the actual ERP, real verification, WhatsApp, and helpdesk during a pilot only after the owner confirms their systems. At this scale, integration quality and operating discipline deserve more attention than an elaborate autonomous-agent framework.
