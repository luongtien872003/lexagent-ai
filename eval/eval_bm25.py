#!/usr/bin/env python3
"""
Eval BM25 retriever — quick sanity check.
Usage: python eval/eval_bm25.py
"""
import sys, json
from pathlib import Path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from backend.core.retrieval.bm25 import BM25Retriever

QUESTIONS = ROOT / "eval/questions.json"
INDEXES   = ROOT / "data/indexes"


def main():
    with open(QUESTIONS, encoding="utf-8") as f:
        questions = json.load(f)

    bm25 = BM25Retriever(str(INDEXES))
    print(f"\n  Loaded law_ids: {bm25.available_law_ids()}\n")

    hit1 = hit5 = 0
    for q in questions:
        query    = q["question"]
        expected = set(q.get("expected_dieu", []))
        if not expected:
            continue

        results = bm25.search(query, top_k=5)
        found   = {r.so_dieu for r in results}

        if expected & {results[0].so_dieu} if results else set():
            hit1 += 1
        if expected & found:
            hit5 += 1

    n = len([q for q in questions if q.get("expected_dieu")])
    print(f"  BM25 Eval ({n} queries)")
    print(f"  Recall@1 = {hit1/n*100:.1f}%")
    print(f"  Recall@5 = {hit5/n*100:.1f}%\n")

if __name__ == "__main__":
    main()
