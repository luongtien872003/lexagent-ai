"""
Reciprocal Rank Fusion (RRF) — v2
----------------------------------
score(d) = Σ weight_i / (k + rank_i(d))

v2 adds:
- weighted_rrf: mỗi retriever có weight riêng
- chapter_boost_rerank: boost kết quả thuộc chương ưu tiên
- intent_aware_rrf: kết hợp weighted_rrf + chapter boost dựa trên classifier intent
"""

from backend.core.retrieval.base import RetrievedChunk


# ════════════════════════════════════════════════════════════
# RRF cơ bản (giữ nguyên tương thích ngược)
# ════════════════════════════════════════════════════════════

def reciprocal_rank_fusion(
    result_lists: list[list[RetrievedChunk]],
    k: int = 60,
    top_k: int = 10,
) -> list[RetrievedChunk]:
    """Standard RRF — equal weight cho tất cả retrievers."""
    rrf_scores: dict[str, float]          = {}
    chunk_map:  dict[str, RetrievedChunk] = {}

    for ranked_list in result_lists:
        for rank, chunk in enumerate(ranked_list):
            cid = chunk.chunk_id
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
            if cid not in chunk_map or chunk.score > chunk_map[cid].score:
                chunk_map[cid] = chunk

    sorted_ids = sorted(rrf_scores, key=lambda x: rrf_scores[x], reverse=True)
    return _build_results(sorted_ids[:top_k], chunk_map, rrf_scores, source="rrf")


# ════════════════════════════════════════════════════════════
# Weighted RRF
# ════════════════════════════════════════════════════════════

def weighted_rrf(
    result_lists_with_weights: list[tuple[list[RetrievedChunk], float]],
    k: int = 60,
    top_k: int = 10,
) -> list[RetrievedChunk]:
    """
    Weighted RRF: score(d) = Σ weight_i / (k + rank_i(d))

    Args:
        result_lists_with_weights: list of (results, weight) tuples
        k: RRF constant (default 60)
        top_k: số kết quả trả về

    Example:
        results = weighted_rrf([
            (bm25_results,   0.5),
            (e5_results,     1.5),
            (bge_results,    2.0),
            (sparse_results, 1.0),
        ], top_k=5)
    """
    rrf_scores: dict[str, float]          = {}
    chunk_map:  dict[str, RetrievedChunk] = {}

    for ranked_list, weight in result_lists_with_weights:
        for rank, chunk in enumerate(ranked_list):
            cid = chunk.chunk_id
            contribution = weight / (k + rank + 1)
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + contribution
            if cid not in chunk_map or chunk.score > chunk_map[cid].score:
                chunk_map[cid] = chunk

    sorted_ids = sorted(rrf_scores, key=lambda x: rrf_scores[x], reverse=True)
    return _build_results(sorted_ids[:top_k], chunk_map, rrf_scores, source="weighted_rrf")


# ════════════════════════════════════════════════════════════
# Chapter Boost Reranker
# ════════════════════════════════════════════════════════════

def chapter_boost_rerank(
    results: list[RetrievedChunk],
    boost_dieu_range: tuple[int, int] | None = None,
    priority_chapters: list[int] | None = None,
    boost_factor: float = 2.0,
    top_k: int = 5,
) -> list[RetrievedChunk]:
    """
    Post-retrieval reranking: boost chunks thuộc điều/chương ưu tiên.

    Dùng sau weighted_rrf khi intent là "basic_rights" hoặc "definition".

    Args:
        results:           list kết quả từ RRF
        boost_dieu_range:  (min_dieu, max_dieu) — boost chunks trong range này
        priority_chapters: list chương cần boost (alternative to dieu_range)
        boost_factor:      hệ số nhân score (default 2.5)
        top_k:             số kết quả sau boost

    Returns:
        list RetrievedChunk đã rerank, score được cập nhật
    """
    boosted = []
    for chunk in results:
        score = chunk.score

        # Boost theo điều range (precision cao hơn)
        if boost_dieu_range is not None:
            min_d, max_d = boost_dieu_range
            if min_d <= chunk.so_dieu <= max_d:
                score *= boost_factor

        # Boost theo chương (fallback nếu không có dieu_range)
        elif priority_chapters:
            if chunk.chuong_so in priority_chapters:
                score *= boost_factor

        boosted.append(RetrievedChunk(
            chunk_id   = chunk.chunk_id,
            so_dieu    = chunk.so_dieu,
            ten_dieu   = chunk.ten_dieu,
            chuong_so  = chunk.chuong_so,
            ten_chuong = chunk.ten_chuong,
            noi_dung   = chunk.noi_dung,
            score      = score,
            source     = chunk.source + "+boost",
        ))

    # Re-sort theo boosted score
    boosted.sort(key=lambda x: x.score, reverse=True)
    return boosted[:top_k]


# ════════════════════════════════════════════════════════════
# Intent-Aware RRF (full pipeline cho Phase 2)
# ════════════════════════════════════════════════════════════

def intent_aware_rrf(
    result_lists_with_weights: list[tuple[list[RetrievedChunk], float]],
    intent: dict,
    k: int = 60,
    top_k: int = 5,
) -> list[RetrievedChunk]:
    """
    Full pipeline:
    1. Weighted RRF với weights từ caller
    2. Chapter Boost nếu intent có boost_early=True
    3. Return top_k

    Args:
        result_lists_with_weights: [(results, weight), ...]
        intent: dict từ query_classifier.classify_query()
        k, top_k: RRF params
    """
    # Step 1: Weighted RRF (lấy top_k * 3 để có buffer cho boost)
    rrf_results = weighted_rrf(
        result_lists_with_weights,
        k=k,
        top_k=top_k * 3,
    )

    # Step 2: Chapter boost nếu cần
    if intent.get("boost_early") and (
        intent.get("boost_dieu_range") or intent.get("priority_chapters")
    ):
        rrf_results = chapter_boost_rerank(
            results           = rrf_results,
            boost_dieu_range  = intent.get("boost_dieu_range"),
            priority_chapters = intent.get("priority_chapters"),
            boost_factor      = 2.5,
            top_k             = top_k,
        )
    else:
        rrf_results = rrf_results[:top_k]

    return rrf_results


# ════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════

def _build_results(
    sorted_ids: list[str],
    chunk_map:  dict[str, RetrievedChunk],
    scores:     dict[str, float],
    source:     str,
) -> list[RetrievedChunk]:
    results = []
    for cid in sorted_ids:
        c = chunk_map[cid]
        results.append(RetrievedChunk(
            chunk_id   = c.chunk_id,
            so_dieu    = c.so_dieu,
            ten_dieu   = c.ten_dieu,
            chuong_so  = c.chuong_so,
            ten_chuong = c.ten_chuong,
            noi_dung   = c.noi_dung,
            score      = scores[cid],
            source     = source,
        ))
    return results