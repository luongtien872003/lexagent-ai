"""
Eval v3b — Tune boost_factor để combine @1=75% + @5=100%.

Vấn đề: M13 boost_factor=2.5 làm @5 drop về 90%.
Mục tiêu: tìm boost_factor cho @1 cao nhất mà @5 không drop dưới 95%.

Thử: boost_factor = [1.2, 1.5, 1.8, 2.0, 2.3, 2.5]
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

BM25_INDEX = Path(__file__).parent.parent / "indexer/indexes/bm25_10.2012.QH13.pkl"
QUESTIONS  = Path(__file__).parent / "questions.json"
RESULTS_V3B = Path(__file__).parent / "eval_results_v3b.json"
TOP_K = 5
HARD_CASE_IDS = {"q003", "q004", "q005"}

BOOST_FACTORS_TO_TEST = [1.2, 1.5, 1.8, 2.0, 2.3, 2.5]


def recall_at_k(results, gt: list[int], k: int) -> bool:
    return any(gt_d in {r.so_dieu for r in results[:k]} for gt_d in gt)


def run_method(query, bm25, e5, bge_dense, bge_sparse, boost_factor, intent_weights=True):
    intent   = classify_query(query)
    expanded = expand_with_intent(query, intent)

    if intent_weights and intent["type"] in ("basic_rights", "definition", "coverage"):
        w = [(0.3, bm25), (2.0, e5), (1.5, bge_dense), (0.8, bge_sparse)]
    else:
        w = [(0.5, bm25), (1.5, e5), (2.0, bge_dense), (1.0, bge_sparse)]

    r_bm25   = bm25.search(expanded, top_k=10)
    r_e5     = e5.search(expanded, top_k=10)
    r_bge    = bge_dense.search(expanded, top_k=10)
    r_sparse = bge_sparse.search(expanded, top_k=10)

    rrf = weighted_rrf([
        (r_bm25,   w[0][0]),
        (r_e5,     w[1][0]),
        (r_bge,    w[2][0]),
        (r_sparse, w[3][0]),
    ], top_k=TOP_K * 3)

    if intent.get("boost_early") and intent.get("boost_dieu_range"):
        return chapter_boost_rerank(
            rrf,
            boost_dieu_range = intent["boost_dieu_range"],
            boost_factor     = boost_factor,
            top_k            = TOP_K,
        )
    return rrf[:TOP_K]


def evaluate(questions, bm25, e5, bge_dense, bge_sparse, boost_factor):
    hits = {1: 0, 3: 0, 5: 0}
    hard_case_results = []

    for q in questions:
        results = run_method(q["question"], bm25, e5, bge_dense, bge_sparse, boost_factor)
        gt = q["ground_truth_dieu"]

        if recall_at_k(results, gt, 1): hits[1] += 1
        if recall_at_k(results, gt, 3): hits[3] += 1
        if recall_at_k(results, gt, 5): hits[5] += 1

        if q["id"] in HARD_CASE_IDS:
            hard_case_results.append({
                "id":    q["id"],
                "gt":    gt,
                "top5":  [r.so_dieu for r in results[:5]],
                "hit@1": recall_at_k(results, gt, 1),
                "hit@5": recall_at_k(results, gt, 5),
            })

    n = len(questions)
    return {
        "boost_factor": boost_factor,
        "recall@1": round(hits[1] / n, 4),
        "recall@3": round(hits[3] / n, 4),
        "recall@5": round(hits[5] / n, 4),
        "hard_cases": hard_case_results,
    }


def main():
    with open(QUESTIONS, encoding="utf-8") as f:
        questions = json.load(f)

    print("Loading retrievers...")
    bm25       = BM25Retriever(str(BM25_INDEX))
    e5         = VectorRetriever("intfloat/multilingual-e5-large", "dense_e5", embed_prefix="query: ")
    bge_dense  = VectorRetriever("BAAI/bge-m3", "dense_bge", embed_prefix="")
    bge_sparse = BGESparseRetriever()
    print("Ready.\n")

    print(f"{'boost':>6}  {'@1':>6}  {'@3':>6}  {'@5':>6}  hard_cases(q003/q004/q005 @1)")
    print("=" * 68)

    all_results = []
    best = None

    for bf in BOOST_FACTORS_TO_TEST:
        r = evaluate(questions, bm25, e5, bge_dense, bge_sparse, bf)
        all_results.append(r)

        hc = {h["id"]: ("✓" if h["hit@1"] else "✗") + ("✓" if h["hit@5"] else "✗") for h in r["hard_cases"]}
        hc_str = f"q003={hc.get('q003','??')} q004={hc.get('q004','??')} q005={hc.get('q005','??')}"

        marker = ""
        if r["recall@5"] >= 0.95 and r["recall@1"] >= 0.70:
            marker = " ← candidate"
        if r["recall@5"] >= 1.0 and r["recall@1"] >= 0.70:
            marker = " ★ BEST"
            best = r

        print(f"{bf:>6.1f}  {r['recall@1']:>5.0%}  {r['recall@3']:>5.0%}  {r['recall@5']:>5.0%}  {hc_str}{marker}")

    # Chọn best: ưu tiên @5 cao nhất, tie-break bằng @1
    if best is None:
        # Nếu không có @5=100% + @1>=70%, chọn @5 cao nhất
        best = max(all_results, key=lambda x: (x["recall@5"], x["recall@1"]))

    print(f"\n→ Best boost_factor = {best['boost_factor']}")
    print(f"  @1={best['recall@1']:.0%}  @3={best['recall@3']:.0%}  @5={best['recall@5']:.0%}")

    # Save
    with open(RESULTS_V3B, "w", encoding="utf-8") as f:
        json.dump([{k: v for k, v in r.items() if k != "hard_cases"} for r in all_results],
                  f, ensure_ascii=False, indent=2)
    print(f"\nSaved → {RESULTS_V3B}")

    # In gợi ý update fusion.py
    print(f"""
→ Update trong fusion.py / eval_v3.py:
  chapter_boost_rerank(..., boost_factor={best['boost_factor']}, ...)
""")


if __name__ == "__main__":
    main()
