"""
Eval v2 — 5 phương pháp retrieval + weighted RRF + query expansion.

Chạy:
    python eval_v2.py
"""
import sys, json, argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "retriever"))
sys.path.insert(0, str(Path(__file__).parent.parent / "indexer"))

QUESTIONS_PATH = Path(__file__).parent / "questions.json"
K_VALUES = [1, 3, 5]

BM25_STD     = "../indexer/indexes/bm25_10.2012.QH13.pkl"
BM25_BOOST   = "../indexer/indexes/bm25_boosted_10.2012.QH13.pkl"
BM25_TITLE   = "../indexer/indexes/bm25_title_10.2012.QH13.pkl"


def recall_at_k(retrieved, gt, k):
    return 1.0 if set(retrieved[:k]) & set(gt) else 0.0


def evaluate(retriever_fn, questions, label):
    scores   = {k: [] for k in K_VALUES}
    failures = []
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")

    for q in questions:
        qid, query, gt = q["id"], q["question"], q["ground_truth_ids"]
        qtype = q.get("type", "?")
        try:
            results = retriever_fn(query)
            rids    = [r.chunk_id for r in results]
            for k in K_VALUES:
                scores[k].append(recall_at_k(rids, gt, k))
            h1   = "✓" if recall_at_k(rids, gt, 1) else "✗"
            h3   = "✓" if recall_at_k(rids, gt, 3) else "✗"
            h5   = "✓" if recall_at_k(rids, gt, 5) else "✗"
            top1 = rids[0].split("_dieu_")[-1] if rids else "N/A"
            print(f"  {qid}[{qtype[:3]}] @1{h1} @3{h3} @5{h5}  top1=D{top1}  {query[:38]}")
        except Exception as e:
            failures.append({"qid": qid, "error": str(e)})
            for k in K_VALUES:
                scores[k].append(0.0)
            print(f"  {qid} ERROR: {e}")

    print(f"\n  {'Metric':<10} {'Score':>7}   Bar")
    print(f"  {'-'*42}")
    summary = {"label": label}
    for k in K_VALUES:
        avg = sum(scores[k]) / len(scores[k]) if scores[k] else 0.0
        bar = "█" * int(avg * 20) + "░" * (20 - int(avg * 20))
        print(f"  Recall@{k:<4} {avg:>6.1%}   {bar}")
        summary[f"recall@{k}"] = round(avg, 4)
    if failures:
        print(f"\n  ⚠ {len(failures)} errors: {[f['qid'] for f in failures]}")
    summary["failures"] = len(failures)
    return summary


def weighted_rrf(result_lists_weights, top_k=10):
    """RRF với weight khác nhau cho mỗi retriever."""
    from bm25_retriever import RetrievedChunk
    rrf_scores = {}
    chunk_map  = {}
    k = 60
    for ranked_list, weight in result_lists_weights:
        for rank, chunk in enumerate(ranked_list):
            cid = chunk.chunk_id
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + weight / (k + rank + 1)
            if cid not in chunk_map or chunk.score > chunk_map[cid].score:
                chunk_map[cid] = chunk
    sorted_ids = sorted(rrf_scores, key=lambda x: rrf_scores[x], reverse=True)
    results = []
    for cid in sorted_ids[:top_k]:
        c = chunk_map[cid]
        from bm25_retriever import RetrievedChunk
        results.append(RetrievedChunk(
            chunk_id=c.chunk_id, so_dieu=c.so_dieu, ten_dieu=c.ten_dieu,
            chuong_so=c.chuong_so, ten_chuong=c.ten_chuong, noi_dung=c.noi_dung,
            score=rrf_scores[cid], source="weighted_rrf",
        ))
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()
    K = args.top_k

    with open(QUESTIONS_PATH, encoding="utf-8") as f:
        questions = json.load(f)
    print(f"Questions: {len(questions)} ({', '.join(set(q.get('type','?') for q in questions))})")

    from bm25_retriever import BM25Retriever
    from vector_retriever import VectorRetriever, BGESparseRetriever
    from query_expansion import expand_for_bm25, expand_for_vector

    # ── Load all retrievers ────────────────────────────────
    print("\nLoading retrievers...")
    bm25_std   = BM25Retriever(BM25_STD)
    bm25_boost = BM25Retriever(BM25_BOOST)
    bm25_title = BM25Retriever(BM25_TITLE)
    e5         = VectorRetriever("intfloat/multilingual-e5-large", "dense_e5", "query: ")
    bge_dense  = VectorRetriever("BAAI/bge-m3", "dense_bge", "")
    bge_sparse = BGESparseRetriever()
    print("All retrievers loaded ✓")

    all_results = []

    # 1. BM25 Standard (baseline)
    all_results.append(evaluate(
        lambda q: bm25_std.search(q, top_k=K), questions, "1. BM25 Standard"
    ))

    # 2. BM25 Title Boosted
    all_results.append(evaluate(
        lambda q: bm25_boost.search(q, top_k=K), questions, "2. BM25 Title Boosted"
    ))

    # 3. BM25 Title Only
    all_results.append(evaluate(
        lambda q: bm25_title.search(q, top_k=K), questions, "3. BM25 Title Only"
    ))

    # 4. E5 Dense (boosted embedding)
    all_results.append(evaluate(
        lambda q: e5.search(q, top_k=K), questions, "4. E5 Dense (boosted)"
    ))

    # 5. BGE-M3 Dense (boosted embedding)
    all_results.append(evaluate(
        lambda q: bge_dense.search(q, top_k=K), questions, "5. BGE-M3 Dense (boosted)"
    ))

    # 6. BGE-M3 Sparse (boosted embedding)
    all_results.append(evaluate(
        lambda q: bge_sparse.search(q, top_k=K), questions, "6. BGE-M3 Sparse (boosted)"
    ))

    # 7. BM25 Boosted + Query Expansion
    all_results.append(evaluate(
        lambda q: bm25_boost.search(expand_for_bm25(q), top_k=K),
        questions, "7. BM25 Boosted + Query Exp"
    ))

    # 8. E5 + Query Expansion
    all_results.append(evaluate(
        lambda q: e5.search(expand_for_vector(q), top_k=K),
        questions, "8. E5 + Query Expansion"
    ))

    # 9. RRF Equal weights (all 4)
    def rrf_equal(q):
        lists = [(bm25_boost.search(q, top_k=K), 1.0),
                 (e5.search(q, top_k=K),          1.0),
                 (bge_dense.search(q, top_k=K),   1.0),
                 (bge_sparse.search(q, top_k=K),  1.0)]
        return weighted_rrf(lists, top_k=K)
    all_results.append(evaluate(rrf_equal, questions, "9. RRF Equal (all 4)"))

    # 10. Weighted RRF — BGE Dense 2x, BM25 0.5x
    def rrf_weighted(q):
        lists = [(bm25_boost.search(expand_for_bm25(q), top_k=K), 0.5),
                 (e5.search(expand_for_vector(q), top_k=K),        1.5),
                 (bge_dense.search(q, top_k=K),                    2.0),
                 (bge_sparse.search(q, top_k=K),                   1.0),
                 (bm25_title.search(q, top_k=K),                   1.0)]
        return weighted_rrf(lists, top_k=K)
    all_results.append(evaluate(rrf_weighted, questions, "10. Weighted RRF (best mix)"))

    # ── Summary ───────────────────────────────────────────
    print(f"\n{'='*62}")
    print("  FINAL COMPARISON")
    print(f"{'='*62}")
    print(f"  {'Method':<30} {'@1':>6} {'@3':>6} {'@5':>6}")
    print(f"  {'-'*52}")
    best_at5 = 0
    for r in all_results:
        marker = " ★" if r["recall@5"] >= 0.9 else ""
        print(f"  {r['label']:<30} {r['recall@1']:>6.1%} {r['recall@3']:>6.1%} {r['recall@5']:>6.1%}{marker}")
        best_at5 = max(best_at5, r["recall@5"])

    print(f"\n  Best Recall@5: {best_at5:.1%}")
    methods_90 = [r["label"] for r in all_results if r["recall@5"] >= 0.9]
    print(f"  Methods ≥90%@5: {len(methods_90)} — {methods_90}")

    out = Path(__file__).parent / "eval_results_v2.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\nSaved → {out}")


if __name__ == "__main__":
    main()
