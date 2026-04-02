"""
Eval v3 — Test các method mới với intent-aware retrieval.

Methods mới (11-15):
  11. E5 + QE + Intent Classifier (chapter boost)
  12. Weighted RRF + QE (fix weighted_rrf đúng)
  13. Weighted RRF + QE + Chapter Boost
  14. BGE Dense + QE + Chapter Boost
  15. Full: Weighted RRF + QE + Chapter Boost (best mix)

Output:
  - eval_results_v3.json  (kết quả tổng hợp)
  - per-question breakdown để debug 3 hard cases
"""

import os, sys, json, time
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).parent.parent / "retriever"))
sys.path.insert(0, str(Path(__file__).parent.parent / "indexer"))

from bm25_retriever   import BM25Retriever
from vector_retriever import VectorRetriever, BGESparseRetriever
from query_expansion  import expand_query, expand_for_vector, expand_with_intent
from query_classifier import classify_query
from fusion           import (
    reciprocal_rank_fusion,
    weighted_rrf,
    chapter_boost_rerank,
    intent_aware_rrf,
)

# ── Paths ────────────────────────────────────────────────────────
QUESTIONS_PATH    = Path(__file__).parent / "questions.json"
BM25_INDEX        = Path(__file__).parent.parent / "indexer/indexes/bm25_10.2012.QH13.pkl"
BM25_BOOSTED      = Path(__file__).parent.parent / "indexer/indexes/bm25_boosted_10.2012.QH13.pkl"
RESULTS_V2        = Path(__file__).parent / "eval_results_v2.json"
RESULTS_V3        = Path(__file__).parent / "eval_results_v3.json"

# ── Hard cases cần theo dõi đặc biệt ────────────────────────────
HARD_CASE_IDS = {"q003", "q004", "q005"}

TOP_K = 5


# ════════════════════════════════════════════════════════════
# Load data
# ════════════════════════════════════════════════════════════

def load_questions():
    with open(QUESTIONS_PATH, encoding="utf-8") as f:
        return json.load(f)


# ════════════════════════════════════════════════════════════
# Recall calculator
# ════════════════════════════════════════════════════════════

def recall_at_k(results, ground_truth_dieu: list[int], k: int) -> bool:
    """True nếu ít nhất 1 ground truth dieu nằm trong top-k."""
    top_k_dieu = {r.so_dieu for r in results[:k]}
    return any(gt in top_k_dieu for gt in ground_truth_dieu)


def evaluate_method(
    method_fn,
    questions: list,
    label: str,
    verbose: bool = True,
) -> dict:
    """Chạy eval 1 method, trả về metrics."""
    hits = {1: 0, 3: 0, 5: 0}
    failures = 0
    per_question = []

    for q in questions:
        try:
            results = method_fn(q["question"])
        except Exception as e:
            print(f"  [ERROR] {q['id']}: {e}")
            failures += 1
            per_question.append({
                "id": q["id"], "type": q["type"],
                "question": q["question"][:50],
                "gt_dieu": q["ground_truth_dieu"],
                "top5_dieu": [], "hit@1": False, "hit@3": False, "hit@5": False,
                "error": str(e),
            })
            continue

        gt = q["ground_truth_dieu"]
        h1 = recall_at_k(results, gt, 1)
        h3 = recall_at_k(results, gt, 3)
        h5 = recall_at_k(results, gt, 5)

        if h1: hits[1] += 1
        if h3: hits[3] += 1
        if h5: hits[5] += 1

        top5 = [r.so_dieu for r in results[:5]]
        per_question.append({
            "id":       q["id"],
            "type":     q["type"],
            "question": q["question"][:60],
            "gt_dieu":  gt,
            "top5_dieu": top5,
            "hit@1":    h1,
            "hit@3":    h3,
            "hit@5":    h5,
        })

    n = len(questions)
    result = {
        "label":      label,
        "recall@1":   round(hits[1] / n, 4),
        "recall@3":   round(hits[3] / n, 4),
        "recall@5":   round(hits[5] / n, 4),
        "failures":   failures,
        "per_question": per_question,
    }

    if verbose:
        print(f"  {label:<45} @1={hits[1]/n:.0%}  @3={hits[3]/n:.0%}  @5={hits[5]/n:.0%}")

    return result


# ════════════════════════════════════════════════════════════
# Method definitions
# ════════════════════════════════════════════════════════════

def make_methods(bm25, e5, bge_dense, bge_sparse):
    """Trả về dict method_name → function(query → list[RetrievedChunk])."""

    # ── Baseline weights (giữ giống v2 để compare) ──────────────
    DEFAULT_WEIGHTS = [
        (bm25,        0.5),
        (e5,          1.5),
        (bge_dense,   2.0),
        (bge_sparse,  1.0),
    ]

    def _weighted_rrf_base(query, top_k=TOP_K):
        r_bm25   = bm25.search(query, top_k=10)
        r_e5     = e5.search(query,   top_k=10)
        r_bge    = bge_dense.search(query, top_k=10)
        r_sparse = bge_sparse.search(query, top_k=10)
        return weighted_rrf([
            (r_bm25,   0.5),
            (r_e5,     1.5),
            (r_bge,    2.0),
            (r_sparse, 1.0),
        ], top_k=top_k)

    # ── M11: E5 + QE + Intent Chapter Boost ─────────────────────
    def m11_e5_qe_intent(query):
        intent   = classify_query(query)
        expanded = expand_with_intent(query, intent)
        results  = e5.search(expanded, top_k=15)
        if intent["boost_early"]:
            results = chapter_boost_rerank(
                results,
                boost_dieu_range  = intent.get("boost_dieu_range"),
                priority_chapters = intent.get("priority_chapters"),
                boost_factor      = 2.5,
                top_k             = TOP_K,
            )
        return results[:TOP_K]

    # ── M12: Weighted RRF + QE (expand tất cả retrievers) ───────
    def m12_weighted_rrf_qe(query):
        expanded = expand_query(query, max_expansions=3)
        r_bm25   = bm25.search(expanded, top_k=10)
        r_e5     = e5.search(expand_for_vector(query), top_k=10)
        r_bge    = bge_dense.search(expanded, top_k=10)
        r_sparse = bge_sparse.search(expanded, top_k=10)
        return weighted_rrf([
            (r_bm25,   0.5),
            (r_e5,     1.5),
            (r_bge,    2.0),
            (r_sparse, 1.0),
        ], top_k=TOP_K)

    # ── M13: Weighted RRF + QE + Chapter Boost ──────────────────
    def m13_weighted_rrf_qe_boost(query):
        intent   = classify_query(query)
        expanded = expand_with_intent(query, intent)
        r_bm25   = bm25.search(expanded, top_k=10)
        r_e5     = e5.search(expanded, top_k=10)
        r_bge    = bge_dense.search(expanded, top_k=10)
        r_sparse = bge_sparse.search(expanded, top_k=10)
        return intent_aware_rrf([
            (r_bm25,   0.5),
            (r_e5,     1.5),
            (r_bge,    2.0),
            (r_sparse, 1.0),
        ], intent=intent, top_k=TOP_K)

    # ── M14: BGE Dense + QE + Chapter Boost ─────────────────────
    def m14_bge_qe_boost(query):
        intent   = classify_query(query)
        expanded = expand_with_intent(query, intent)
        results  = bge_dense.search(expanded, top_k=15)
        if intent["boost_early"]:
            results = chapter_boost_rerank(
                results,
                boost_dieu_range  = intent.get("boost_dieu_range"),
                priority_chapters = intent.get("priority_chapters"),
                boost_factor      = 2.5,
                top_k             = TOP_K,
            )
        return results[:TOP_K]

    # ── M15: Full Best Pipeline ──────────────────────────────────
    # Weighted RRF với intent expansion + chapter boost
    # Tune weights: E5 và BGE Dense nặng hơn, BM25 nhẹ hơn
    def m15_full_best(query):
        intent   = classify_query(query)
        expanded = expand_with_intent(query, intent)

        # Scenario queries: tăng BGE Dense (tốt hơn với semantic)
        # Rights/Definition queries: tăng E5 + thêm chapter boost
        if intent["type"] in ("basic_rights", "definition", "coverage"):
            weights = [(0.3, "bm25"), (2.0, "e5"), (1.5, "bge"), (0.8, "sparse")]
        elif intent["type"] == "scenario":
            weights = [(0.5, "bm25"), (1.5, "e5"), (2.0, "bge"), (1.0, "sparse")]
        else:
            weights = [(0.5, "bm25"), (1.5, "e5"), (2.0, "bge"), (1.0, "sparse")]

        r_bm25   = bm25.search(expanded, top_k=10)
        r_e5     = e5.search(expanded, top_k=10)
        r_bge    = bge_dense.search(expanded, top_k=10)
        r_sparse = bge_sparse.search(expanded, top_k=10)

        return intent_aware_rrf([
            (r_bm25,   weights[0][0]),
            (r_e5,     weights[1][0]),
            (r_bge,    weights[2][0]),
            (r_sparse, weights[3][0]),
        ], intent=intent, top_k=TOP_K)

    return {
        "11. E5 + QE + Chapter Boost":             m11_e5_qe_intent,
        "12. Weighted RRF + QE":                   m12_weighted_rrf_qe,
        "13. Weighted RRF + QE + Chapter Boost":   m13_weighted_rrf_qe_boost,
        "14. BGE Dense + QE + Chapter Boost":      m14_bge_qe_boost,
        "15. Full Best Pipeline":                  m15_full_best,
    }


# ════════════════════════════════════════════════════════════
# Hard case analysis
# ════════════════════════════════════════════════════════════

def print_hard_case_analysis(all_results: list[dict]):
    """In phân tích chi tiết cho 3 hard cases."""
    print("\n" + "=" * 70)
    print("HARD CASE ANALYSIS (q003, q004, q005)")
    print("=" * 70)

    for result in all_results:
        hard_hits = []
        for pq in result.get("per_question", []):
            if pq["id"] in HARD_CASE_IDS:
                hard_hits.append(pq)

        if not hard_hits:
            continue

        print(f"\n[{result['label']}]")
        for pq in hard_hits:
            hit5 = "✓" if pq["hit@5"] else "✗"
            hit1 = "✓" if pq["hit@1"] else "✗"
            print(f"  {pq['id']} @1={hit1} @5={hit5} | GT={pq['gt_dieu']} | TOP5={pq['top5_dieu']}")
            print(f"       Q: {pq['question'][:65]}")


# ════════════════════════════════════════════════════════════
# Main
# ════════════════════════════════════════════════════════════

def main():
    questions = load_questions()
    print(f"Loaded {len(questions)} questions\n")

    # ── Load retrievers ──────────────────────────────────────────
    print("Loading retrievers...")
    t0 = time.time()

    bm25      = BM25Retriever(str(BM25_INDEX))
    e5        = VectorRetriever("intfloat/multilingual-e5-large", "dense_e5", embed_prefix="query: ")
    bge_dense = VectorRetriever("BAAI/bge-m3", "dense_bge", embed_prefix="")
    bge_sparse = BGESparseRetriever()

    print(f"Retrievers loaded in {time.time()-t0:.1f}s\n")

    methods = make_methods(bm25, e5, bge_dense, bge_sparse)

    # ── Load v2 baseline ─────────────────────────────────────────
    v2_results = []
    if RESULTS_V2.exists():
        with open(RESULTS_V2) as f:
            v2_results = json.load(f)

    # ── Run v3 methods ───────────────────────────────────────────
    print("=" * 70)
    print(f"{'Method':<45}  @1      @3      @5")
    print("=" * 70)

    # Print v2 best results for comparison
    for r in v2_results:
        if r["label"] in ("8. E5 + Query Expansion", "10. Weighted RRF (best mix)"):
            print(f"  [v2] {r['label']:<41} @1={r['recall@1']:.0%}  @3={r['recall@3']:.0%}  @5={r['recall@5']:.0%}  ← baseline")
    print("-" * 70)

    v3_results = []
    for label, fn in methods.items():
        result = evaluate_method(fn, questions, label)
        v3_results.append(result)

    # ── Save ─────────────────────────────────────────────────────
    # Save clean version (without per_question for JSON brevity)
    clean_results = []
    for r in v3_results:
        clean_results.append({
            "label":    r["label"],
            "recall@1": r["recall@1"],
            "recall@3": r["recall@3"],
            "recall@5": r["recall@5"],
            "failures": r["failures"],
        })

    with open(RESULTS_V3, "w", encoding="utf-8") as f:
        json.dump(clean_results, f, ensure_ascii=False, indent=2)
    print(f"\nSaved → {RESULTS_V3}")

    # ── Hard case analysis ───────────────────────────────────────
    print_hard_case_analysis(v3_results)

    # ── Summary: improvement over v2 ────────────────────────────
    print("\n" + "=" * 70)
    print("IMPROVEMENT SUMMARY (vs v2 best: @5=90%)")
    print("=" * 70)
    best_v2_5 = 0.90
    for r in clean_results:
        delta5 = r["recall@5"] - best_v2_5
        marker = " ★ NEW BEST" if r["recall@5"] > best_v2_5 else ""
        delta_str = f"{delta5:+.0%}"
        print(f"  {r['label']:<45} @5={r['recall@5']:.0%} ({delta_str}){marker}")


if __name__ == "__main__":
    main()
