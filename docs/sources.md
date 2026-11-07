# Sources & evidence register

Checked **7 November 2026**. Availability, pricing, endpoint behavior, and provider policies must be checked again before implementation. These references support feasibility discussion; they do not substitute for testing the selected deployment.

## Current MVP evidence and integration references

The current documentation was reviewed against code baseline `d49563f`. Implementation claims come from repository code and defined local tests, not from external marketing material. See [the evidence register](17-evidence-and-faq.md) and [presentation claim table](PRESENTATION_BRIEF.md).

| Primary reference | What was checked / used | Limit |
| --- | --- | --- |
| [Model adapter](../backend/model.py) and [workflow](../backend/service.py) | Actual four tool schemas, bounded inference, fallback, rendering and evidence | Source inspection does not prove broad language performance |
| [Read boundary](../backend/reads.py), [return intake](../backend/returns_flow.py), [store](../backend/store.py), [ERP](../backend/erp.py) | Ownership, policy/value checks, explicit workflow and local transactions | Not a real retailer/courier/payment connection or a complete security audit |
| [Channel](../backend/whatsapp.py), [API](../backend/app.py), [media](../backend/media.py), [workspace client](../src/useWorkspace.ts) | Local protocol, identity shortcuts, media limits, notifications and reconnect | Not official WhatsApp transport or durable distributed delivery |
| [Meta official Postman workspace](https://www.postman.com/meta/whatsapp-business-platform/overview) | Official WhatsApp Business Platform API reference entry point | Specific account setup and API version still need implementation-time verification |
| [Meta official signature-validation example](https://github.com/fbsamples/whatsapp-api-examples/blob/main/signature-validation-with-webhooks-payloads/app.py) | Provider signature example and header | An example, not a complete production adapter or proof this MVP verifies Meta events |
| [Twilio WhatsApp API overview](https://www.twilio.com/docs/whatsapp/api) and [best practices](https://www.twilio.com/docs/whatsapp/best-practices-and-faqs) | Provider channel model, current service-window/template and opt-in guidance | Twilio is an optional example; no account, rate quote or integration is selected |
| [Twilio webhook security](https://www.twilio.com/docs/usage/webhooks/webhooks-security) | Provider-specific request validation | Not interchangeable with Meta's verification protocol |
| [Shiprocket API](https://apidocs.shiprocket.in/?version=latest) | Example logistics capability and tracking webhook reference | No retailer account, integration, API permission or serviceability has been tested |
| [Razorpay refund read](https://razorpay.com/docs/api/refunds/fetch-with-id/) | Example external refund-status source | A provider state is not proof of bank credit; no money moves here |
| [Razorpay webhook verification](https://razorpay.com/docs/webhooks/validate-test/) | Signature/raw-body guidance, duplicate event ID and unordered delivery | Used to motivate a proposed inbox/reconciliation pattern, not an implemented payment adapter |
| [Shopify order query](https://shopify.dev/docs/api/admin-graphql/latest/queries/order) | Example commerce order/fulfilment read | Actual retailer stack and scopes remain unknown |

**Research limitation:** direct Meta developer overview/webhook/send-message pages returned HTTP 429 during this documentation pass. The official Meta workspace/sample and accessible primary provider documentation were used instead. Recheck the selected current Meta/provider endpoints, permissions, signatures, message capabilities and rules before building the adapter. The archived Meta Node SDK is not recommended as a dependency. No rate card, current provider bill or production certification is asserted.

## Earlier design research

The following register is retained for the initial model/business discussion. Its US-region context came from the early draft and is superseded by the user's India-store decision. It does not establish current production requirements or measured results.

| Reference | What it supports | What it does not establish |
| --- | --- | --- |
| User-supplied Scenario A image | Retailer type, 400 queries/day, status/returns emphasis, live-order requirement, advisory deliverable | Detailed policy, ERP, channel, staffing, or rubric beyond the image |
| User-supplied preliminary report | Working assumptions about US location, WhatsApp, response times, staffing, preferences and selection weights | Validated operational measurements or final instructor requirements |
| [Official Qwen3-8B model card](https://huggingface.co/Qwen/Qwen3-8B) | Published weights, stated Apache 2.0 license, documented tool integration | This project's task success, provider region, or exact hosted availability |
| [Official Mistral Small 3.2 model card](https://huggingface.co/mistralai/Mistral-Small-3.2-24B-Instruct-2506) | Published weights, stated Apache 2.0 license, documented function-calling work | Superiority for this workload or a US endpoint hosting this exact model |
| [Mistral regional inference docs](https://docs.mistral.ai/inference/regional-inference) | A US inference route exists; exact-model availability is region-dependent | All data/metadata stays in the US, or our chosen model is available there |
| [Official WhatsApp Business pricing](https://whatsappbusiness.com/products/platform-pricing/) | Service-window concept and category/market-dependent charging | A specific retailer's total channel cost, BSP fees, or integration readiness |

All sample policies, customer IDs, item names, dates, model-token budgets, labor rates, benefit examples, and acceptance thresholds in this repository are illustrative design inputs unless explicitly marked otherwise. No provider quote, benchmark result, or retailer measurement has been collected in v0.1.

Current UI references: [WhatsApp Business app features](https://whatsappbusiness.com/products/business-app-features/) and [Business Platform features](https://whatsappbusiness.com/products/business-platform-features/). Apparel photography is licensed under the [Unsplash license](https://unsplash.com/license); photographer and image-page attribution is recorded in [public/products/credits.json](../public/products/credits.json). Images illustrate fictional catalogue items.
