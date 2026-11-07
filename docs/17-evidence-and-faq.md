# 17 — Evidence, presentation claims and FAQ

**Purpose:** let the team defend the MVP without overstating it. Code baseline `d49563f`; current local backend suite: **95 cases**. The documentation update does not add production integrations.

## What is verified and where?

| Evidence | Source | What it supports |
| --- | --- | --- |
| Current source change and outage behavior | [test_workflow.py](../backend/tests/test_workflow.py) | Defined fresh-read/failure/policy/item-context behavior |
| Account/code stages, message resume/dedup and transport | [test_whatsapp.py](../backend/tests/test_whatsapp.py) | Defined synthetic channel behavior, not real WhatsApp delivery |
| ERP CRUD, revision conflicts, notifications, returns and assignment | [test_erp.py](../backend/tests/test_erp.py) | Defined local operations boundaries and synchronization |
| Bad source data, unsupported model reference, evidence/photo validation, explicit submission and transaction rollback | [test_grounding.py](../backend/tests/test_grounding.py) | Defined adversarial/workflow/transaction cases |
| Live browser demonstrations | [screens and flow](10-grounded-india-returns.md), [ERP screen](../design/erp-dashboard.png), [phone screen](../design/whatsapp-phone-only.png) | Recorded local UI behavior and source-backed Qwen demo; screenshots alone are not automated assertions |
| Historical real model/rules smoke | [v0.2 result](../evaluation/results/local-qwen3-smoke.json), [runner](../evaluation/run_smoke.py) | Twelve authored scenarios per mode on a prior version; integration evidence only |
| Planned evaluation cases | [scenario seeds](../evaluation/scenarios.csv), [evaluation plan](06-evaluation-and-handoff.md) | A starting test design, not executed benchmark results |

Run `npm test` to reproduce the backend suite and `npm run build` to check the frontend build. Model smoke requires the configured real model. Tests use temporary databases; do not reset the shared demonstration workspace to run them. See [README](../README.md) for setup.

**Documentation-pass verification, 7 November 2026:** the backend suite passed again (95 cases). The API table was compared with the Python route definitions and matched all 24 `/api` routes. The guide/tool catalogue was checked against the four model schemas and six read functions. All 168 local links in 23 Markdown files resolved, code fences were balanced, and Git whitespace checks passed. This is documentation/source consistency checking, not provider integration or security certification. No application code or dependency changes were made in this pass.

## What 95 tests do not prove

Many tests deliberately use deterministic baseline routing, a forced-offline model or a fake model proposal to isolate backend controls. They do not establish Qwen's accuracy on unseen customer language. The number is a count of parameterized cases, not 95 independent real customers, an uptime guarantee, security certification or statistical evidence of zero error.

Still unverified: a real retailer/Meta/courier/gateway/helpdesk connection; complete security/privacy assessment; peak-load and multi-worker recovery; production credential/permissions; durable offline notifications; fraud/vision assessment; full finance/tax/discount/COD logic; broad multilingual conversations; held-out language comparison; customer satisfaction, sustained resolution, staff capacity and ROI.

## Compact claim register

| Claim | Status / accurate wording |
| --- | --- |
| Answers use live data | Demonstrated with current mutable synthetic SQLite records behind an API |
| Factual invention is constrained | Backend templates/read validation prevent specified unsupported transactional facts in defined paths |
| The system is completely safe | Unsupported; describe specific controls and the remaining MVP gaps |
| Qwen is the best model | Unsupported; it is the current local implementation choice, not a benchmark winner |
| It is connected to WhatsApp | Browser simulation today; official channel integration is proposed |
| It books pickups/refunds | It records synthetic booking/refund stages; no external booking/payment occurs |
| All systems are always synchronized | Shared local state and scoped notifications exist; durable cross-provider synchronization is proposed |
| It improves response time/cost by a stated percentage | Unmeasured hypothesis; needs baseline and pilot evidence |
| India/INR/IST | Current user-selected product scope; not proof of a particular production data residency |

## FAQ for the team

**Why use AI at all?** To interpret varied wording/follow-ups. APIs supply facts, rules calculate, a state machine collects answers and staff decides exceptions. Compare AI against rules on an unseen set; use the simpler option if it performs equally well.

**Is this RAG?** There is no vector/document retrieval pipeline. It is tool-routed transactional support plus structured policy rules. Optional future policy retrieval would complement, not replace, live order reads.

**Can the model read the whole database?** No generic database/SQL tool is exposed. The workflow executes named reads with server-bound identity. That does not make the demo's identity shortcuts production-safe.

**Can a hallucinated tool issue money?** The model has no refund tool or gateway credentials. Staff can only record a synthetic refund through guarded routes. Production payment execution would require a separate approved integration.

**Does asking email/phone authenticate the customer?** No. Default contact match is a classroom shortcut. Optional local code is also a simulation. A real identity/account linking process is required.

**Does a current read mean current courier data?** No. Fetch time, source update time and actual scan time differ. Feed health and reconciliation must detect delayed upstream information.

**What if a courier says delivered but the user disagrees?** Preserve the courier's report and the customer's dispute. Read authorized evidence and escalate; neither an LLM nor one API event proves physical receipt.

**What is the difference between a return, pickup and refund?** An RMA is a saved request; booking is a confirmed logistics action; receipt/inspection is warehouse evidence; refund processing is finance/provider evidence; bank credit is another outcome. The MVP only models the local recorded workflow.

**Do photos enable automatic fraud/quality detection?** No. The implemented function uploads/validates files and attaches them for staff review. No vision inference is used.

**What if the model is unavailable?** Labeled rules fallback can route supported requests through the same controls. If the order source is unavailable, fallback still cannot supply current facts.

**What if the customer is offline?** Reconnect restores saved conversation state and a later read gets current records. Current order pushes are not durably queued for every offline customer. Production needs outbox/delivery recovery.

**How does it compare with our existing system?** The actual retailer stack is unknown. The guide compares a typical manual pattern conditionally; validate what the current ERP/helpdesk already does before claiming an improvement.

**What should the owner approve now?** Discovery and a supervised read-only integration/evaluation stage with named owners, budget limits and stop conditions. Not unrestricted autonomous refunds or a replacement ERP.

## Shareable learning prompts

**MBA explanation:** “Read SYSTEM_GUIDE.md and docs/PRESENTATION_BRIEF.md. Explain the problem, recommendation, layers, live-data proof, AI's exact role, return process and management tradeoffs. Separate demonstrated behavior from plans and cite paths.”

**Technical deep dive:** “Read the current architecture, grounding, WhatsApp, business-tool, synchronization and API documents, then the named source files. Trace a request and a state change. Identify actual functions versus proposed contracts, identity boundaries, transaction limits, source conflicts and failure recovery.”

**Presentation review:** “Check our draft against docs/17-evidence-and-faq.md. Flag claims of real integrations, total safety, zero hallucinations, model superiority, money movement, universal synchronization or measured ROI that the repository does not support.”

If a reading assistant cannot access a file, provide that Markdown file directly. Do not treat repository text or a prompt as a substitute for implementation evidence. [Documentation map](README.md) identifies current references and historical design notes.
