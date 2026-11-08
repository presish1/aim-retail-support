# Support tuning material

The running v0.6 uses **RAG, prompt examples, a structured response schema, and low-variance decoding**. Qwen3-8B's weights have **not** been fine-tuned. A custom prompt or a different temperature is not weight fine-tuning.

`support-examples.jsonl` contains 16 authored synthetic input/target pairs for prompt review and possible future supervised training. They cover intent/focus, relevant guide IDs and conversational opening/closing fields. The server inserts factual paragraphs separately. These pairs are not real customer data, a complete reviewed production dataset, or proof that an adapter improves quality. The inference prompt uses representative intent examples; it does not load this entire file on every request. A training pipeline would also need to construct the matching retrieved context for each pair.

The response guides in `data/support-guides.json` supply retrieval context. BM25 retrieves locally from this approved, versioned corpus. No orders, customer uploads or transcripts are placed in the guide index. Operational values still come from current authorized reads.

Current support generation defaults: temperature `0.2`, top-p `0.8`, repetition penalty `1.05`, non-thinking mode, output cap 380 tokens, context 6144 tokens, HTTP timeout 30 seconds. Exact UI actions/social turns avoid model calls. A free-text turn has at most one model call for planning and wording together. Temperature changes sampling variability; understanding comes from the model, useful context, task instructions, examples and retrieval—not temperature alone.

Before a genuine LoRA/SFT experiment:

1. Collect and review representative conversations, including failures and hard negative cases. Remove personal data and secrets with an approved process.
2. Split by conversation/customer pattern, keeping an unseen evaluation set separate. Do not train on the authored regression cases and call the score held-out performance.
3. Label correct intent, focus, allowed source references, appropriate clarifying question and safe response. Include multiple acceptable phrasings; keep transactional values as locked facts.
4. Train an adapter on suitable isolated hardware, retain the base model and record data/model/config hashes. Do not overwrite the working model without comparison.
5. Compare base + RAG against adapter + the same RAG on task success, missed issues, factual/authorization failures, latency and cost. Reject regressions; weight tuning cannot replace source reads, permissions or write gates.

The repository's conversation evaluation runner reports actual model versus fallback and accepted model wording versus source renderer. It is an authored regression exercise, not a production language benchmark. Training a new adapter remains a separate experiment requiring a reviewed dataset.
