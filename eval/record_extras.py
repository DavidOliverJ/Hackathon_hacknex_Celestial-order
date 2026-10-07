"""Record extra free-form demo questions into the LLM cache.

Run once with a key:  AGENT_MODE=record python eval/record_extras.py
The Streamlit demo can then answer these phrasings keyless (replay mode).
Claims are NOT written, so eval results are untouched.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("AGENT_MODE", "record")

from agent.pipeline import run  # noqa: E402
from agent.profile import build_profile  # noqa: E402

EXTRA_QUESTIONS = [
    "What was the total revenue in USD across all orders in 2024?",
    "How many duplicate rows are in the sales data?",
    "What was the average order value in Q1 2024?",
    "Which region had the lowest revenue in Q3 2024?",
    "How many orders were placed in July 2024?",
    "What is the median quantity per order?",
    "Which product category had the most products?",
    "How many distinct products were sold in Q3 2024?",
    "What was the total revenue of INR orders in Q3 2024?",
    "What was the average daily revenue in June 2024?",
    "What was the revenue on 2024-07-04?",
    "Did revenue grow from Q1 to Q2 2024?",
    "What was the profit on order O00001?",
    "What were the total sales in North America in May 2024?",
]


def main() -> None:
    profile = build_profile()
    ok = fail = 0
    for q in EXTRA_QUESTIONS:
        try:
            res = run(q, qid="demo", profile=profile, write_claim=False)
            status = "answered" if res["answerable"] else f"refused:{res['refusal_category']}"
            print(f"  [{status}] {q}", flush=True)
            ok += 1
        except Exception as exc:
            print(f"  [ERROR] {q} -> {exc}", flush=True)
            fail += 1
    print(f"done: {ok} recorded/answered, {fail} failed")


if __name__ == "__main__":
    main()
