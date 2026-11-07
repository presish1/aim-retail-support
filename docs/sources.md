# Sources & evidence register

Checked **7 November 2026**. Availability, pricing, endpoint behavior, and provider policies must be checked again before implementation. These references support feasibility discussion; they do not substitute for testing the selected deployment.

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
