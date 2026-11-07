# 03 — Architecture: current MVP and proposed integrations

**Current local implementation: v0.5, code baseline `d49563f`.** The [system guide](../SYSTEM_GUIDE.md) is the business explanation; this reference maps it to the code. The production diagram is a proposal.

## The design decision

Use a bounded workflow and a small set of tools. The model interprets supported requests; backend code owns identity, permissions, calculations, writes and final transactional responses. Return intake is an explicit state machine. There is no autonomous multi-agent framework, arbitrary SQL tool, vector database or project fine-tuning in the current implementation.

## Current deployment

```mermaid
flowchart LR
    subgraph Browser[Browser experiences]
        PHONE[Phone at /whatsapp]
        ERP[ERP at /]
    end
    subgraph Local[Local laptop - synthetic records]
        V[Vite :5173]
        API[FastAPI :8000]
        WF[Workflow and return state machine]
        READ[Authorized reads and rules]
        DB[(SQLite)]
        FILES[Local photo files]
        HUB[In-process WebSocket hub]
        O[Ollama :11434]
    end
    PHONE --> V
    ERP --> V
    V -->|HTTP and WebSocket /api proxy| API
    API --> WF
    WF -->|Bounded intent/tool proposal| O
    WF --> READ --> DB
    API -->|Operator commands| DB
    API --> FILES
    API --> HUB
    HUB --> PHONE
    HUB --> ERP
```

`npm run dev` starts Vite and FastAPI on loopback. A built frontend can instead be served by FastAPI at port 8000. The read layer currently calls SQLite in-process; it is not an outbound HTTP request to a real retailer. These are layers of one application, not separately deployed microservices.

## Layer and source map

| Layer | Responsibility | Source |
| --- | --- | --- |
| Experience | Operator tables/forms, phone messages, photos and reply buttons | [App.tsx](../src/App.tsx), [OperationsForms.tsx](../src/OperationsForms.tsx), [WhatsApp.tsx](../src/WhatsApp.tsx) |
| API/channel boundary | Request validation, synthetic sessions, local origins/capabilities, sockets, media | [app.py](../backend/app.py), [media.py](../backend/media.py) |
| Conversation | Contact/code stages, order choice, message IDs, retry/resume and pending intent | [whatsapp.py](../backend/whatsapp.py) |
| Workflow | One tool proposal, reference handling, rules/fallback, source errors, tickets, templates | [service.py](../backend/service.py) |
| AI adapter | Four schemas, inference configuration, proposal validation | [model.py](../backend/model.py) |
| Read/rule boundary | Ownership, healthy source, validated records and exact policy version | [reads.py](../backend/reads.py), `Workflow.return_result` in [service.py](../backend/service.py) |
| Return application | Draft states, explicit answers and final RMA submission | [returns_flow.py](../backend/returns_flow.py) |
| Operations/persistence | Customer/order/return/ticket commands; revisions and transactions | [erp.py](../backend/erp.py), [store.py](../backend/store.py) |
| Synchronization/evidence | Source-backed pushes, saved conversations, workspace reload and traces | [whatsapp.py](../backend/whatsapp.py), [useWorkspace.ts](../src/useWorkspace.ts) |

Fixture JSON seeds/resets SQLite. Runtime answers use current records. The policy is a structured setting; there is no document retrieval pipeline in this MVP.

## Order-answer sequence

```mermaid
sequenceDiagram
    participant C as Customer
    participant CH as Channel/session
    participant W as Workflow
    participant M as Model
    participant R as LiveReads
    participant DB as SQLite
    C->>CH: Track selected order 4812
    CH->>W: Message and confirmed order context
    W->>M: Tool schemas, IDs and limited recent history
    M-->>W: Untrusted proposal
    W->>W: Validate tool and reference provenance
    W->>R: get_order(session.customer, 4812)
    R->>DB: Owned record and source controls
    R-->>W: Validated order at revision N
    W->>R: get_payment with expected revision N
    R->>DB: Current payment projection
    alt Compatible validated reads
        W->>W: Backend render and evidence persistence
        W-->>CH: Facts, product data and actions
        CH-->>C: Saved business message
    else Unavailable, invalid, inaccessible or changed
        R-->>W: SourceError
        W-->>CH: Supported failure or handoff path
        CH-->>C: No guessed current status
    end
```

Not every phone turn invokes AI. Identification, menu selection, deterministic return intake and source-change notifications have code paths that need no model. A failed model call uses a labeled rules fallback, subject to the same source controls. The model adapter is bounded to one proposal, not repeated self-directed actions.

## Authority boundaries

- Customer text, photos, addresses and model proposals are untrusted inputs. Reporting a payment or garment condition does not prove it.
- The server chooses the bound customer ID. Order/item references are resolved from allowed context and owned records. Ambiguity still requires careful selection; heuristics are not a proof of customer intent.
- Typed validation catches specified bad data; it cannot prove that an operator's or courier's event reflects physical reality.
- Staff and customer commands have different routes. The local operator capability is an evaluator mechanism, not real staff authentication/RBAC.
- Return submission belongs to `ReturnFlow`; it is not a model-callable commercial action. Staff records later stages through the ERP. No carrier/payment call exists.
- Traces/history may contain sensitive data in a real deployment. Current logging is not comprehensively redacted or immutable.

## Proposed production integration shape

```mermaid
flowchart TB
    WA[Real WhatsApp] <--> P[Meta Cloud API or selected provider]
    P <--> EDGE[HTTPS channel adapter]
    EDGE --> IN[Durable inbox and deduplication]
    IN --> APP[Bounded application service]
    STAFF[Authenticated staff portal] --> APP
    APP --> ID[Customer linking and staff identity]
    APP <--> MODEL[Approved inference endpoint]
    APP --> GATE[Authorized business adapters]
    GATE <--> OMS[Existing commerce / OMS]
    GATE <--> COURIER[Courier / aggregator]
    GATE <--> PAY[Payment / refund provider]
    GATE <--> HELP[Existing helpdesk]
    APP --> DB[(Workflow state and source projections)]
    APP --> MEDIA[Private media storage]
    APP --> OUT[Durable outbox and delivery workers]
    OUT --> EDGE
    APP --> OBS[Audit, metrics and incident controls]
```

This proposal can remain a modular service. PostgreSQL, a managed queue, Redis or particular hosting products are options to select after discovery; none is installed or mandatory here. Multiple workers require shared event distribution and locks/state beyond the in-process hub.

Each external system retains field authority. Use live transactional APIs for current order facts; a vector index is not the authority for latest status. Approved document retrieval might later explain a larger policy library, but must preserve effective versions and remain separate from order reads.

An outbox coordinates local state and outbound work; it cannot make an external pickup/refund and local database update one transaction. Use command intent records, provider identifiers, approved permissions and reconciliation. See [synchronization](14-data-and-synchronization.md), [tool contracts](13-business-tools-and-scenarios.md) and [production gates](15-production-plan-and-operations.md).
