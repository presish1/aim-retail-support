# 06 · Evaluation, rollout & presentation handoff

## Evaluation design

The repository includes **30 planned scenario seeds**, not executed tests or results. Use them to build a small development set, then create a separate held-out set of customer-style paraphrases and multi-turn conversations. Keep the final holdout unseen while adjusting prompts.

For a classroom comparison, run each held-out scenario at least three times per model with the same fixtures, clock, policy, identity state, and failure settings. Record outcomes per run; do not imply repeated runs are independent customers. Randomize order when measuring latency. A 30-scenario suite can expose failures but cannot establish a production error rate.

Test both **tool selection alone** and the **complete workflow**. Template rendering can prevent some factual inventions without proving the model understood the right order or item.

| Measure | Definition | Proposed classroom gate |
| --- | --- | --- |
| End-to-end task success | Correct supported outcome or appropriate escalation, with the right order/item | At least 90% on the declared held-out set; report denominator |
| Factual integrity | All transactional claims match source evidence and applicable policy | Zero fabricated transactional facts in the evaluated set |
| Authorization | No private disclosure or action across customer boundaries | All access-boundary scenarios pass |
| Failure behavior | Correct handling of outages, lagging data, malformed tool calls, failed tickets | Every critical failure scenario passes |
| Useful-answer latency | Time from user submission to a useful fact / appropriate action | Proposed p95 ≤ 5 seconds for verified routine requests under test conditions |
| Handoff usefulness | Ticket has original request, identity state, facts, reason, and attempted steps | All created tickets complete and truthful |
| Incremental model value | Task-success difference on paraphrase/ambiguity subset vs baseline | Evaluate the 10 percentage-point hypothesis; show raw results |
| Cost | Actual inference usage plus estimated channel/operations | Below owner-approved ceiling; ceiling still to be agreed |

Treat fabricated facts, unauthorized disclosure, and unauthorized actions as release blockers. Proposed thresholds are team design choices, not instructor requirements or evidence of performance. Statistical uncertainty, dataset limitations, and untested conditions should accompany results.

## Required result record

For each run, store scenario ID, mode/model and revision, provider/region verification status, prompt/tool-schema version, synthetic customer, demo clock, input, expected outcome, proposed tool and arguments, executed tool trace, source evidence, final reply, outcome, elapsed time, billable tokens, cost basis, and reviewer notes. Redact secrets and real personal information.

Evaluate case resolution in a real pilot with a 48-hour reopen window. A successful automatic greeting, a handoff, and a resolved case are three different events.

## Rollout recommendation

| Stage | Scope | Owner | Exit condition |
| --- | --- | --- | --- |
| Discover | Verify traffic, source systems, policy, staffing, channel and budget | Business owner + support lead | Agreed baseline and integration access |
| Prototype | Synthetic data, real database/API, one model, baseline, failure paths | Prototype lead | Critical acceptance checks pass; measured comparison available |
| Shadow | Read real approved cases; responses remain internal for agent review | Support lead + integration owner | Correctness, region/data handling, and operating ownership confirmed |
| Limited pilot | Small share of eligible traffic; human escalation and daily review | Support lead | Quality, sustained resolution, cost, and customer outcomes meet agreed gates |
| Expand or stop | Increase only supported intents; retain kill switch | Business owner | Explicit decision based on measured evidence |

An illustrative schedule is five to seven focused prototype work sessions plus pilot discovery; confirm against the actual deadline and team availability. Do not present a production launch date before access and integration constraints are known.

During the pilot, stop automatic answers after any verified private-data disclosure, unauthorized commercial action, or fabricated transactional claim. Use deterministic/unavailable responses or agent review until the issue is understood. Escalation capacity must be checked before increasing traffic.

## What the presentation team should receive after the prototype

| Presentation point | Evidence to capture |
| --- | --- |
| Why the owner should care | Confirmed query volume, useful-answer baseline, case/message definitions |
| Why this concept | Three alternatives and the chosen scope |
| Why the architecture fits Scenario A | Simple architecture diagram and live API request evidence |
| Why AI adds value | Identical paraphrase/ambiguity cases across baseline and model modes |
| Why customers can trust it | Status changed in the source and answer changed; outage produced uncertainty |
| How humans stay involved | Persisted handoff with context and explicit exception reason |
| Whether economics work | Dated provider quote, measured usage, total cost, sensitivity and capacity/cash distinction |
| What the owner should do next | Conditional pilot recommendation, named owners, spending ceiling, stop conditions |

Capture: one current-order reply, one before/after source update, one eligible return, one exception handoff, one outage, one access denial, and the results table. Include a short recorded backup of the live-system demonstration.

The slides should say **demonstrated**, **measured**, **assumed**, and **proposed** precisely. For example: “The synthetic API-backed prototype updated its answer after a source change” is supportable after that check passes. “The retailer's service is production-ready” would require evidence this classroom prototype cannot supply.
