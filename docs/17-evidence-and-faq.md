# 17 — Evidence, presentation claims and FAQ

**Purpose:** let the team defend the MVP without overstating it. Current local MVP **v0.6**, reviewed 8 November 2026; backend suite: **150 cases**. Contextual support/RAG is implemented; real retailer/provider integrations remain future work.

## What is verified and where?

| Evidence | Source | What it supports |
| --- | --- | --- |
| Current source change and outage behavior | [test_workflow.py](../backend/tests/test_workflow.py) | Defined fresh-read/failure/policy/item-context behavior |
| Account/code stages, message resume/dedup and transport | [test_whatsapp.py](../backend/tests/test_whatsapp.py) | Defined synthetic channel behavior, not real WhatsApp delivery |
| ERP CRUD, revision conflicts, notifications, returns and assignment | [test_erp.py](../backend/tests/test_erp.py) | Defined local operations boundaries and synchronization |
| Bad source data, unsupported model reference, evidence/photo validation, explicit submission and transaction rollback | [test_grounding.py](../backend/tests/test_grounding.py) | Defined adversarial/workflow/transaction cases |
| Focused follow-ups, compound questions, return interruptions/corrections, negation, RAG refresh/provenance, checked model wording and fallback | [test_support.py](../backend/tests/test_support.py) | Defined conversation and composition boundaries; many cases deliberately use model doubles |
| Current authored conversations | [runner](../evaluation/run_conversations.py), [cases](../evaluation/conversation_cases.json), [recorded v0.6 run](../evaluation/results/v06-conversations.json) | 16 authored scenarios in baseline and real Qwen modes; development regression, not unseen accuracy |
| Live browser demonstrations | [screens and flow](10-grounded-india-returns.md), [ERP screen](../design/erp-dashboard.png), [phone screen](../design/whatsapp-phone-only.png) | Recorded local UI behavior and source-backed Qwen demo; screenshots alone are not automated assertions |
| Historical real model/rules smoke | [v0.2 result](../evaluation/results/local-qwen3-smoke.json), [runner](../evaluation/run_smoke.py) | Twelve authored scenarios per mode on a prior version; integration evidence only |
| Planned evaluation cases | [scenario seeds](../evaluation/scenarios.csv), [evaluation plan](06-evaluation-and-handoff.md) | A starting test design, not executed benchmark results |

Run `npm test` to reproduce the backend suite and `npm run build` to check the frontend build. Model smoke requires the configured real model. Tests use temporary databases; do not reset the shared demonstration workspace to run them. See [README](../README.md) for setup.

**Historical documentation verification, 7 November 2026:** the then-current 95-case suite passed, the API table matched 24 `/api` routes, the legacy catalogue matched four model schemas/six read functions, and 168 links resolved in 23 Markdown files. Those counts describe the v0.5 documentation pass.

**v0.6 verification, 8 November 2026:** 150 backend cases and the TypeScript/Vite production build pass. The recorded conversation run retains actual per-turn mode, source/guidance provenance, generated opening/closing, accepted wording or fallback reason, tokens and local timing. Model mode is not synonymous with model-written final text: action confirmations intentionally use guarded renderers, and failed wording checks also use source text. Count these separately when analyzing the JSON.

The final recorded run passed **16/16 authored scenarios in each mode**, with 49 customer turns per mode. The model run made 35 genuine inference calls and avoided inference on 14 system turns; no model-outage fallback occurred. Eight eligible replies used accepted generated wording; one generated factual wording was rejected and source-rendered. Other inference turns led to guarded intake, selection, handoff or failure responses. Median actual-model turn latency was 4,189 ms and nearest-rank p95 was 5,526 ms on the already-running local model. This single authored development run does not establish unseen accuracy, cold-start performance, capacity or a production SLA.

Browser checks used actual local Qwen: a tracking-only follow-up, delivery estimate, existing-refund response, account switch, return reason “the sleeves are too tight,” combined condition/tag answer, and a tag FAQ that preserved the pending photo step. ERP Conversations displayed named reads and the new readable evidence panel. These use the existing mutable synthetic workspace, not a pristine benchmark. The broader prior UI checks remain historical evidence.

Screens: [contextual return in the phone](../design/whatsapp-contextual-return.png), [readable response evidence in ERP](../design/erp-response-evidence.png).

## What these tests do not prove

Many tests use deterministic baseline routing, forced model failure or fake model output to isolate controls. They do not establish Qwen's accuracy on unseen language. The count is parameterized cases, not independent real customers, an uptime guarantee, security certification or statistical evidence of zero error. The authored real-Qwen conversations were used during development; passing them is regression evidence, not a fair estimate of generalization or proof of a “100x” improvement.

Still unverified: a real retailer/Meta/courier/gateway/helpdesk connection; complete security/privacy assessment; peak-load and multi-worker recovery; production credential/permissions; durable offline notifications; fraud/vision assessment; full finance/tax/discount/COD logic; broad multilingual conversations; held-out language comparison; customer satisfaction, sustained resolution, staff capacity and ROI.

## Compact claim register

| Claim | Status / accurate wording |
| --- | --- |
| Answers use live data | Demonstrated with current mutable synthetic SQLite records behind an API |
| Factual invention is constrained | Current validated paragraphs, targeted prose checks and fallback constrain specified unsupported claims; qualitative errors remain possible |
| The support uses RAG | Implemented local BM25 retrieval over 25 approved support passages, separate from live order reads |
| The model was fine-tuned | Unsupported as a weights claim; prompts/context/retrieval/decoding were tuned and synthetic training pairs prepared |
| The system is completely safe | Unsupported; describe specific controls and the remaining MVP gaps |
| Qwen is the best model | Unsupported; it is the current local implementation choice, not a benchmark winner |
| It is connected to WhatsApp | Browser simulation today; official channel integration is proposed |
| It books pickups/refunds | It records synthetic booking/refund stages; no external booking/payment occurs |
| All systems are always synchronized | Shared local state and scoped notifications exist; durable cross-provider synchronization is proposed |
| It improves response time/cost by a stated percentage | Unmeasured hypothesis; needs baseline and pilot evidence |
| India/INR/IST | Current user-selected product scope; not proof of a particular production data residency |

## FAQ for the team

**Why use AI at all?** To understand varied wording/follow-ups and phrase contextual explanations. RAG supplies approved reference content; APIs supply current facts; rules calculate; the state machine collects reported answers; staff decides exceptions. Compare on an unseen set before claiming model superiority.

**Is this RAG?** Yes. The phone retrieves approved passages using a local BM25 index with topic filtering/boosts, then supplies them to the model. There is no vector database or embedding API. Current order/payment facts still require authorized live reads. See [document 18](18-conversational-rag.md).

**Did we fine-tune the model?** No weights or LoRA adapter have been trained. We tuned instructions, context, retrieval, schema and decoding (default temperature 0.2/top-p 0.8). Sixteen synthetic training pairs and a real training/evaluation plan are in [training](../training/README.md). Temperature controls sampling variability, not understanding by itself.

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
