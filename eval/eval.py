"""
Eval — đo Recall@1, Recall@3, Recall@5 cho từng retriever + RRF fusion.

Chạy:
    python eval.py --bm25 ../indexer/indexes/bm25_10.2012.QH13.pkl
    python eval.py --bm25 ../indexer/indexes/bm25_10.2012.QH13.pkl --retriever bm25
    python eval.py --bm25 ../indexer/indexes/bm25_10.2012.QH13.pkl --retriever all
"""
import sys
import json
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "retriever"))

QUESTIONS_PATH = Path(__file__).parent / "questions.json"
K_VALUES = [1, 3, 5]


def recall_at_k(retrieved_ids, ground_truth_ids, k):
    return 1.0 if set(retrieved_ids[:k]) & set(ground_truth_ids) else 0.0


def evaluate(retriever_fn, questions, label):
    scores   = {k: [] for k in K_VALUES}
    failures = []

    print(f"\n{'='*58}")
    print(f"  {label}")
    print(f"{'='*58}")

    for q in questions:
        qid    = q["id"]
        query  = q["question"]
        gt_ids = q["ground_truth_ids"]
        try:
            results       = retriever_fn(query)
            retrieved_ids = [r.chunk_id for r in results]
            for k in K_VALUES:
                scores[k].append(recall_at_k(retrieved_ids, gt_ids, k))
            h1   = "✓" if recall_at_k(retrieved_ids, gt_ids, 1) else "✗"
            h3   = "✓" if recall_at_k(retrieved_ids, gt_ids, 3) else "✗"
            h5   = "✓" if recall_at_k(retrieved_ids, gt_ids, 5) else "✗"
            top1 = retrieved_ids[0].split("_dieu_")[-1] if retrieved_ids else "N/A"
            print(f"  {qid} @1{h1} @3{h3} @5{h5}  top1=Dieu{top1}  {query[:40]}")
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
        print(f"\n  ⚠ {len(failures)} errors:")
        for f in failures:
            print(f"    {f['qid']}: {f['error']}")
    summary["failures"] = len(failures)
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--retriever", choices=["bm25","e5","bge_dense","bge_sparse","rrf","all"], default="all")
    parser.add_argument("--bm25", default="../indexer/indexes/bm25_10.2012.QH13.pkl")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()

    with open(QUESTIONS_PATH, encoding="utf-8") as f:
        questions = json.load(f)
    print(f"Questions: {len(questions)}")

    run = args.retriever
    all_results = []

    # init retrievers
    bm25_obj = e5_obj = bge_dense_obj = bge_sparse_obj = None

    if run in ("bm25", "rrf", "all"):
        from bm25_retriever import BM25Retriever
        bm25_obj = BM25Retriever(args.bm25)

    if run in ("e5", "rrf", "all"):
        from vector_retriever import VectorRetriever
        e5_obj = VectorRetriever("intfloat/multilingual-e5-large", "dense_e5", "query: ")

    if run in ("bge_dense", "rrf", "all"):
        from vector_retriever import VectorRetriever
        bge_dense_obj = VectorRetriever("BAAI/bge-m3", "dense_bge", "")

    if run in ("bge_sparse", "rrf", "all"):
        from vector_retriever import BGESparseRetriever
        bge_sparse_obj = BGESparseRetriever()

    # eval each
    fns = []
    if bm25_obj:
        fn = lambda q, r=bm25_obj: r.search(q, top_k=args.top_k)
        fns.append((fn, "BM25"))
    if e5_obj:
        fn = lambda q, r=e5_obj: r.search(q, top_k=args.top_k)
        fns.append((fn, "E5 Dense"))
    if bge_dense_obj:
        fn = lambda q, r=bge_dense_obj: r.search(q, top_k=args.top_k)
        fns.append((fn, "BGE-M3 Dense"))
    if bge_sparse_obj:
        fn = lambda q, r=bge_sparse_obj: r.search(q, top_k=args.top_k)
        fns.append((fn, "BGE-M3 Sparse"))

    for fn, label in fns:
        all_results.append(evaluate(fn, questions, label))

    # RRF
    if run in ("rrf", "all") and all([bm25_obj, e5_obj, bge_dense_obj, bge_sparse_obj]):
        from fusion import reciprocal_rank_fusion
        def rrf_fn(q):
            lists = [
                bm25_obj.search(q,       top_k=args.top_k),
                e5_obj.search(q,         top_k=args.top_k),
                bge_dense_obj.search(q,  top_k=args.top_k),
                bge_sparse_obj.search(q, top_k=args.top_k),
            ]
            return reciprocal_rank_fusion(lists, k=60, top_k=args.top_k)
        all_results.append(evaluate(rrf_fn, questions, "RRF Fusion (all 4)"))

    # summary
    if len(all_results) > 1:
        print(f"\n{'='*58}")
        print("  FINAL COMPARISON")
        print(f"{'='*58}")
        print(f"  {'Retriever':<24} {'@1':>6} {'@3':>6} {'@5':>6}")
        print(f"  {'-'*46}")
        for r in all_results:
            print(f"  {r['label']:<24} {r['recall@1']:>6.1%} {r['recall@3']:>6.1%} {r['recall@5']:>6.1%}")
        out = Path(__file__).parent / "eval_results.json"
        with open(out, "w", encoding="utf-8") as f:
            json.dump(all_results, f, ensure_ascii=False, indent=2)
        print(f"\nSaved → {out}")


if __name__ == "__main__":
    main()
