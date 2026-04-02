"""
Eval v5 — Full Pipeline với Graph Expansion
=============================================
So sánh 4 variants để đo impact của từng component:

  V5-A: M11 + Reranker                        (baseline = v4 result)
  V5-B: M11 + Citation Graph + Reranker
  V5-C: M11 + Knowledge Graph + Reranker
  V5-D: M11 + Citation Graph + KG + Reranker  (full pipeline)

Pipeline M11 (giữ nguyên từ v4):
  BM25 + E5 + BGE Dense + BGE Sparse
  → Weighted RRF + Query Expansion + Chapter Boost (boost_factor=2.0)
  → top-5 candidates

Graph Expansion (V5-B/C/D):
  → Citation Graph: expand điều được tham chiếu rõ ràng
  → KG: expand điều liên quan qua entity/relation matching
  → Merge → top-8 candidates (5 gốc + 3 mới từ graph)

Reranker (tất cả variants):
  BGE-reranker-v2-m3, hybrid_alpha=0.5, top_k=3

Output:
  eval_results_v5.json  — summary
  Console: bảng so sánh + per-question breakdown cho failures
"""

import os, sys, json, time
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).parent.parent / "retriever"))
sys.path.insert(0, str(Path(__file__).parent.parent / "indexer"))

from bm25_retriever   import BM25Retriever, RetrievedChunk
from vector_retriever import VectorRetriever, BGESparseRetriever
from query_expansion  import expand_with_intent
from query_classifier import classify_query
from fusion           import weighted_rrf, chapter_boost_rerank
from reranker         import BGEReranker
from graph_retriever  import CitationGraphRetriever
from kg_retriever     import KGRetriever

# ── Paths ─────────────────────────────────────────────────────
BM25_INDEX    = Path(__file__).parent.parent / "indexer/indexes/bm25_10.2012.QH13.pkl"
CITATION_PATH = Path(__file__).parent.parent / "indexer/indexes/citation_graph_10.2012.QH13.json"
KG_PATH       = Path(__file__).parent.parent / "indexer/indexes/kg_10.2012.QH13.json"
QUESTIONS     = Path(__file__).parent / "questions.json"
RESULTS_V4    = Path(__file__).parent / "eval_results_v4.json"
RESULTS_V5    = Path(__file__).parent / "eval_results_v5.json"

HYBRID_ALPHA = 0.5
TOP_RETRIEVE = 5
TOP_EXPAND   = 3    # max chunks thêm từ graph
TOP_RERANK   = 3


# ════════════════════════════════════════════════════════════
# Core retrieve — M11 pipeline (giữ nguyên từ v4)
# ════════════════════════════════════════════════════════════

def retrieve_m11(query, bm25, e5, bge_dense, bge_sparse):
    """M11: Weighted RRF + Query Expansion + Chapter Boost."""
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
        chunks = chapter_boost_rerank(
            rrf, boost_dieu_range=intent["boost_dieu_range"],
            boost_factor=2.0, top_k=TOP_RETRIEVE,
        )
    else:
        chunks = rrf[:TOP_RETRIEVE]

    return chunks, intent


def dedup_chunks(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    """Dedup theo so_dieu, giữ chunk có score cao nhất."""
    seen = {}
    for c in chunks:
        if c.so_dieu not in seen or c.score > seen[c.so_dieu].score:
            seen[c.so_dieu] = c
    return list(seen.values())


# ════════════════════════════════════════════════════════════
# Recall helpers
# ════════════════════════════════════════════════════════════

def hit(items, gt, k):
    return any(g in {x.so_dieu for x in items[:k]} for g in gt)


# ════════════════════════════════════════════════════════════
# Evaluate 1 variant
# ════════════════════════════════════════════════════════════

def evaluate_variant(
    label:     str,
    questions: list,
    bm25, e5, bge_dense, bge_sparse,
    reranker:  BGEReranker,
    citation_graph = None,
    kg_retriever   = None,
    verbose:   bool = True,
) -> dict:
    ret_hits  = {1: 0, 3: 0, 5: 0}
    rnk_hits  = {1: 0, 3: 0}
    failures  = 0
    per_q     = []

    for q in questions:
        try:
            # Step 1: M11 retrieve
            top5, intent = retrieve_m11(
                q["question"], bm25, e5, bge_dense, bge_sparse
            )

            # Step 2: Graph expand (nếu có)
            extra = []
            if citation_graph:
                extra += citation_graph.expand(top5, depth=1, direction="both",
                                               max_expand=TOP_EXPAND)
            if kg_retriever:
                kg_extra = kg_retriever.expand(q["question"], top5,
                                               max_expand=TOP_EXPAND)
                extra += kg_extra

            # Merge + dedup
            all_candidates = dedup_chunks(top5 + extra)

            # Step 3: Rerank
            reranked = reranker.rerank(
                q["question"], all_candidates,
                intent=intent, top_k=TOP_RERANK, hybrid_alpha=HYBRID_ALPHA,
            )

            gt = q["ground_truth_dieu"]

            # Retrieval metrics (trên top5 gốc)
            r1 = hit(top5, gt, 1)
            r3 = hit(top5, gt, 3)
            r5 = hit(top5, gt, 5)
            # Sau expand (trước rerank)
            r5_exp = hit(all_candidates, gt, 5) if extra else r5
            if r1: ret_hits[1] += 1
            if r3: ret_hits[3] += 1
            if r5: ret_hits[5] += 1

            # Rerank metrics
            rk1 = hit(reranked, gt, 1)
            rk3 = hit(reranked, gt, 3)
            if rk1: rnk_hits[1] += 1
            if rk3: rnk_hits[3] += 1

            per_q.append({
                "id":       q["id"],
                "type":     q["type"],
                "question": q["question"][:55],
                "gt":       gt,
                "top5":     [c.so_dieu for c in top5],
                "expanded": [c.so_dieu for c in extra],
                "reranked": [r.so_dieu for r in reranked],
                "ret@1": r1, "ret@5": r5, "ret@5_exp": r5_exp,
                "rnk@1": rk1, "rnk@3": rk3,
            })

        except Exception as e:
            print(f"  [ERROR] {q['id']}: {e}")
            failures += 1

    n = len(questions)
    result = {
        "label":    label,
        "ret@1":    round(ret_hits[1] / n, 4),
        "ret@3":    round(ret_hits[3] / n, 4),
        "ret@5":    round(ret_hits[5] / n, 4),
        "rnk@1":    round(rnk_hits[1] / n, 4),
        "rnk@3":    round(rnk_hits[3] / n, 4),
        "failures": failures,
        "per_question": per_q,
    }

    if verbose:
        print(f"  {label:<45} "
              f"Ret@5={ret_hits[5]/n:.0%} "
              f"Rnk@1={rnk_hits[1]/n:.0%} "
              f"Rnk@3={rnk_hits[3]/n:.0%}")

    return result


# ════════════════════════════════════════════════════════════
# Failure analysis
# ════════════════════════════════════════════════════════════

def print_failure_analysis(results: list[dict]):
    print("\n" + "=" * 72)
    print("FAILURE ANALYSIS — câu nào vẫn miss @1 sau rerank")
    print("=" * 72)

    # Tìm câu miss ở tất cả variants
    all_ids = {pq["id"] for pq in results[0]["per_question"]}
    for qid in sorted(all_ids):
        row = {}
        for r in results:
            pq = next((p for p in r["per_question"] if p["id"] == qid), None)
            if pq:
                row[r["label"][:10]] = "✓" if pq["rnk@1"] else "✗"

        if any(v == "✗" for v in row.values()):
            pq_base = next(p for p in results[0]["per_question"] if p["id"] == qid)
            print(f"\n[{qid}] {pq_base['question'][:60]}...")
            print(f"  GT={pq_base['gt']}")
            for r in results:
                pq = next((p for p in r["per_question"] if p["id"] == qid), None)
                if pq:
                    rnk1 = "✓" if pq["rnk@1"] else "✗"
                    exp  = pq["expanded"][:3] if pq["expanded"] else []
                    print(f"  [{r['label'][:35]:<35}] "
                          f"Rnk@1={rnk1} | top5={pq['top5']} | expand={exp} | reranked={pq['reranked']}")


# ════════════════════════════════════════════════════════════
# Main
# ════════════════════════════════════════════════════════════

def main():
    with open(QUESTIONS, encoding="utf-8") as f:
        questions = json.load(f)
    print(f"Loaded {len(questions)} questions\n")

    # ── Load all components ──────────────────────────────────
    print("Loading retrievers...")
    bm25       = BM25Retriever(str(BM25_INDEX))
    e5         = VectorRetriever("intfloat/multilingual-e5-large", "dense_e5", embed_prefix="query: ")
    bge_dense  = VectorRetriever("BAAI/bge-m3", "dense_bge", embed_prefix="")
    bge_sparse = BGESparseRetriever()
    reranker   = BGEReranker()

    # Citation Graph
    citation = None
    if CITATION_PATH.exists():
        citation = CitationGraphRetriever(str(CITATION_PATH), str(BM25_INDEX))
        print(f"[Citation] Loaded")
    else:
        print("[Citation] Not found — skip")

    # Knowledge Graph
    kg = None
    if KG_PATH.exists():
        kg = KGRetriever(str(KG_PATH), str(BM25_INDEX),
                         citation_graph_path=str(CITATION_PATH) if CITATION_PATH.exists() else None)
        print(f"[KG] Loaded")
    else:
        print("[KG] Not found — skip")

    print()

    # ── Load v4 baseline từ file ─────────────────────────────
    v4_ret1 = v4_rnk1 = v4_rnk3 = "N/A"
    if RESULTS_V4.exists():
        with open(RESULTS_V4) as f:
            v4 = json.load(f)
        v4_ret1 = f"{v4['retriever']['recall@1']:.0%}"
        v4_rnk1 = f"{v4['reranker']['recall@1']:.0%}"
        v4_rnk3 = f"{v4['reranker']['recall@3']:.0%}"

    # ── Run variants ─────────────────────────────────────────
    print("=" * 72)
    print(f"{'Variant':<45} {'Ret@5':<8} {'Rnk@1':<8} {'Rnk@3'}")
    print("=" * 72)
    print(f"  [v4 baseline from file]"
          f"{'':>22} ret@1={v4_ret1}  rnk@1={v4_rnk1}  rnk@3={v4_rnk3}")
    print("-" * 72)

    all_results = []

    # V5-A: M11 + Reranker (re-run để confirm)
    r_a = evaluate_variant(
        "V5-A: M11 + Reranker",
        questions, bm25, e5, bge_dense, bge_sparse, reranker,
        citation_graph=None, kg_retriever=None,
    )
    all_results.append(r_a)

    # V5-B: M11 + Citation + Reranker
    if citation:
        r_b = evaluate_variant(
            "V5-B: M11 + Citation + Reranker",
            questions, bm25, e5, bge_dense, bge_sparse, reranker,
            citation_graph=citation, kg_retriever=None,
        )
        all_results.append(r_b)

    # V5-C: M11 + KG + Reranker
    if kg:
        r_c = evaluate_variant(
            "V5-C: M11 + KG + Reranker",
            questions, bm25, e5, bge_dense, bge_sparse, reranker,
            citation_graph=None, kg_retriever=kg,
        )
        all_results.append(r_c)

    # V5-D: M11 + Citation + KG + Reranker (full)
    if citation and kg:
        r_d = evaluate_variant(
            "V5-D: M11 + Citation + KG + Reranker (FULL)",
            questions, bm25, e5, bge_dense, bge_sparse, reranker,
            citation_graph=citation, kg_retriever=kg,
        )
        all_results.append(r_d)

    # ── Summary table ────────────────────────────────────────
    print("=" * 72)
    print("\n── Improvement vs V5-A baseline ──")
    base_rnk1 = all_results[0]["rnk@1"]
    base_rnk3 = all_results[0]["rnk@3"]
    for r in all_results:
        d1 = r["rnk@1"] - base_rnk1
        d3 = r["rnk@3"] - base_rnk3
        best = " ★" if r["rnk@1"] > base_rnk1 or r["rnk@3"] > base_rnk3 else ""
        print(f"  {r['label']:<45} "
              f"Rnk@1={r['rnk@1']:.0%} ({d1:+.0%})  "
              f"Rnk@3={r['rnk@3']:.0%} ({d3:+.0%}){best}")

    # ── Failure analysis ─────────────────────────────────────
    print_failure_analysis(all_results)

    # ── Save ─────────────────────────────────────────────────
    clean = []
    for r in all_results:
        clean.append({
            "label":    r["label"],
            "ret@1":    r["ret@1"],
            "ret@3":    r["ret@3"],
            "ret@5":    r["ret@5"],
            "rnk@1":    r["rnk@1"],
            "rnk@3":    r["rnk@3"],
            "failures": r["failures"],
        })
    with open(RESULTS_V5, "w", encoding="utf-8") as f:
        json.dump(clean, f, ensure_ascii=False, indent=2)
    print(f"\nSaved → {RESULTS_V5}")


if __name__ == "__main__":
    main()
