# Documentation map

**Current scope: MVP v0.7 · reviewed 8 November 2026.** This is an MBA Scenario A prototype for an Indian D2C apparel store. Customer/purchase/policy fixtures are fictional. Gemini generation and embedding calls are real; the live order source is mutable local SQLite. Current focus is hybrid RAG, live reads and grounded support. Fine-tuning is outside scope.

## Start here

1. **Preparing the presentation:** [Presentation briefing](PRESENTATION_BRIEF.md). Contains a slide-ready story, diagrams, speaker notes, demo steps and likely questions. No slides are generated here.
2. **Understanding the whole system:** [Complete system guide](../SYSTEM_GUIDE.md). This is the self-contained file to share with a teammate or a reading assistant.
3. **Checking a detailed claim:** use the references below and the linked code.

| Label | Meaning |
| --- | --- |
| **Implemented** | Exists in the MVP. Gemini is connected; retailer, courier, payment and WhatsApp business integrations remain proposed. |
| **Verified locally** | A defined test or demonstration passed on synthetic records. |
| **Proposed** | A future integration/control; not implemented in this repository. |
| **Assumption** | Requires the retailer's confirmation. |
| **Historical** | Describes an earlier design or prototype snapshot. |

The system is not certified “totally safe,” production-ready, or universally hallucination-free. The documents explain what its safeguards do and what remains unproven.

## Current references

| Document | What it explains |
| --- | --- |
| [System guide](../SYSTEM_GUIDE.md) | Purpose, architecture, differences from a conventional support workflow, MVP boundaries and learning path |
| [Presentation briefing](PRESENTATION_BRIEF.md) | Suggested slides, ready-to-use explanations, demo and presentation-safe claims |
| [03 — Architecture](03-architecture.md) | Layers, code ownership, request sequences and proposed integration shape |
| [10 — India and return design](10-grounded-india-returns.md) | Implemented customer experience, INR/IST fixtures, return journey and screenshots |
| [11 — Grounding and safety](11-grounding-and-safety.md) | Hallucination controls, threat model, residual risks and release blockers |
| [12 — WhatsApp integration](12-whatsapp-integration.md) | Current browser simulation and proposed real webhook/messaging integration |
| [13 — Business tools and scenarios](13-business-tools-and-scenarios.md) | Actual AI tools, internal reads, future business adapters and realistic cases |
| [14 — Data and synchronization](14-data-and-synchronization.md) | Authority, revisions, transactions, notifications, offline behavior and production event design |
| [15 — Production plan and operations](15-production-plan-and-operations.md) | MVP-to-pilot stages, ownership, deployment, costs, metrics and stop conditions |
| [16 — API and data reference](16-api-and-data-reference.md) | Current endpoints, socket events, records, settings and error contracts |
| [17 — Evidence and FAQ](17-evidence-and-faq.md) | Verification scope, known gaps, management questions and learning prompts |
| [19 — Gemini, hybrid RAG and live data](19-gemini-hybrid-live-data.md) | Current generation, embeddings/cache, ranking/fallback, database authority, grounding and tests |
| [Sources](sources.md) | Code evidence and dated primary external references |
| [Demo data](../data/README.md) | Fictional accounts, orders, policy and fixed clock |

For a business presentation read the briefing, system guide, scenarios and evidence. Engineers can continue through architecture, API reference and synchronization. A reading tool may need individual files; a GitHub link does not guarantee that it has fetched the entire repository.

## Earlier rationale and snapshots

[01 — Definition](01-project-definition.md) records assignment facts and assumptions. [02 — Service design](02-service-design.md) and [04 — Prototype specification](04-prototype-specification.md) are early explorations. [05 — Models/business case](05-models-and-business-case.md) contains provisional comparisons and arithmetic, not a completed benchmark or provider quote. [06 — Evaluation plan](06-evaluation-and-handoff.md) contains proposed targets. [07 — v0.2 status](07-implementation-status.md), [08 — Earlier WhatsApp design](08-whatsapp-experience.md), and [09 — v0.4 ERP](09-erp-workspace.md) are historical snapshots.

Use current code and the references above for present-tense claims. Document 10 records the retained return/read design. [18 — v0.6 conversation/RAG](18-conversational-rag.md) records the earlier local Qwen/BM25 version; document 19 supersedes its model/retrieval settings. India/INR supersedes the draft's US-store assumption. Comparisons with the retailer's unknown “existing system” remain conditional.
