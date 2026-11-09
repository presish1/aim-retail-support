# Threadline
### Order & returns support, grounded in the order system

**AI in Management · MBA · Scenario A · Working prototype v0.8 · 9 November 2026**

> Recommend a small, supervised AI service that answers routine post-purchase questions using current order records, checks return eligibility with explicit business rules, and hands exceptions to a person with the context attached.

This repository contains the **working prototype**, service design and architecture for an academic consulting assignment. It combines Gemini, hybrid semantic/keyword RAG and an API-backed live synthetic order database. “Threadline” and all example records are fictional. [Read the current architecture](docs/19-gemini-hybrid-live-data.md).

## Preparing the team presentation

Start with the **[presentation briefing](docs/PRESENTATION_BRIEF.md)** for a slide-ready narrative, architecture diagram, speaker notes, demo script and likely questions. Read the **[complete system guide](SYSTEM_GUIDE.md)** for a self-contained explanation of the MVP. Share that file's GitHub link when asking an assistant or teammate to learn the system; some reading tools will need the individual linked files.

The **[documentation map](docs/README.md)** separates current implementation, verified local evidence, production proposals, assumptions and historical notes. The MVP uses real reads from a mutable synthetic database and a browser WhatsApp simulation. Real WhatsApp, courier, payment and retailer integrations are future work. It demonstrates specific safeguards; it is not universally hallucination-free or certified totally safe.

## Retail operations workspace

Open **http://127.0.0.1:5173** for the ERP. It includes searchable order and customer records, order creation, fulfilment editing, payment status, return processing, a support queue, conversation history, and an activity log. All counts reflect the database; no invented performance metrics are displayed.

![Threadline retail operations workspace](design/erp-dashboard.png)

## WhatsApp customer experience

Open **http://127.0.0.1:5173/whatsapp**, or use **Open customer chat** in the ERP header. This tab contains only the iPhone mockup. Operators manage settings and inspect conversations in the ERP.

Ask “Where is my order?”, then supply **aarav@example.com**, **+91 90000 00101**, or **CUS-1001**. The default demo setting matches an existing account directly. An unknown contact gets an explicit account-not-found reply and is not asked for a code. **ananya@example.com** is a second fictional customer. Add a new customer and order in the ERP to test a new account end to end.

Saving a selected order's status, carrier estimate, or tracking details sends a source-backed update to its connected customer chat. A subsequent AI request reads the database again. The ERP also refreshes through its own WebSocket when messages or records change. [Read current synchronization and limits](docs/14-data-and-synchronization.md).

![Gemini customer conversation with current tracking data](design/whatsapp-gemini-support.png)

## Customer changes and delivery estimates

Ask “I ordered S but need M for order [ID].” The service reads the owned unfulfilled purchase and configured size options, shows an exact preview, and saves only after confirmation. The size, revision and audit record commit together; the open ERP refreshes automatically. Shipped items go to store review. Use **Demo tools → Prepare a size-change demo** to create an S order for Aarav.

In Orders, click the **Delivery estimate** date to set or clear it. Eligible connected chats receive a short update, and the next question reads the saved date. Presets use the displayed store demo clock. [Read the flow, limits and demo steps](docs/20-delivery-and-order-actions.md).

## India store and guided returns

Catalogue prices are illustrative INR prices; policy and delivery dates use IST. Customer replies include product photographs, order details, payment status, and useful reply buttons. Return intake collects the item, reason, condition, tags, optional photos, quantity, pickup address and preferred window, then asks for explicit submission. The ERP continues through approval, carrier booking, receipt, inspection and recorded refund. No carrier booking or payment is executed.

The [return design and read contracts](docs/10-grounded-india-returns.md) explain the factual boundary and return journey. The [current Gemini/RAG reference](docs/19-gemini-hybrid-live-data.md) explains the model, retrieval, live reads and safeguards. Photos and credits are bundled under [public/products](public/products/credits.json).

## Conversational support and RAG

The phone uses **Gemini 3.8 Flash** with a versioned, 26-passage support corpus. **Hybrid RAG combines BM25, Gemini embeddings and reciprocal-rank fusion** to find relevant explanations. General help needs no email; the controller keeps the account, purchase and return step in context.

Current order facts come from fresh authorized reads and locked factual paragraphs. Generated wording is checked before use; rejected wording falls back to the approved/source renderer. Return submission and staff decisions remain guarded workflows. ERP Conversations shows the intent, guidance, reads and actual model/fallback behavior.

Gemini uses provider sampling defaults, LOW thinking and at most one generation call per free-text turn. Query embeddings are separate; approved document vectors are cached and invalidated when the guide changes. Fine-tuning is outside the current scope. The system's evidence comes from retrieval, live read contracts, guarded workflows and recorded checks.

## Run the prototype

Requires Node.js 20.19+ or 22.12+, Python 3.11+, internet and a Gemini API key with generation/embedding access. No local model download or Ollama installation is required.

```sh
git clone https://github.com/presish1/aim-retail-support.git
cd aim-retail-support
npm ci
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.lock
cp .env.example .env
# Add your own THREADLINE_MODEL_API_KEY to .env using an editor.
npm run dev
```

The dev command starts Vite and FastAPI; records persist in ignored `artifacts/local/threadline.db`. Approved guide vectors are cached under `artifacts/local/retrieval/`. **Settings → Restore sample data** restores 8 fictional customers and 14 orders and clears subsequent demo activity.

For a built frontend served by FastAPI alone: `npm run build`, then `npm start`, then open `http://127.0.0.1:8000`.

Environment variables override `.env`. Keys stay on the backend; never commit `.env`. Optional legacy Ollama/compatible adapters remain in code. The store region is India; a production cloud-processing region and data handling terms still need an owner decision.

```sh
npm test
npm run build
.venv/bin/python evaluation/run_conversations.py --modes baseline model --output artifacts/local/conversations.json
.venv/bin/python evaluation/run_retrieval.py --output artifacts/local/retrieval.json
```

**First demo:** open customer chat → ask about an order → use `aarav@example.com` → select #4812 → find #4812 in ERP Orders → set Delivered in its inline selector → see the order update arrive in chat → ask “Can you check again?” → inspect the conversation and response evidence in ERP Conversations.

The default **Contact match · demo** setting intentionally simplifies identification for a synthetic classroom demo. Optional code verification is available under Settings; its code is visible in ERP Conversations. Neither mode is production authentication. The server binds to loopback. Return and refund records update the synthetic database only; no real payment service, retailer ERP, or WhatsApp account is connected.

Earlier designs and model experiments are listed separately in the [documentation history](docs/README.md#earlier-rationale-and-snapshots).

## The assignment we are solving

Scenario A is a direct-to-consumer apparel retailer receiving **400 queries per day**. Order status and returns dominate. **Answers must come from a live order system.** The deliverable is an actionable recommendation for a nontechnical owner, supported by a prototype that demonstrates feasibility.

Our central design question:

**How might we give a customer a trustworthy answer and a clear next step immediately, while reserving human attention for exceptions?**

## The concept in one minute

1. A customer asks, “Where is my order?” or “Can I return the shirt?”
2. The service verifies access to the purchase and reads its current record.
3. Gemini interprets the concern and phrases a reply using approved hybrid retrieval. Backend rules determine eligibility; fresh structured reads supply dates and status.
4. The customer receives the requested details and a useful next step. The compiler checks generated wording before inserting verified factual paragraphs.
5. Missing data, exceptions, and requests for a person create a handoff with verified context.

**The signature demonstration:** ask about an order, change its status in a separate demo order console, then ask again. The second answer must reflect the new database value. Turn the order API off: the service must admit it cannot check, rather than reuse the earlier answer as current.

## Recommended architecture

```mermaid
flowchart LR
    C[Customer channel] --> S[Session & identity verification]
    S --> W[Bounded support workflow]
    W --> K[Approved support-guide retrieval]
    K --> M[Gemini structured generation]
    M --> W
    W --> T[Authorized tool gateway]
    T <--> O[(Live order system)]
    T <--> P[Versioned return policy & rules]
    T --> H[Human support queue]
    T --> F[Validated facts and checked wording / fallback]
    F --> C
```

The phone model produces a typed intent, requested details, guidance IDs and conversational opening/closing. The backend owns authorization, calculations, permissions, factual values and writes. A rules baseline uses the same business boundary. [Read the current design](docs/19-gemini-hybrid-live-data.md).

## Read the design package

| File | What it helps the team decide |
| --- | --- |
| [Presentation briefing](docs/PRESENTATION_BRIEF.md) | Suggested presentation, speaker notes, demo narration and safe claims |
| [Complete system guide](SYSTEM_GUIDE.md) | Understand the whole MVP without starting with code |
| [Architecture](docs/03-architecture.md) | Actual layers, source map, request sequences and proposed deployment |
| [India and return design](docs/10-grounded-india-returns.md) | Current customer experience, INR/IST, return flow and screenshots |
| [Grounding and safety](docs/11-grounding-and-safety.md) | Implemented hallucination controls, threat model and remaining gaps |
| [WhatsApp integration plan](docs/12-whatsapp-integration.md) | Simulation versus real channel, webhooks, templates, media and people |
| [Business tools and scenarios](docs/13-business-tools-and-scenarios.md) | Actual model tools, internal reads and proposed courier/payment/store adapters |
| [Data and synchronization](docs/14-data-and-synchronization.md) | Source authority, revisions, transactions, offline behavior and events |
| [MVP-to-pilot plan](docs/15-production-plan-and-operations.md) | Integration gates, operational owners, evaluation and economics |
| [API and data reference](docs/16-api-and-data-reference.md) | Implemented endpoints, WebSocket protocol, records and configuration |
| [Evidence and FAQ](docs/17-evidence-and-faq.md) | What the tests demonstrate, untested areas and presentation answers |
| [Gemini, hybrid RAG and live data](docs/19-gemini-hybrid-live-data.md) | Current pipeline, embeddings/cache, exact database reads, grounding and evidence |
| [Delivery and customer order changes](docs/20-delivery-and-order-actions.md) | Confirmed S → M changes, live estimates, conversation, transactions and demo steps |
| [Documentation map and history](docs/README.md) | Reading paths and earlier definition, model, business-case and design notes |
| [Sources](docs/sources.md) | Primary references checked for the model and deployment discussion |
| [Demo data](data/README.md) | Eight synthetic customers, fourteen sample orders, an illustrative policy, and a fixed demo clock |
| [Evaluation scenarios](evaluation/scenarios.csv) | Thirty planned checks; no measured results |

## Current implementation decisions

- Focus on order status, return eligibility, and useful escalation.
- Use a browser-based customer chat to simulate the channel in class; treat official WhatsApp integration as a proposed next stage.
- Demonstrate real reads from a mutable local database behind an API. This proves a live integration pattern, while actual retailer ERP integration remains a production task.
- The model never writes retailer orders or payments. Operators edit synthetic orders; customers explicitly submit return requests through a fixed workflow. Staff records pickup, inspection, and refund decisions.
- Use Gemini generation and embeddings with hybrid retrieval. Compare quality and operating cost against the deterministic baseline before a retailer pilot.
- Treat staffing, channel, policy, prices, and benefits as assumptions until verified.

## Repository status

**Completed:** operations ERP, phone-only chat, Gemini support, hybrid semantic/keyword RAG, checked wording, persistent operational records, live updates, natural return intake, failure controls, deduplicated support requests, readable evidence and a rules baseline.

**Verification:** the [evidence register](docs/17-evidence-and-faq.md) records backend tests, real Gemini conversations, mutable-database checks, lexical/hybrid comparison and browser checks. These are authored development regressions, not unseen accuracy or a production reliability estimate. Earlier Qwen results remain historical.

**Next:** unseen conversation evaluation, measured provider/cost comparisons and real retailer integrations with production identity and deployment review. Current architecture, screenshots and recorded checks are ready for the team presentation.
