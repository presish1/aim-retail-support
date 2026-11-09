"""Authored conversation regression, not an unseen benchmark. Uses isolated temporary databases."""

import argparse
import asyncio
import json
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.model import ModelAdapter
from backend.service import Workflow
from backend.store import Store
from backend.whatsapp import ChannelHub, WhatsAppChannel

ROOT = Path(__file__).resolve().parents[1]


def check(record, store, expected):
    trace = record.get("latest_trace") or {}
    message = record["messages"][-1]
    text = message["text"].casefold()
    draft = record.get("return_draft") or {}
    errors = []

    def need(condition, label):
        if not condition:
            errors.append(label)

    for entry in record["messages"]:
        if entry["role"] == "assistant":
            for fragment in (
                "=>",
                "{{fact:",
                "[verified value]",
                "Offer to ",
                "Never promise ",
            ):
                need(
                    fragment not in entry["text"],
                    "leaked response instruction " + fragment,
                )

    for key, exp in expected.items():
        if key == "intent":
            need((trace.get("plan") or {}).get("intent") == exp, "intent")
        elif key == "outcome":
            need(message.get("outcome") == exp, "outcome")
        elif key == "guide":
            need(
                exp in (trace.get("retrieval") or {}).get("used_chunk_ids", []), "guide"
            )
        elif key == "contains":
            need(exp.casefold() in text, "contains " + exp)
        elif key == "contains_all":
            for part in exp:
                need(part.casefold() in text, "contains " + part)
        elif key == "not_contains":
            need(exp.casefold() not in text, "not_contains " + exp)
        elif key == "order":
            need(record.get("selected_order") == exp, "order")
        elif key == "draft_step":
            need(draft.get("step") == exp, "draft_step")
        elif key in ("reason", "condition", "tags"):
            need(draft.get(key) == exp, key)
        elif key == "stage":
            need(record["stage"] == exp, "stage")
        elif key == "offer":
            need(bool(record.get("pending_offer")) == exp, "offer")
        elif key == "no_tickets":
            need(not store.records("tickets"), "no_tickets")
        elif key == "ticket_count":
            need(len(store.records("tickets")) == exp, "ticket_count")
        elif key == "item_size":
            order = store.order(exp["order_id"])
            need(
                order["items"][exp.get("item_index", 0)]["size"] == exp["size"],
                "item_size",
            )
        elif key == "size_change_step":
            need(
                (record.get("size_change") or {}).get("step") == exp, "size_change_step"
            )
        elif key == "size_write_count":
            need(
                len(
                    [
                        a
                        for a in store.all_records("activity")
                        if a["action"] == "size_changed"
                    ]
                )
                == exp,
                "size_write_count",
            )
    return errors


async def run(args):
    cases = json.loads((ROOT / "evaluation/conversation_cases.json").read_text())
    if args.case:
        cases = [c for c in cases if c["id"] in args.case]
    model = ModelAdapter()
    if "model" in args.modes and not (await model.health())["ready"]:
        raise SystemExit(
            "Real model unavailable; don't count fallback as genuine inference."
        )
    results = []
    with tempfile.TemporaryDirectory(prefix="threadline-conversations-") as folder:
        for mode in args.modes:
            for case in cases:
                store = Store(Path(folder) / (mode + "-" + case["id"] + ".db"))
                for additional in case.get("additional_orders", []):
                    store.insert_order(additional)
                for reference, updates in case.get(
                    "order_updates_before_first", {}
                ).items():
                    store.revise_order(
                        reference,
                        lambda current, changes=updates: {**current, **changes},
                    )
                channel = WhatsAppChannel(store, Workflow(store, model), ChannelHub())
                record = channel.start()
                turns = []
                for index, text in enumerate(case["turns"]):
                    if index == len(case["turns"]) - 1:
                        for key, value in case.get("controls_before_last", {}).items():
                            store.set_setting(key, value)
                        for reference, updates in case.get(
                            "order_updates_before_last", {}
                        ).items():
                            store.revise_order(
                                reference,
                                lambda current, changes=updates: {**current, **changes},
                            )
                    started = time.perf_counter()
                    await channel.handle(record["id"], uuid.uuid4().hex, text, mode)
                    record = store.channel(record["id"])
                    trace = record.get("latest_trace") or {}
                    turns.append(
                        {
                            "customer": text,
                            "reply": record["messages"][-1]["text"],
                            "outcome": record["messages"][-1].get("outcome"),
                            "mode": trace.get("mode"),
                            "intent": (trace.get("plan") or {}).get("intent"),
                            "plan": trace.get("plan"),
                            "composition": trace.get("composition"),
                            "retrieval": trace.get("retrieval"),
                            "reads": trace.get("reads"),
                            "evidence": trace.get("evidence"),
                            "decoding": trace.get("decoding"),
                            "usage": trace.get("usage"),
                            "latency_ms": round((time.perf_counter() - started) * 1000),
                        }
                    )
                errors = check(record, store, case["expect"])
                row = {
                    "case": case["id"],
                    "requested_mode": mode,
                    "passed": not errors,
                    "errors": errors,
                    "turns": turns,
                }
                results.append(row)
                print(
                    f"{mode:8} {case['id']:28} {'PASS' if not errors else 'FAIL: ' + ', '.join(errors)}",
                    flush=True,
                )
                if args.output:
                    Path(args.output).write_text(
                        json.dumps(
                            {
                                "kind": "authored_conversation_regression_not_holdout",
                                "at": datetime.now(timezone.utc).isoformat(),
                                "model": model.model,
                                "limitations": "Synthetic authored cases used during development; no production accuracy or fine-tuning claim.",
                                "results": results,
                            },
                            indent=2,
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
    if any(not r["passed"] for r in results):
        raise SystemExit(1)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument(
        "--modes",
        nargs="+",
        choices=["baseline", "model"],
        default=["baseline", "model"],
    )
    p.add_argument("--case", action="append")
    p.add_argument("--output")
    asyncio.run(run(p.parse_args()))
