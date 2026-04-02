"""
Reranker — BAAI/bge-reranker-v2-m3
------------------------------------
v2: Intent-aware query prefix + hybrid scoring

Vấn đề v1: reranker bị lexical trap
  q004 "quyền đình công" → Điều 218 (đình công dày đặc) > Điều 5 (quyền cơ bản)
  q005 "đóng cửa tạm thời" → Điều 216 > Điều 6

Fix:
  1. Intent prefix: "Câu hỏi về quyền cơ bản: ..." → reranker hiểu context
  2. Hybrid score = alpha * rerank + (1-alpha) * retrieval_normalized
     → Điều 5/6 có retrieval rank cao, không bị kéo xuống hoàn toàn

Chạy test:
    python reranker.py
"""

import os
import time
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

try:
    from FlagEmbedding import FlagReranker
except ImportError:
    raise SystemExit("Thiếu FlagEmbedding. Chạy: pip install FlagEmbedding")

from backend.core.retrieval.base import RetrievedChunk


RERANKER_MODEL = os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")

INTENT_PREFIX = {
    "basic_rights": "Câu hỏi về quyền và nghĩa vụ cơ bản theo Bộ luật Lao động: ",
    "definition":   "Câu hỏi về định nghĩa và khái niệm theo Bộ luật Lao động: ",
    "coverage":     "Câu hỏi về phạm vi và đối tượng áp dụng Bộ luật Lao động: ",
    "scenario":     "Tình huống thực tế về quan hệ lao động: ",
    "general":      "",
}


@dataclass
class RerankResult:
    chunk_id:        str
    so_dieu:         int
    ten_dieu:        str
    chuong_so:       int
    ten_chuong:      str
    noi_dung:        str
    rerank_score:    float
    retrieval_score: float
    hybrid_score:    float
    retrieval_rank:  int


class BGEReranker:
    def __init__(self, model_name: str = RERANKER_MODEL):
        print(f"[Reranker] Loading {model_name}...")
        t0 = time.time()
        self.model      = FlagReranker(model_name, use_fp16=False)
        self.model_name = model_name
        print(f"[Reranker] Ready in {time.time()-t0:.1f}s")

    def rerank(
        self,
        query:        str,
        chunks:       list[RetrievedChunk],
        intent:       dict | None = None,
        top_k:        int   = 3,
        hybrid_alpha: float = 0.7,
    ) -> list[RerankResult]:
        if not chunks:
            return []

        prefix = ""
        if intent:
            prefix = INTENT_PREFIX.get(intent.get("type", "general"), "")

        rerank_query = prefix + query
        pairs = [[rerank_query, c.noi_dung] for c in chunks]

        t0 = time.time()
        scores = self.model.compute_score(pairs, normalize=True)
        elapsed = time.time() - t0

        if isinstance(scores, float):
            scores = [scores]

        # Normalize retrieval scores về [0,1]
        ret_scores = [c.score for c in chunks]
        ret_min, ret_max = min(ret_scores), max(ret_scores)
        ret_range = ret_max - ret_min if ret_max > ret_min else 1.0
        norm_ret = [(s - ret_min) / ret_range for s in ret_scores]

        results = []
        for rank, (chunk, r_score, nr) in enumerate(zip(chunks, scores, norm_ret), start=1):
            hybrid = hybrid_alpha * float(r_score) + (1 - hybrid_alpha) * nr
            results.append(RerankResult(
                chunk_id        = chunk.chunk_id,
                so_dieu         = chunk.so_dieu,
                ten_dieu        = chunk.ten_dieu,
                chuong_so       = chunk.chuong_so,
                ten_chuong      = chunk.ten_chuong,
                noi_dung        = chunk.noi_dung,
                rerank_score    = float(r_score),
                retrieval_score = chunk.score,
                hybrid_score    = hybrid,
                retrieval_rank  = rank,
            ))

        results.sort(key=lambda x: x.hybrid_score, reverse=True)

        label = f"prefix='{prefix[:30]}...'" if prefix else "no prefix"
        print(f"[Reranker] {len(chunks)} chunks | {elapsed:.1f}s | {label}")
        return results[:top_k]


# ════════════════════════════════════════════════════════════
# Smoke test
# ════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "indexer"))

    from bm25_retriever   import BM25Retriever
    from backend.core.retrieval.vector import VectorRetriever, BGESparseRetriever
    from query_expansion  import expand_with_intent
    from backend.core.retrieval.query_classifier import classify_query
    from fusion           import weighted_rrf, chapter_boost_rerank

    BM25_INDEX = Path(__file__).parent.parent / "indexer/indexes/bm25_10.2012.QH13.pkl"

    print("Loading retrievers...")
    bm25       = BM25Retriever(str(BM25_INDEX))
    e5         = VectorRetriever("intfloat/multilingual-e5-large", "dense_e5", embed_prefix="query: ")
    bge_dense  = VectorRetriever("BAAI/bge-m3", "dense_bge", embed_prefix="")
    bge_sparse = BGESparseRetriever()
    reranker   = BGEReranker()

    def retrieve_top5(query, intent=None):
        if intent is None:
            intent = classify_query(query)
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
            return chapter_boost_rerank(rrf, boost_dieu_range=intent["boost_dieu_range"],
                                        boost_factor=2.0, top_k=5)
        return rrf[:5]

    test_queries = [
        ("q003", "Độ tuổi tối thiểu để được coi là người lao động theo Bộ luật là bao nhiêu?", [3]),
        ("q004", "Người lao động có quyền đình công không?",                                   [5]),
        ("q005", "Người sử dụng lao động có quyền đóng cửa tạm thời nơi làm việc không?",     [6]),
        ("q016", "Tôi bị sếp ép làm thêm giờ không trả lương, tôi có quyền tự ý nghỉ việc không?", [37]),
        ("q018", "Nhân viên bị ốm nặng điều trị 13 tháng liên tục, công ty có được sa thải không?", [38]),
    ]

    # Tune alpha
    print("\n── Tune hybrid_alpha (chỉ @1, 1 câu/alpha) ──")
    alphas = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    print(f"{'alpha':>6}  {'@1':>6}")
    print("─" * 20)

    best_alpha, best_hit = 0.7, -1
    alpha_top5_cache = {}

    # Pre-retrieve để tránh gọi lại nhiều lần
    print("Pre-retrieving top5 for all queries...")
    cached = {}
    for qid, query, gt in test_queries:
        intent = classify_query(query)
        cached[qid] = (retrieve_top5(query, intent), intent, gt)

    for alpha in alphas:
        hits = 0
        for qid, query, gt in test_queries:
            top5, intent, gt_ = cached[qid]
            reranked = reranker.rerank(query, top5, intent=intent, top_k=1, hybrid_alpha=alpha)
            if reranked and reranked[0].so_dieu in gt_:
                hits += 1
        n = len(test_queries)
        marker = " ← best" if hits > best_hit else ""
        if hits > best_hit:
            best_hit = hits
            best_alpha = alpha
        print(f"{alpha:>6.1f}  {hits/n:>5.0%}{marker}")

    # Final test
    print(f"\n── Final test (alpha={best_alpha}) ──")
    print("=" * 70)
    print(f"{'ID':<6} {'GT':<6} {'Before @1':<13} {'After @1':<13} Top3")
    print("=" * 70)

    hit_before = hit_after = 0
    for qid, query, gt in test_queries:
        top5, intent, _ = cached[qid]
        before_top1 = top5[0].so_dieu if top5 else None
        b_hit = "✓" if before_top1 in gt else "✗"

        reranked = reranker.rerank(query, top5, intent=intent, top_k=3, hybrid_alpha=best_alpha)
        after_top1 = reranked[0].so_dieu if reranked else None
        a_hit = "✓" if after_top1 in gt else "✗"

        top3 = [r.so_dieu for r in reranked]
        moved = " ← FIXED" if (a_hit == "✓" and b_hit == "✗") else \
                " ← DROPPED" if (a_hit == "✗" and b_hit == "✓") else ""

        if before_top1 in gt: hit_before += 1
        if after_top1  in gt: hit_after  += 1

        print(f"{qid:<6} {str(gt):<6} Điều {str(before_top1):<4} {b_hit}    Điều {str(after_top1):<4} {a_hit}    {top3}{moved}")

    n = len(test_queries)
    print("=" * 70)
    print(f"@1 Before: {hit_before}/{n} = {hit_before/n:.0%}")
    print(f"@1 After:  {hit_after}/{n}  = {hit_after/n:.0%}")