"""
Eval v4 — Full 20 câu với Reranker
------------------------------------
Pipeline: M11 (E5 + QE + Chapter Boost) → BGE Reranker v2-m3 (hybrid alpha=0.5)

So sánh:
  v3 best (M11):         @1=60%  @3=90%  @5=100%
  v4 after rerank @1:    ?       @3:     ?
"""

import os, sys, json, time
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).parent.parent / "retriever"))
sys.path.insert(0, str(Path(__file__).parent.parent / "indexer"))

from bm25_retriever   import BM25Retriever
from vector_retriever import VectorRetriever, BGESparseRetriever
from query_expansion  import expand_with_intent
from query_classifier import classify_query
from fusion           import weighted_rrf, chapter_boost_rerank
from reranker         import BGEReranker

BM25_INDEX  = Path(__file__).parent.parent / "indexer/indexes/bm25_10.2012.QH13.pkl"
QUESTIONS   = Path(__file__).parent / "questions.json"
RESULTS_V4  = Path(__file__).parent / "eval_results_v4.json"

HYBRID_ALPHA = 0.5  # tuned từ smoke test
TOP_RETRIEVE = 5
TOP_RERANK   = 3


def retrieve_top5(query, bm25, e5, bge_dense, bge_sparse):
    intent   = classify_query(query)
    expanded = expand_with_intent(query, intent)

    r_bm25   = bm25.search(expanded, top_k=10)
    r_e5     = e5.search(expanded, top_k=10)
    r_bge    = bge_dense.search(expanded, top_k=10)
    r_sparse = bge_sparse.search(expanded, top_k=10)

    if intent["type"] in ("basic_rights", "definition", "coverage"):
        w = [(0.3, r_bm25), (2.0, r_e5), (1.5, r_bge), (0.8, r_sparse)]
    else:
        w = [(0.5, r_bm25), (1.5, r_e5), (2.0, r_bge), (1.0, r_sparse)]

    rrf = weighted_rrf([(r, wt) for wt, r in w], top_k=15)

    if intent.get("boost_early") and intent.get("boost_dieu_range"):
        chunks = chapter_boost_rerank(rrf, boost_dieu_range=intent["boost_dieu_range"],
                                      boost_factor=2.0, top_k=TOP_RETRIEVE)
    else:
        chunks = rrf[:TOP_RETRIEVE]

    return chunks, intent


def recall_at_k(items, gt, k):
    return any(g in {x.so_dieu for x in items[:k]} for g in gt)


def recall_at_k_rerank(items, gt, k):
    return any(g in {x.so_dieu for x in items[:k]} for g in gt)


def main():
    with open(QUESTIONS, encoding="utf-8") as f:
        questions = json.load(f)

    print("Loading retrievers...")
    bm25       = BM25Retriever(str(BM25_INDEX))
    e5         = VectorRetriever("intfloat/multilingual-e5-large", "dense_e5", embed_prefix="query: ")
    bge_dense  = VectorRetriever("BAAI/bge-m3", "dense_bge", embed_prefix="")
    bge_sparse = BGESparseRetriever()
    reranker   = BGEReranker()
    print()

    # Metrics
    ret_hits  = {1: 0, 3: 0, 5: 0}
    rank_hits = {1: 0, 3: 0}
    failures  = 0
    per_question = []

    print("=" * 72)
    print(f"{'ID':<6} {'Type':<12} {'Ret@1':<7} {'Ret@5':<7} {'Rnk@1':<7} {'Rnk@3':<7} GT → Top3")
    print("=" * 72)

    for q in questions:
        try:
            # Step 1: Retrieve
            top5, intent = retrieve_top5(q["question"], bm25, e5, bge_dense, bge_sparse)

            # Step 2: Rerank
            reranked = reranker.rerank(q["question"], top5, intent=intent,
                                       top_k=TOP_RERANK, hybrid_alpha=HYBRID_ALPHA)

            gt = q["ground_truth_dieu"]

            # Retrieval metrics
            r1 = recall_at_k(top5, gt, 1)
            r3 = recall_at_k(top5, gt, 3)
            r5 = recall_at_k(top5, gt, 5)
            if r1: ret_hits[1] += 1
            if r3: ret_hits[3] += 1
            if r5: ret_hits[5] += 1

            # Rerank metrics
            rk1 = recall_at_k_rerank(reranked, gt, 1)
            rk3 = recall_at_k_rerank(reranked, gt, 3)
            if rk1: rank_hits[1] += 1
            if rk3: rank_hits[3] += 1

            top3 = [r.so_dieu for r in reranked]
            print(f"{q['id']:<6} {q['type']:<12} "
                  f"{'✓' if r1 else '✗':<7} {'✓' if r5 else '✗':<7} "
                  f"{'✓' if rk1 else '✗':<7} {'✓' if rk3 else '✗':<7} "
                  f"{gt} → {top3}")

            per_question.append({
                "id": q["id"], "type": q["type"],
                "question": q["question"][:55],
                "gt_dieu": gt,
                "retrieval_top5": [c.so_dieu for c in top5],
                "rerank_top3":    top3,
                "ret@1": r1, "ret@3": r3, "ret@5": r5,
                "rnk@1": rk1, "rnk@3": rk3,
            })

        except Exception as e:
            print(f"{q['id']:<6} ERROR: {e}")
            failures += 1

    n = len(questions)
    print("=" * 72)
    print(f"\n{'Metric':<20} {'Retriever (M11)':<20} {'After Rerank':<20}")
    print("-" * 60)
    print(f"{'@1':<20} {ret_hits[1]/n:<20.0%} {rank_hits[1]/n:<20.0%}")
    print(f"{'@3':<20} {ret_hits[3]/n:<20.0%} {rank_hits[3]/n:<20.0%}")
    print(f"{'@5 (retriever)':<20} {ret_hits[5]/n:<20.0%} {'N/A (top-3 only)'}")
    print(f"\nFailures: {failures}")

    # v3 baseline comparison
    print("\n── vs v3 baseline (M11) ──")
    print(f"  Retriever @1: 60% → {ret_hits[1]/n:.0%}  (should be same)")
    print(f"  Reranker  @1: N/A → {rank_hits[1]/n:.0%}  ← improvement")
    print(f"  Reranker  @3: N/A → {rank_hits[3]/n:.0%}")

    # Save
    results = {
        "retriever": {
            "method": "M11 E5+QE+ChapterBoost",
            "recall@1": round(ret_hits[1]/n, 4),
            "recall@3": round(ret_hits[3]/n, 4),
            "recall@5": round(ret_hits[5]/n, 4),
        },
        "reranker": {
            "model":    "BAAI/bge-reranker-v2-m3",
            "alpha":    HYBRID_ALPHA,
            "recall@1": round(rank_hits[1]/n, 4),
            "recall@3": round(rank_hits[3]/n, 4),
        },
        "failures": failures,
        "per_question": per_question,
    }
    with open(RESULTS_V4, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nSaved → {RESULTS_V4}")


if __name__ == "__main__":
    main()
