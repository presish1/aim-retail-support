# 05 · Model selection & business case

**Historical model research and illustrative arithmetic.** The Qwen/open-weight recommendation below belongs to an earlier design. Current v0.7 uses [Gemini and hybrid RAG](19-gemini-hybrid-live-data.md). No model superiority, current price quote or realized savings is established here. The original US-region preference discussed below came from the early draft and is superseded by the user's India-store decision; production processing requirements still need confirmation. Use [the current plan](15-production-plan-and-operations.md) and [evidence](17-evidence-and-faq.md) in the presentation.

**v0.2 implementation decision:** use `qwen3:8b` through local Ollama for the synthetic classroom prototype, with non-thinking tool selection and server-rendered transactional facts. The 12-case integration smoke run passes, as does the rules baseline. The broader comparative evaluation and production deployment decision remain open; see [implementation status](07-implementation-status.md).

## Historical recommendation — superseded

Start with managed inference for an open-weight model, conditional on a suitable region, exact-model availability, acceptable retention, latency, and spending controls. Keep a deterministic baseline. Do not buy GPU infrastructure based only on 400 daily queries: that average says little about peak concurrency, token use, utilization, or support burden.

This is a deployment hypothesis. The final choice should follow the same task-specific evaluation for each candidate.

## Provisional candidate set

These are concrete evaluation candidates, not a claim that they are the newest or best models available. Refresh availability before implementation and pin exact model revisions/settings for repeatability.

| Candidate | Verified starting evidence | Role in evaluation | Still to establish |
| --- | --- | --- | --- |
| `Qwen/Qwen3-8B` | Official model card lists Apache 2.0 and describes tool integration | Small-model candidate for understanding short service requests | Provider-specific tool reliability, US deployment, latency, actual price, and case success |
| `mistralai/Mistral-Small-3.2-24B-Instruct-2506` | Official model card lists Apache 2.0 and improved function calling | Larger comparison candidate if the smaller model fails important cases | Exact model availability, deployment region, price, and incremental task value |
| Menu/rules baseline | No language model; same authorized tools and response renderer | Establish the value and expense of adding an LLM | Ambiguity handling and customer task completion |

Sources: [Qwen model card](https://huggingface.co/Qwen/Qwen3-8B), [Mistral model card](https://huggingface.co/mistralai/Mistral-Small-3.2-24B-Instruct-2506). Model-card capability is not evidence of success in this retailer's workflow.

## Separate model gates from deployment gates

**Model gates:** accessible weights; acceptable commercial-use license and obligations; correct tool-call/schema behavior on the chosen serving stack.

**Deployment gates:** exact model available in the selected US processing region if that preference is confirmed; documented retention and data handling; authenticated endpoint; operational budget controls; acceptable latency and uptime. Open weights do not guarantee a serverless provider hosts that exact model.

As one feasibility example, Mistral documents a US regional inference endpoint and region-specific model availability. Regional inference is distinct from the location of all account metadata or storage, so do not claim an end-to-end US data boundary from the endpoint alone. Verify the exact model and full data flow before choosing it. [Regional inference documentation](https://docs.mistral.ai/inference/regional-inference).

## Weighted selection after gates

Retain the draft's preference weights, but define what will be measured. Do not fill in invented grades.

| Criterion | Weight | Evidence |
| --- | --- | --- |
| Task quality | 40% | Completed tasks, correct tool arguments, factual integrity, appropriate clarification/escalation |
| Switching flexibility | 25% | Re-run on a second compatible deployment, recorded adapter changes, portable schemas and license |
| Monthly cost | 20% | Measured token use and total operating cost at ordinary and peak volume |
| Speed | 15% | Median and p95 useful-answer latency on the same test setup |

Score qualifying alternatives on a documented 1–5 scale. Calculate `0.40Q + 0.25F + 0.20C + 0.15S`. Define score thresholds before looking at results. Show raw measures beside the score so a preference weight cannot hide privacy failures or fabricated facts. Compare the winning LLM workflow with the baseline as a separate owner decision.

## Cost model

The 20-word customer message is only a small part of inference input. Include instructions, conversation history, tool schemas/results, multiple model calls, retries, and any billed reasoning tokens.

Define:

- `M` = incoming customer messages per month.
- `K` = unique customer cases per month, measured separately.
- `r` = share of messages sent to the model.
- `c` = mean model calls per routed message, including retries.
- `Tin`, `Tout` = mean billable input/output tokens per model call.
- `Pin`, `Pout` = quoted prices per million tokens for the exact deployment.

`Model cost = M × r × c × (Tin × Pin + Tout × Pout) / 1,000,000`

`Monthly service cost = model + messaging/BSP + app/database/logging + helpdesk increment + monitoring/maintenance + verification + contingency`

Track one-time integration/setup and any dedicated endpoint minimums separately. Provider quotas and alerts are not automatically hard financial caps; verify actual enforcement and maintain an application usage circuit breaker.

### Transparent arithmetic example

**Illustrative assumptions only:** 30 days; all 400 daily queries treated as incoming messages; all route to the model; two calls per message; 1,000 input and 150 output tokens per call.

- `M = 12,000`, model calls = `24,000`.
- Input = **24 million tokens**; output = **3.6 million tokens**.
- Model cost = **`24 × Pin + 3.6 × Pout` dollars/month**, before other operating costs.

This is a formula, not a vendor quote. Replace every input with measured traffic and a dated quote. Record whether regional surcharges, discounts, minimum fees, and caching apply. For a provider priced per GPU-hour, compare the full endpoint cost rather than converting from a nonexistent per-token rate.

The draft's 25% follow-up estimate would imply 100 follow-up messages and 300 other messages daily if the denominator is all 400 messages. It does not automatically establish 300 unique cases. Its 35% after-hours estimate implies 140 messages/day under the same denominator; these groups overlap and cannot be added as independent savings.

WhatsApp's official pricing page describes a customer service window and category/market-dependent message charging. Budget the chosen business solution provider, verification, and other channel charges separately; do not assume the entire channel is free. [Official WhatsApp pricing](https://whatsappbusiness.com/products/platform-pricing/).

## Benefit and break-even

Use cases rather than messages for benefits, and count only cases that remain resolved. If `a` is the sustained automation share, `h` is manual minutes avoided per automated case, and `R` is loaded hourly labor cost:

`Gross capacity value = K × a × h / 60 × R`

Subtract human review, escalations' incremental handling, monitoring, and rework to get net capacity value. Report cash savings only where overtime, outsourcing, or planned hiring actually changes. Freed employee time can be valuable without reducing payroll.

For a simple sensitivity illustration, **300 unique cases/day**, 30 days, 50% sustained automation, and four minutes avoided imply **300 hours/month of gross capacity**. At an assumed $20/hour that is **$6,000 of gross capacity value**, before offsets; none of these assumptions is a forecast or an observed result.

Compare at least three cases: low (25% automation, two minutes avoided), central (50%, four minutes), and high (65%, five minutes). Use the same measured case volume and show full operating/setup costs. Do not separately add follow-up reduction if that effect is already captured in measured handling time or case volume.

## The decision the owner should receive

Run a limited pilot if the integration gates pass, the model provides measurable value over the baseline, quality thresholds hold, and the conservative net value is positive within the spending ceiling. Otherwise retain the rules workflow or agent copilot, fix the limiting issue, and reassess. Provide a named support lead, a technical integration owner, an approved monthly budget, and explicit stop conditions.
