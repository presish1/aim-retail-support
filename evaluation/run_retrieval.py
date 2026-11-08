"""Authored retrieval checks, independent of the generator. No customer database indexed."""

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.hybrid import HybridRetriever
from backend.model import ModelAdapter
from backend.retrieval import guides


async def run(output):
    model = ModelAdapter()
    retriever = HybridRetriever(model)
    cases = json.loads((Path(__file__).parent / "retrieval_cases.json").read_text())
    results = []
    for case in cases:
        lexical = guides.search(case["query"], limit=4)
        hybrid, details = await retriever.search(guides, case["query"], limit=4)
        expected = set(case["expected"])
        row = {
            **case,
            "bm25_top4": [d["id"] for d in lexical],
            "hybrid_top4": [d["id"] for d in hybrid],
            "bm25_hit": bool(expected & {d["id"] for d in lexical}),
            "hybrid_hit": bool(expected & {d["id"] for d in hybrid}),
            "retrieval": details,
        }
        results.append(row)
        print(
            f"lexical={row['bm25_hit']} hybrid={row['hybrid_hit']} {case['query']}",
            flush=True,
        )
    report = {
        "kind": "authored_retrieval_regression_not_holdout",
        "at": datetime.now(timezone.utc).isoformat(),
        "guide_digest": guides.digest,
        "embedding_model": retriever.model,
        "k": 4,
        "summary": {
            "cases": len(cases),
            "bm25_hits": sum(r["bm25_hit"] for r in results),
            "hybrid_hits": sum(r["hybrid_hit"] for r in results),
            "semantic_fallbacks": sum(
                bool(r["retrieval"].get("fallback_reason")) for r in results
            ),
        },
        "limitations": "Authored development checks; any acceptable reference in top 4 counts as a hit. No unseen benchmark or customer outcome claim.",
        "results": results,
    }
    Path(output).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="artifacts/local/retrieval-v07.json")
    asyncio.run(run(parser.parse_args().output))
