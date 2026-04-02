"""
Eval v6 — KG Fixed (hub filter + score threshold)
===================================================
Chỉ chạy 2 variants mới cần test:
  V6-C: M11 + KG (fixed) + Reranker
  V6-D: M11 + Citation + KG (fixed) + Reranker

So sánh với v5 baseline (đọc từ file):
  V5-A: Rnk@1=70%, Rnk@3=95%   ← target cần beat
  V5-B: Rnk@1=60%, Rnk@3=90%
  V5-C: Rnk@1=0%,  Rnk@3=35%   ← cái cần fix
  V5-D: Rnk@1=0%,  Rnk@3=40%   ← cái cần fix

KG fixes:
  hub_threshold=15   — skip entity xuất hiện > 15 điều
  score_threshold=1.5 — chỉ expand nếu score >= 1.5
"""

import sys, json, time
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

BM25_INDEX    = Path(__file__).parent.parent / "indexer/indexes/bm25_10.2012.QH13.pkl"
CITATION_PATH = Path(__file__).parent.parent / "indexer/indexes/citation_graph_10.2012.QH13.json"
KG_PATH       = Path(__file__).parent.parent / "indexer/indexes/kg_10.2012.QH13.json"
QUESTIONS     = Path(__file__).parent / "questions.json"
RESULTS_V5    = Path(__file__).parent / "eval_results_v5.json"
RESULTS_V6    = Path(__file__).parent / "eval_results_v6.json"

HYBRID_ALPHA = 0.5
TOP_RERANK   = 3
TOP_EXPAND   = 3


def retrieve_m11(query, bm25, e5, bge_dense, bge_sparse):
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
                                      boost_factor=2.0, top_k=5)
    else:
        chunks = rrf[:5]
    return chunks, intent


def dedup(chunks):
    seen = {}
    for c in chunks:
        if c.so_dieu not in seen or c.score > seen[c.so_dieu].score:
            seen[c.so_dieu] = c
    return list(seen.values())


def hit(items, gt, k):
    return any(g in {x.so_dieu for x in items[:k]} for g in gt)


def run_variant(label, questions, bm25, e5, bge_dense, bge_sparse,
                reranker, citation=None, kg=None):
    rnk = {1: 0, 3: 0}
    per_q = []
    failures = 0

    for q in questions:
        try:
            top5, intent = retrieve_m11(q["question"], bm25, e5, bge_dense, bge_sparse)

            extra = []
            if citation:
                extra += citation.expand(top5, depth=1, direction="both", max_expand=TOP_EXPAND)
            if kg:
                extra += kg.expand(q["question"], top5, max_expand=TOP_EXPAND)

            candidates = dedup(top5 + extra)
            reranked   = reranker.rerank(q["question"], candidates, intent=intent,
                                         top_k=TOP_RERANK, hybrid_alpha=HYBRID_ALPHA)
            gt = q["ground_truth_dieu"]
            rk1 = hit(reranked, gt, 1)
            rk3 = hit(reranked, gt, 3)
            if rk1: rnk[1] += 1
            if rk3: rnk[3] += 1

            per_q.append({
                "id": q["id"], "gt": gt,
                "top5":     [c.so_dieu for c in top5],
                "expanded": [c.so_dieu for c in extra],
                "reranked": [r.so_dieu for r in reranked],
                "rnk@1": rk1, "rnk@3": rk3,
            })
        except Exception as e:
            print(f"  [ERROR] {q['id']}: {e}")
            failures += 1

    n = len(questions)
    result = {
        "label":    label,
        "rnk@1":    round(rnk[1] / n, 4),
        "rnk@3":    round(rnk[3] / n, 4),
        "failures": failures,
        "per_question": per_q,
    }
    print(f"  {label:<45} Rnk@1={rnk[1]/n:.0%}  Rnk@3={rnk[3]/n:.0%}  failures={failures}")
    return result


def main():
    with open(QUESTIONS, encoding="utf-8") as f:
        questions = json.load(f)

    print("Loading...")
    bm25       = BM25Retriever(str(BM25_INDEX))
    e5         = VectorRetriever("intfloat/multilingual-e5-large", "dense_e5", embed_prefix="query: ")
    bge_dense  = VectorRetriever("BAAI/bge-m3", "dense_bge", embed_prefix="")
    bge_sparse = BGESparseRetriever()
    reranker   = BGEReranker()
    citation   = CitationGraphRetriever(str(CITATION_PATH), str(BM25_INDEX))
    kg         = KGRetriever(str(KG_PATH), str(BM25_INDEX),
                             citation_graph_path=str(CITATION_PATH))
    print()

    # V5 baseline từ file
    v5 = {}
    if RESULTS_V5.exists():
        with open(RESULTS_V5) as f:
            for r in json.load(f):
                v5[r["label"][:4]] = r

    print("=" * 65)
    print(f"{'Variant':<45} {'Rnk@1':<8} {'Rnk@3'}")
    print("=" * 65)
    if "V5-A" in v5:
        print(f"  [v5-A baseline] M11 + Reranker"
              f"{'':>14} {v5['V5-A']['rnk@1']:.0%}     {v5['V5-A']['rnk@3']:.0%}  ← target")
        print(f"  [v5-C broken]   M11 + KG (naive)"
              f"{'':>13} {v5['V5-C']['rnk@1']:.0%}      {v5['V5-C']['rnk@3']:.0%}  ← was broken")
    print("-" * 65)

    results = []

    # V6-C: KG fixed only
    rc = run_variant("V6-C: M11 + KG (fixed) + Reranker",
                     questions, bm25, e5, bge_dense, bge_sparse, reranker,
                     citation=None, kg=kg)
    results.append(rc)

    # V6-D: Citation + KG fixed
    rd = run_variant("V6-D: M11 + Citation + KG (fixed) + Reranker",
                     questions, bm25, e5, bge_dense, bge_sparse, reranker,
                     citation=citation, kg=kg)
    results.append(rd)

    print("=" * 65)

    # So sánh vs V5-A
    base1 = v5.get("V5-A", {}).get("rnk@1", 0.7)
    base3 = v5.get("V5-A", {}).get("rnk@3", 0.95)
    print(f"\n── vs V5-A baseline (Rnk@1={base1:.0%}, Rnk@3={base3:.0%}) ──")
    for r in results:
        d1 = r["rnk@1"] - base1
        d3 = r["rnk@3"] - base3
        star = " ★ IMPROVED" if r["rnk@1"] >= base1 else ""
        print(f"  {r['label']:<45} Rnk@1 {d1:+.0%}  Rnk@3 {d3:+.0%}{star}")

    # Failure breakdown — câu nào vẫn miss
    print(f"\n── Per-question breakdown ──")
    print(f"{'ID':<6} {'GT':<8} {'V6-C @1':<10} {'V6-D @1':<10} {'expanded C':<20} {'expanded D'}")
    print("-" * 80)
    pq_c = {p["id"]: p for p in rc["per_question"]}
    pq_d = {p["id"]: p for p in rd["per_question"]}
    for q in questions:
        qid = q["id"]
        gt  = q["ground_truth_dieu"]
        pc  = pq_c.get(qid, {})
        pd  = pq_d.get(qid, {})
        c1  = "✓" if pc.get("rnk@1") else "✗"
        d1  = "✓" if pd.get("rnk@1") else "✗"
        exp_c = str(pc.get("expanded", []))[:18]
        exp_d = str(pd.get("expanded", []))[:18]
        # chỉ in câu miss ở ít nhất 1 variant
        if not pc.get("rnk@1") or not pd.get("rnk@1"):
            print(f"{qid:<6} {str(gt):<8} {c1:<10} {d1:<10} {exp_c:<20} {exp_d}")

    # Save
    clean = [{"label": r["label"], "rnk@1": r["rnk@1"],
              "rnk@3": r["rnk@3"], "failures": r["failures"]}
             for r in results]
    with open(RESULTS_V6, "w", encoding="utf-8") as f:
        json.dump(clean, f, ensure_ascii=False, indent=2)
    print(f"\nSaved → {RESULTS_V6}")


if __name__ == "__main__":
    main()
