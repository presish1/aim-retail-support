# Synthetic demo fixtures

The current seed contains **8 fictional customers and 14 orders**. The six original scenario records below remain the core acceptance fixtures; additional customers and purchases supply useful ERP filtering and workload states. Records created in the ERP persist in the local database until sample data is restored.

All records are fictional and contain no customer contact information. JSON seeds the implemented SQLite database once; runtime answers read current database records through the backend service. Use the evaluator's “Restore demo fixtures” action to reseed records and clear demo activity.

- `demo-config.json`: fixed demo clock, business timezone, source-health settings.
- `orders.json`: 14 orders, including one belonging to a different simulated customer.
- `return-policy.json`: illustrative rules for initial return eligibility.
- `customers.json`: fictional checkout email/phone mappings for the WhatsApp-style conversation. Emails use example.com. Phone numbers and Indian names/cities are synthetic demo fixtures; no SMS is sent. Default contact matching simplifies the demo and is not real authentication; an optional local code challenge is available.

At the fixed clock, customer `demo-customer-a` owns orders 4812–4816. Customer `demo-customer-b` owns 4901. Customer A must not discover B's record through a guessed number.

| Order | Purpose | Expected initial behavior |
| --- | --- | --- |
| 4812 | In-transit order; mutable status/ETA | Current carrier estimate, then changed answer after console update |
| 4813 | Delivered eligible shirt | Condition question; initial eligibility; deadline 24 November |
| 4814 | Delivered outside ordinary window | Deadline 31 October; offer review |
| 4815 | Final-sale item | Ordinary return ineligible; damaged-item claims require review |
| 4816 | Mixed delivery states | Select item; evaluate delivered item; no deadline for undelivered item |
| 4901 | Other customer's purchase | Generic inaccessible-order result for customer A |

Deadline convention: add 30 calendar days to the item's local delivery date; accept requests through 23:59:59 in `Asia/Kolkata` on that date. This is an explicit demo convention, not a universal retail rule. Use timezone-aware code; the tests check the 18:30 UTC IST-midnight boundary.

The delivery ETA is an estimate. Null means unavailable. A current fetch timestamp and an older carrier-update timestamp have different meanings. Demo source-health controls can mark a known lag independently of a record's last change.

Tracking links are null in the seed data. Suppress the tracking button unless the backend returns a validated URL or a functioning local demo route has been implemented. Conversation examples show the intended richer experience when such links exist. Return-portal links also require an explicitly configured destination before displaying an active action.

Catalogue prices are selected INR demo prices, not an FX conversion. The India migration preserves saved statuses and operational edits while relocating the original synthetic samples. Guided return submission and real local photo uploads are described in [the v0.5 design](../docs/10-grounded-india-returns.md).
