"""
Agentic Legal RAG Pipeline v3
==============================
Multi-law: LawClassifier → law_ids → tất cả sub-queries dùng cùng law_ids
"""
from __future__ import annotations
import time
from pathlib import Path

from backend.core.retrieval.base        import RetrievedChunk
from backend.core.retrieval.bm25        import BM25Retriever
from backend.core.retrieval.fusion      import weighted_rrf, chapter_boost_rerank
from backend.core.retrieval.reranker    import BGEReranker
from backend.core.retrieval.query_expansion  import expand_with_intent
from backend.core.retrieval.query_classifier import classify_query
from backend.core.law.classifier        import classify_laws
from backend.core.law.conflict          import resolve as conflict_resolve
from backend.core.law.temporal          import detect_temporal, apply_temporal_filter_to_chunks
from backend.core.pipeline.context_builder import build_context, SYSTEM_PROMPT
from backend.core.pipeline.decomposer   import decompose_query
from backend.core.pipeline.verifier     import verify_context

TOP_K_RETRIEVE = 10
TOP_K_RERANK   = 3
MAX_ROUNDS     = 2


def retrieve_and_rerank(
    query: str,
    bm25: BM25Retriever,
    reranker,
    top_k: int = TOP_K_RERANK,
    law_ids: list[str] | None = None,
    temporal_ctx=None,
):
    intent   = classify_query(query)
    expanded = expand_with_intent(query, intent)

    # BM25 with law_ids filter
    r_bm25 = bm25.search(expanded, top_k=TOP_K_RETRIEVE, law_ids=law_ids)
    if temporal_ctx and temporal_ctx.has_temporal:
        r_bm25 = apply_temporal_filter_to_chunks(r_bm25, temporal_ctx)

    # Vector (optional)
    r_vector: list = []
    try:
        from backend.core.retrieval.vector import VectorRetriever, BGESparseRetriever
        qdrant_filter = None
        if law_ids:
            qdrant_filter = {"must": [{"key": "law_id", "match": {"any": law_ids}}]}

        e5  = VectorRetriever("intfloat/multilingual-e5-large", "dense_e5", embed_prefix="query: ")
        bge = VectorRetriever("BAAI/bge-m3", "dense_bge", embed_prefix="")
        r_e5  = e5.search(expanded, top_k=TOP_K_RETRIEVE, filter=qdrant_filter)
        r_bge = bge.search(expanded, top_k=TOP_K_RETRIEVE, filter=qdrant_filter)
        r_vector = r_e5 + r_bge
    except Exception:
        pass

    # Fusion
    if r_vector:
        if intent["type"] in ("basic_rights", "definition", "coverage"):
            w = [(0.3, r_bm25), (2.0, r_vector[:10]), (1.5, r_vector[10:])]
        else:
            w = [(0.5, r_bm25), (1.5, r_vector[:10]), (2.0, r_vector[10:])]
        fused = weighted_rrf([(r, wt) for wt, r in w], top_k=15)
    else:
        fused = [type("R", (), {"chunk": c, "score": c.score})() for c in r_bm25[:15]]

    if intent.get("boost_early") and intent.get("boost_dieu_range"):
        fused = chapter_boost_rerank(
            fused, boost_dieu_range=intent["boost_dieu_range"],
            boost_factor=2.0, top_k=5,
        )

    if reranker:
        try:
            return reranker.rerank(query, fused, top_k=top_k)
        except Exception:
            pass
    return fused[:top_k]


def run_pipeline(query: str, bm25: BM25Retriever, reranker, client) -> dict:
    t0 = time.time()

    law_ids      = classify_laws(query)
    temporal_ctx = detect_temporal(query)
    sub_queries  = decompose_query(query, client)

    all_chunks:     list = []
    chunk_ids_seen: set  = set()

    for sq in sub_queries:
        results = retrieve_and_rerank(
            sq, bm25=bm25, reranker=reranker,
            top_k=TOP_K_RERANK,
            law_ids=law_ids or None,
            temporal_ctx=temporal_ctx,
        )
        for r in results:
            chunk = getattr(r, "chunk", r)
            cid   = getattr(chunk, "chunk_id", str(id(chunk)))
            if cid not in chunk_ids_seen:
                chunk_ids_seen.add(cid)
                all_chunks.append(chunk)

    sorted_chunks, conflict_notes = conflict_resolve(all_chunks)

    is_sufficient, follow_up = verify_context(query, sorted_chunks, client)
    rounds = 0
    while not is_sufficient and rounds < MAX_ROUNDS and follow_up:
        rounds += 1
        for r in retrieve_and_rerank(follow_up, bm25=bm25, reranker=reranker,
                                      top_k=TOP_K_RERANK, law_ids=law_ids or None):
            chunk = getattr(r, "chunk", r)
            cid   = getattr(chunk, "chunk_id", str(id(chunk)))
            if cid not in chunk_ids_seen:
                chunk_ids_seen.add(cid)
                sorted_chunks.append(chunk)
        sorted_chunks, conflict_notes = conflict_resolve(sorted_chunks)
        is_sufficient, follow_up = verify_context(query, sorted_chunks, client)

    context = build_context(sorted_chunks, conflict_notes=conflict_notes, query=query)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": f"Câu hỏi: {query}\n\nNgữ cảnh pháp lý:\n{context}"},
    ]
    response = client.chat.completions.create(
        model="gpt-4o-mini", messages=messages, temperature=0.1, max_tokens=1500,
    )

    return {
        "query":          query,
        "law_ids":        law_ids,
        "sub_queries":    sub_queries,
        "conflict_notes": [n.note for n in conflict_notes],
        "num_chunks":     len(sorted_chunks),
        "answer":         response.choices[0].message.content,
        "elapsed_s":      round(time.time() - t0, 2),
    }
