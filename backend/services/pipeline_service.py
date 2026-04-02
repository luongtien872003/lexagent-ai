"""
Pipeline Service — production-ready.

FIXES IN THIS VERSION:
  Fix 1 — Agentic pipeline blocked the event loop.
           _retrieve_and_rerank is CPU/IO-bound (embedding, BM25 search,
           neural reranker). Calling it directly inside async def froze the
           event loop during retrieval — no SSE heartbeats, no other requests.
           Every blocking call is now wrapped in run_in_executor.

  Fix 2 — Dedup used rerank_score, but reranker.rerank() sorts by hybrid_score
           (reranker.py line 115). The "best" document kept during dedup could
           be wrong. Both dedup comparison and sort key now use hybrid_score.

  Fix 3 — _get_conversation_history read msg.content which stores the raw LLM
           JSON string ({"summary":"...", "sections":[...]}) as assistant content.
           Passing 300 chars of raw JSON as "history" to the next LLM call is
           useless noise. Router now extracts the summary string for assistant
           turns so history reads naturally.

  Fix 4 — asyncio.get_event_loop() is deprecated in Python 3.10+ and raises
           RuntimeError in 3.12 without a running loop. All calls replaced with
           asyncio.get_running_loop().

  Fix 5 — Chitchat fast path: greetings / small talk no longer trigger
           retrieval + reranker + LLM with full legal context. Detected by
           keyword check (_is_chitchat) — zero additional LLM calls. Response
           is streamed with the same phrase-delay feel as normal answers.
"""
import sys
import asyncio
import random
import time
from pathlib import Path
from typing import Callable, Awaitable

ROOT_DIR = Path(__file__).parent.parent.parent




from backend.app.config import (
    BM25_INDEX, BM25_INDEX_DIR, KG_PATH, CITATION_PATH,
    HYBRID_ALPHA, OPENAI_API_KEY, LLM_MODEL,
    MAX_AGENTIC_ROUNDS, get_model, get_max_tokens, MODEL_TIERS,
)

StatusCallback   = Callable[..., Awaitable[None]] | None
TokenCallback    = Callable[[str], Awaitable[None]] | None
SectionsCallback = Callable[[list], Awaitable[None]] | None

# ── Chitchat system prompt ───────────────────────────────────────────────────

_CHITCHAT_SYSTEM = (
    "Bạn là LexAgent, trợ lý tư vấn pháp luật lao động Việt Nam thân thiện. "
    "Khi người dùng chào hỏi hoặc giao tiếp thông thường, hãy chào lại ngắn gọn "
    "và nhắc rằng bạn có thể giúp giải đáp các câu hỏi về Bộ luật Lao động 10/2012/QH13. "
    "Trả lời bằng JSON thuần túy, không markdown:\n"
    "{\"summary\": \"<câu trả lời ngắn, thân thiện>\", \"sections\": []}"
)

# ── Phrase streaming ─────────────────────────────────────────────────────────

def _split_into_phrases(text: str) -> list[str]:
    words = text.split()
    if not words:
        return []
    phrases, i = [], 0
    while i < len(words):
        size  = 3 if len(words) - i <= 4 else random.randint(3, 5)
        chunk = " ".join(words[i:i + size])
        phrases.append(chunk if i == 0 else " " + chunk)
        i += size
    return phrases


def _phrase_delay(phrase: str) -> float:
    s = phrase.strip()
    n = len(s)
    base = 0.040 if n <= 8 else 0.050 if n <= 15 else 0.060 if n <= 25 else 0.070
    if s and s[-1] in ".!?;": base += 0.022
    elif s and s[-1] == ",":  base += 0.010
    return max(0.030, base + random.uniform(-0.008, 0.008))


# ── PipelineService ──────────────────────────────────────────────────────────

class PipelineService:
    def __init__(self):
        self._ready      = False
        self._components = None
        self._start_time = time.time()

    @property
    def ready(self) -> bool:
        return self._ready

    @property
    def uptime(self) -> float:
        return time.time() - self._start_time

    async def initialize(self):
        # Fix 4: use get_running_loop() inside async context
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._load_models)

    def _load_models(self):
        print("[PipelineService] Loading models...")
        t0 = time.time()

        from backend.core.retrieval.bm25 import BM25Retriever
        from backend.core.retrieval.vector import VectorRetriever, BGESparseRetriever
        from backend.core.retrieval.reranker import BGEReranker
        from openai           import OpenAI

        # Multi-law: load all pkl from dir; fallback to single file
        _bm25_path = str(BM25_INDEX_DIR) if BM25_INDEX_DIR.exists() else str(BM25_INDEX)
        bm25       = BM25Retriever(_bm25_path)
        e5         = VectorRetriever("intfloat/multilingual-e5-large", "dense_e5", embed_prefix="query: ")
        bge_dense  = VectorRetriever("BAAI/bge-m3", "dense_bge", embed_prefix="")
        bge_sparse = BGESparseRetriever()
        reranker   = BGEReranker()

        kg = None
        if KG_PATH.exists():
            from backend.core.retrieval.kg_retriever import KGRetriever
            kg = KGRetriever(
                str(KG_PATH), str(BM25_INDEX),
                citation_graph_path=str(CITATION_PATH) if CITATION_PATH.exists() else None,
            )

        self._components = {
            "bm25": bm25, "e5": e5, "bge_dense": bge_dense,
            "bge_sparse": bge_sparse, "reranker": reranker,
            "kg": kg, "llm": OpenAI(api_key=OPENAI_API_KEY),
        }
        self._ready = True
        print(f"[PipelineService] Ready in {time.time()-t0:.1f}s ✓")

    # ── Chitchat detection ────────────────────────────────────────────────────

    def _is_chitchat(self, question: str) -> bool:
        """
        Fast keyword-only check — zero LLM calls.
        Returns True for greetings, thanks, or very short social messages
        that don't need retrieval.
        """
        q = question.strip().lower()
        GREETINGS = [
            "xin chào", "chào bạn", "chào", "hello", "hi", "hey", "alo",
            "cảm ơn", "cảm ơn bạn", "cảm ơn nhiều", "thanks", "thank you",
            "ok", "được rồi", "tốt lắm", "hay quá", "ổn rồi", "tạm biệt",
            "bạn là ai", "bạn làm được gì", "bạn có thể làm gì",
        ]
        return (
            any(q.startswith(g) or q == g for g in GREETINGS)
            and len(q) < 80
        )

    # ── Standard pipeline ─────────────────────────────────────────────────────

    async def query(
        self,
        question:             str,
        mode:                 str = "standard",
        model_tier:           str = "fast",
        on_status:            StatusCallback   = None,
        conversation_history: list[dict] | None = None,
    ) -> dict:
        if not self._ready:
            raise RuntimeError("Pipeline not initialized yet")
        loop = asyncio.get_running_loop()   # Fix 4

        # Fix 5: chitchat fast path — skip retrieval entirely
        if self._is_chitchat(question):
            if on_status:
                await on_status("generating", "Đang soạn phản hồi...")
            raw, structured = await self._chitchat_response(question, loop)
            return {
                "answer": raw, "structured": structured,
                "citations": [], "intent": "chitchat", "pipeline": mode,
                "retrieval_top5": [], "reranked_top3": [],
            }

        if mode == "agentic":
            return await self._agentic_query(
                question, model_tier=model_tier, on_status=on_status,
                conversation_history=conversation_history, loop=loop,
            )

        if on_status:
            await on_status("classifying", "Đang phân tích câu hỏi và xác định loại vấn đề pháp lý...")

        from backend.core.retrieval.query_classifier import classify_query
        from backend.core.retrieval.query_expansion import expand_with_intent
        intent   = classify_query(question)
        expanded = expand_with_intent(question, intent)

        if on_status:
            await on_status("retrieving", "Đang tìm kiếm trong cơ sở dữ liệu điều luật...")

        reranked, top5 = await loop.run_in_executor(
            None, self._retrieve_and_rerank, question, expanded, intent
        )

        if on_status:
            arts = ", ".join(f"Điều {r.so_dieu}" for r in reranked[:3])
            await on_status("reranking", f"Đã chọn: {arts} — độ liên quan cao nhất")

        if on_status:
            arts_g = ", ".join(f"Điều {r.so_dieu}" for r in merged[:3])
            await on_status("generating", f"Tổng hợp từ {arts_g}", "", True)

        raw, structured = await loop.run_in_executor(
            None, self._generate, question, reranked, conversation_history, model_tier
        )

        return {
            "answer": raw, "structured": structured,
            "citations": self._build_citations(reranked, structured),
            "intent": intent.get("type", "general"), "pipeline": mode,
            "retrieval_top5": top5, "reranked_top3": [r.so_dieu for r in reranked[:3]],
            "model_tier": model_tier,
        }

    async def query_stream(
        self,
        question:             str,
        mode:                 str = "standard",
        model_tier:           str = "fast",
        on_status:            StatusCallback   = None,
        on_token:             TokenCallback    = None,
        on_sections:          SectionsCallback = None,
        conversation_history: list[dict] | None = None,
    ) -> dict:
        if not self._ready:
            raise RuntimeError("Pipeline not initialized yet")
        loop = asyncio.get_running_loop()   # Fix 4

        # Chitchat fast path — NO status events emitted → tracker stays invisible on frontend
        if self._is_chitchat(question):
            raw, structured = await self._chitchat_stream(question, loop, on_token)
            return {
                "answer": raw, "structured": structured,
                "citations": [], "intent": "chitchat", "pipeline": mode,
                "retrieval_top5": [], "reranked_top3": [],
            }

        if mode == "agentic":
            return await self._agentic_query_stream(
                question, model_tier=model_tier,
                on_status=on_status, on_token=on_token, on_sections=on_sections,
                conversation_history=conversation_history, loop=loop,
            )

        if on_status:
            await on_status("classifying", "Đang hiểu câu hỏi và xác định vấn đề pháp lý...")

        from backend.core.retrieval.query_classifier import classify_query
        from backend.core.retrieval.query_expansion import expand_with_intent
        intent   = classify_query(question)
        expanded = expand_with_intent(question, intent)

        # Progressive retrieval — each retriever emits its own status update
        reranked, top5 = await self._retrieve_progressive_stream(
            question, expanded, intent, on_status, loop
        )

        if on_status:
            arts = ", ".join(f"Điều {r.so_dieu}" for r in reranked[:3])
            await on_status("reranking", f"Đã xác định điều luật phù hợp nhất: {arts}")

        if on_status:
            await on_status("generating", "Đang soạn câu trả lời dựa trên điều luật...")

        raw, structured = await self._stream_generate(
            question, reranked, on_token, on_sections, conversation_history, model_tier
        )

        return {
            "answer": raw, "structured": structured,
            "citations": self._build_citations(reranked, structured),
            "intent": intent.get("type", "general"), "pipeline": mode,
            "retrieval_top5": top5, "reranked_top3": [r.so_dieu for r in reranked[:3]],
            "model_tier": model_tier,
        }

    # ── Agentic pipeline ──────────────────────────────────────────────────────

    async def _agentic_query(
        self,
        question:             str,
        model_tier:           str = "fast",
        on_status:            StatusCallback   = None,
        conversation_history: list[dict] | None = None,
        loop=None,
    ) -> dict:
        if loop is None:
            loop = asyncio.get_running_loop()

        from backend.core.pipeline.decomposer import decompose_query
        from backend.core.pipeline.verifier import verify_context
        from backend.core.retrieval.query_classifier import classify_query
        from backend.core.retrieval.query_expansion import expand_with_intent

        if on_status:
            await on_status("classifying", "Đang phân tích và tách câu hỏi thành các vấn đề độc lập...")

        sub_queries = await loop.run_in_executor(
            None, decompose_query, self._components["llm"], question
        )

        if on_status:
            n = len(sub_queries)
            meta_subs = "\n".join(f"{i+1}. {sq}" for i, sq in enumerate(sub_queries))
            lbl = f"Tách thành {n} vấn đề" if n > 1 else "1 vấn đề pháp lý"
            await on_status("classifying", lbl, meta_subs, False)

        all_reranked = []
        for i, sq in enumerate(sub_queries):
            intent   = classify_query(sq)
            expanded = expand_with_intent(sq, intent)
            if on_status:
                short = sq[:48] + ("..." if len(sq) > 48 else "")
                lbl2 = f"Tìm kiếm #{i+1}: {short}" if len(sub_queries) > 1 else short
                await on_status("retrieving", lbl2, "", True)
            results, _ = await self._retrieve_progressive_stream(
                sq, expanded, intent, on_status, loop, first_emit=False
            )
            all_reranked.extend(results)

        merged = _dedup_by_hybrid(all_reranked)

        rounds = 0
        while rounds < MAX_AGENTIC_ROUNDS:
            verify = await loop.run_in_executor(
                None, verify_context, self._components["llm"], question, merged[:5]
            )

            if on_status:
                if verify.sufficient:
                    arts = ", ".join(f"Điều {r.so_dieu}" for r in merged[:3])
                    found_meta = "\n".join(
                        f"✓ Điều {r.so_dieu} — {r.ten_dieu[:50]}" for r in merged[:3]
                    )
                    await on_status("reranking", f"Đủ thông tin — {arts}", found_meta, True)
                else:
                    followup_info = f"\nTìm thêm: {verify.follow_up[:100]}" if verify.follow_up else ""
                    await on_status("reranking", "Chưa đủ — tìm bổ sung...",
                                    (verify.missing or "Thiếu thông tin")[:200] + followup_info, True)

            if verify.sufficient or not verify.follow_up:
                break

            intent       = classify_query(verify.follow_up)
            expanded     = expand_with_intent(verify.follow_up, intent)
            if on_status:
                await on_status("retrieving", f"Bổ sung: {verify.follow_up[:45]}...", "", True)
            follow, _ = await self._retrieve_progressive_stream(
                verify.follow_up, expanded, intent, on_status, loop, first_emit=False
            )
            merged = _dedup_by_hybrid(merged + follow)
            rounds += 1

        if on_status:
            arts_g = ", ".join(f"Điều {r.so_dieu}" for r in merged[:3])
            await on_status("generating", f"Tổng hợp từ {arts_g}", "", True)

        raw, structured = await loop.run_in_executor(
            None, self._generate, question, merged[:3], conversation_history, model_tier
        )

        return {
            "answer": raw, "structured": structured,
            "citations": self._build_citations(merged[:3], structured),
            "intent": "agentic", "pipeline": "agentic",
            "retrieval_top5": [r.so_dieu for r in merged[:5]],
            "reranked_top3":  [r.so_dieu for r in merged[:3]],
            "sub_queries":    sub_queries,
            "agentic_rounds": rounds + 1,
            "model_tier":     model_tier,
        }

    async def _agentic_query_stream(
        self,
        question:             str,
        model_tier:           str = "fast",
        on_status:            StatusCallback   = None,
        on_token:             TokenCallback    = None,
        on_sections:          SectionsCallback = None,
        conversation_history: list[dict] | None = None,
        loop=None,
    ) -> dict:
        if loop is None:
            loop = asyncio.get_running_loop()

        from backend.core.pipeline.decomposer import decompose_query
        from backend.core.pipeline.verifier import verify_context
        from backend.core.retrieval.query_classifier import classify_query
        from backend.core.retrieval.query_expansion import expand_with_intent

        if on_status:
            await on_status("classifying", "Đang phân tích và tách câu hỏi thành các vấn đề độc lập...")

        sub_queries = await loop.run_in_executor(
            None, decompose_query, self._components["llm"], question
        )

        if on_status:
            n = len(sub_queries)
            meta_subs = "\n".join(f"{i+1}. {sq}" for i, sq in enumerate(sub_queries))
            lbl = f"Tách thành {n} vấn đề" if n > 1 else "1 vấn đề pháp lý"
            await on_status("classifying", lbl, meta_subs, False)

        all_reranked = []
        for i, sq in enumerate(sub_queries):
            intent   = classify_query(sq)
            expanded = expand_with_intent(sq, intent)
            if on_status:
                short = sq[:48] + ("..." if len(sq) > 48 else "")
                lbl2 = f"Tìm kiếm #{i+1}: {short}" if len(sub_queries) > 1 else short
                await on_status("retrieving", lbl2, "", True)
            results, _ = await self._retrieve_progressive_stream(
                sq, expanded, intent, on_status, loop, first_emit=False
            )
            all_reranked.extend(results)

        merged = _dedup_by_hybrid(all_reranked)

        rounds = 0
        while rounds < MAX_AGENTIC_ROUNDS:
            verify = await loop.run_in_executor(
                None, verify_context, self._components["llm"], question, merged[:5]
            )

            if on_status:
                if verify.sufficient:
                    arts = ", ".join(f"Điều {r.so_dieu}" for r in merged[:3])
                    found_meta = "\n".join(
                        f"✓ Điều {r.so_dieu} — {r.ten_dieu[:50]}" for r in merged[:3]
                    )
                    await on_status("reranking", f"Đủ thông tin — {arts}", found_meta, True)
                else:
                    followup_info = f"\nTìm thêm: {verify.follow_up[:100]}" if verify.follow_up else ""
                    await on_status("reranking", "Chưa đủ — tìm bổ sung...",
                                    (verify.missing or "Thiếu thông tin")[:200] + followup_info, True)

            if verify.sufficient or not verify.follow_up:
                break

            intent   = classify_query(verify.follow_up)
            expanded = expand_with_intent(verify.follow_up, intent)
            if on_status:
                await on_status("retrieving", f"Bổ sung: {verify.follow_up[:45]}...", "", True)
            follow, _ = await self._retrieve_progressive_stream(
                verify.follow_up, expanded, intent, on_status, loop, first_emit=False
            )
            merged = _dedup_by_hybrid(merged + follow)
            rounds += 1

        if on_status:
            arts_g = ", ".join(f"Điều {r.so_dieu}" for r in merged[:3])
            await on_status("generating", f"Tổng hợp từ {arts_g}", "", True)

        raw, structured = await self._stream_generate(
            question, merged[:3], on_token, on_sections, conversation_history, model_tier
        )

        return {
            "answer": raw, "structured": structured,
            "citations": self._build_citations(merged[:3], structured),
            "intent": "agentic", "pipeline": "agentic",
            "retrieval_top5": [r.so_dieu for r in merged[:5]],
            "reranked_top3":  [r.so_dieu for r in merged[:3]],
            "sub_queries":    sub_queries,
            "agentic_rounds": rounds + 1,
            "model_tier":     model_tier,
        }

    # ── Private helpers ───────────────────────────────────────────────────────

    async def _retrieve_progressive_stream(
        self, question, expanded, intent, on_status, loop, first_emit: bool = True
    ):
        """Progressive retrieval. first_emit=True = new step row; False = update current row."""
        from backend.core.retrieval.fusion import weighted_rrf, chapter_boost_rerank
        c = self._components

        if on_status:
            await on_status("retrieving", "Tra cứu từ khóa (BM25)...", "", first_emit)
        r_bm25 = await loop.run_in_executor(None, lambda: c["bm25"].search(expanded, top_k=10))
        if on_status and r_bm25:
            bm25_meta = "\n".join(f"• Điều {r.so_dieu} — {r.ten_dieu[:40]}" for r in r_bm25[:3])
            await on_status("retrieving", f"BM25 → {len(r_bm25)} kết quả", bm25_meta, False)

        if on_status:
            await on_status("retrieving", "Tìm kiếm ngữ nghĩa (E5)...", "", False)
        r_e5 = await loop.run_in_executor(None, lambda: c["e5"].search(expanded, top_k=10))
        if on_status and r_e5:
            e5_meta = "\n".join(f"• Điều {r.so_dieu} — {r.ten_dieu[:40]}" for r in r_e5[:3])
            await on_status("retrieving", f"E5 → {len(r_e5)} kết quả", e5_meta, False)

        if on_status:
            await on_status("retrieving", "Tìm kiếm đa chiều (BGE dense)...", "", False)
        r_bge = await loop.run_in_executor(None, lambda: c["bge_dense"].search(expanded, top_k=10))
        if on_status and r_bge:
            bge_meta = "\n".join(f"• Điều {r.so_dieu} — {r.ten_dieu[:40]}" for r in r_bge[:3])
            await on_status("retrieving", f"BGE dense → {len(r_bge)} kết quả", bge_meta, False)

        if on_status:
            await on_status("retrieving", "Tìm kiếm thưa (BGE sparse)...", "", False)
        r_sparse = await loop.run_in_executor(None, lambda: c["bge_sparse"].search(expanded, top_k=10))

        if on_status:
            await on_status("retrieving", "Hợp nhất kết quả (RRF)...", "", False)

        # Fusion — pure Python dict ops, fast, safe in event loop
        if intent.get("type") in ("basic_rights", "definition", "coverage"):
            w = [(r_bm25, 0.3), (r_e5, 2.0), (r_bge, 1.5), (r_sparse, 0.8)]
        else:
            w = [(r_bm25, 0.5), (r_e5, 1.5), (r_bge, 2.0), (r_sparse, 1.0)]

        rrf = weighted_rrf(w, top_k=15)

        if intent.get("boost_early") and intent.get("boost_dieu_range"):
            top5 = chapter_boost_rerank(
                rrf, boost_dieu_range=intent["boost_dieu_range"],
                boost_factor=2.0, top_k=5,
            )
        else:
            top5 = rrf[:5]

        retrieval_top5 = [ch.so_dieu for ch in top5]

        reranked = await loop.run_in_executor(
            None,
            lambda: c["reranker"].rerank(
                question, top5, intent=intent, top_k=3, hybrid_alpha=HYBRID_ALPHA
            )
        )
        if on_status and reranked:
            rerank_meta = "\n".join(
                f"• Điều {r.so_dieu} — {r.ten_dieu[:40]} (score: {r.hybrid_score:.2f})"
                for r in reranked[:3]
            )
            arts = ", ".join(f"Điều {r.so_dieu}" for r in reranked[:3])
            await on_status("retrieving", f"Reranker chọn: {arts}", rerank_meta, False)
        return reranked, retrieval_top5

    def _retrieve_and_rerank(self, question, expanded, intent):
        from backend.core.retrieval.fusion import weighted_rrf, chapter_boost_rerank

        c        = self._components
        r_bm25   = c["bm25"].search(expanded, top_k=10)
        r_e5     = c["e5"].search(expanded, top_k=10)
        r_bge    = c["bge_dense"].search(expanded, top_k=10)
        r_sparse = c["bge_sparse"].search(expanded, top_k=10)

        if intent.get("type") in ("basic_rights", "definition", "coverage"):
            w = [(r_bm25, 0.3), (r_e5, 2.0), (r_bge, 1.5), (r_sparse, 0.8)]
        else:
            w = [(r_bm25, 0.5), (r_e5, 1.5), (r_bge, 2.0), (r_sparse, 1.0)]

        rrf = weighted_rrf(w, top_k=15)

        if intent.get("boost_early") and intent.get("boost_dieu_range"):
            top5 = chapter_boost_rerank(
                rrf, boost_dieu_range=intent["boost_dieu_range"],
                boost_factor=2.0, top_k=5,
            )
        else:
            top5 = rrf[:5]

        retrieval_top5 = [ch.so_dieu for ch in top5]
        reranked = c["reranker"].rerank(
            question, top5, intent=intent,
            top_k=3, hybrid_alpha=HYBRID_ALPHA,
        )
        return reranked, retrieval_top5

    def _generate(
        self,
        question:             str,
        reranked:             list,
        conversation_history: list[dict] | None = None,
        model_tier:           str = "fast",
    ) -> tuple[str, dict | None]:
        from backend.core.pipeline.context_builder import build_context, SYSTEM_PROMPT, parse_structured_answer

        context = build_context(
            query=question, reranked=reranked,
            kg_retriever=self._components["kg"],
            max_chunks=7, max_triples=8,
            conversation_history=conversation_history,
        )

        _model = get_model(model_tier)
        _tokens = get_max_tokens(model_tier)
        try:
            resp = self._components["llm"].chat.completions.create(
                model=_model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": context.prompt},
                ],
                temperature=0.1, max_tokens=_tokens,
                response_format={"type": "json_object"},
            )
        except Exception:
            resp = self._components["llm"].chat.completions.create(
                model=_model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": context.prompt},
                ],
                temperature=0.1, max_tokens=_tokens,
            )

        raw = resp.choices[0].message.content.strip()
        return raw, parse_structured_answer(raw)

    async def _stream_generate(
        self,
        question:             str,
        reranked:             list,
        on_token:             TokenCallback    = None,
        on_sections:          SectionsCallback = None,
        conversation_history: list[dict] | None = None,
        model_tier:           str = "fast",
    ) -> tuple[str, dict | None]:
        from backend.core.pipeline.context_builder import build_context, SYSTEM_PROMPT, parse_structured_answer

        context = build_context(
            query=question, reranked=reranked,
            kg_retriever=self._components["kg"],
            max_chunks=7, max_triples=8,
            conversation_history=conversation_history,
        )
        loop = asyncio.get_running_loop()

        _model = get_model(model_tier)
        _tokens = get_max_tokens(model_tier)

        def _drain() -> str:
            buf = ""
            try:
                stream = self._components["llm"].chat.completions.create(
                    model=_model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user",   "content": context.prompt},
                    ],
                    temperature=0.1, max_tokens=_tokens, stream=True,
                    response_format={"type": "json_object"},
                )
            except Exception:
                stream = self._components["llm"].chat.completions.create(
                    model=_model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user",   "content": context.prompt},
                    ],
                    temperature=0.1, max_tokens=_tokens, stream=True,
                )
            for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    buf += delta.content
            return buf

        raw_output = await loop.run_in_executor(None, _drain)
        structured = parse_structured_answer(raw_output)

        if on_sections and structured and structured.get("sections"):
            await on_sections(structured["sections"])

        await asyncio.sleep(0.08)

        if on_token:
            summary = structured.get("summary", "") if structured else raw_output
            for phrase in _split_into_phrases(summary):
                await on_token(phrase)
                await asyncio.sleep(_phrase_delay(phrase))

        return raw_output, structured

    async def _chitchat_response(
        self, question: str, loop
    ) -> tuple[str, dict | None]:
        """Non-streaming chitchat — used by query()."""
        from backend.core.pipeline.context_builder import parse_structured_answer

        def _call():
            resp = self._components["llm"].chat.completions.create(
                model=LLM_MODEL,
                messages=[
                    {"role": "system", "content": _CHITCHAT_SYSTEM},
                    {"role": "user",   "content": question},
                ],
                temperature=0.7, max_tokens=200,
            )
            return resp.choices[0].message.content.strip()

        raw = await loop.run_in_executor(None, _call)
        return raw, parse_structured_answer(raw)

    async def _chitchat_stream(
        self, question: str, loop, on_token: TokenCallback
    ) -> tuple[str, dict | None]:
        """Streaming chitchat — used by query_stream(). No retrieval, direct LLM."""
        from backend.core.pipeline.context_builder import parse_structured_answer

        def _drain() -> str:
            buf = ""
            stream = self._components["llm"].chat.completions.create(
                model=LLM_MODEL,
                messages=[
                    {"role": "system", "content": _CHITCHAT_SYSTEM},
                    {"role": "user",   "content": question},
                ],
                temperature=0.7, max_tokens=200, stream=True,
            )
            for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    buf += delta.content
            return buf

        raw = await loop.run_in_executor(None, _drain)
        structured = parse_structured_answer(raw)

        if on_token:
            summary = structured.get("summary", raw) if structured else raw
            for phrase in _split_into_phrases(summary):
                await on_token(phrase)
                await asyncio.sleep(_phrase_delay(phrase))

        return raw, structured

    def _build_citations(self, reranked, structured: dict | None = None) -> list[dict]:
        """
        Build citation list. If structured (LLM output) is provided, extract
        so_khoan from citation_khoans so the frontend can scroll to the exact clause.
        """
        # Merge citation_khoans across all sections: {so_dieu: so_khoan}
        khoan_map: dict[int, int] = {}
        if structured:
            for sec in structured.get("sections", []):
                ck = sec.get("citation_khoans", {})
                for dieu_str, khoan_num in ck.items():
                    try:
                        khoan_map[int(str(dieu_str))] = int(str(khoan_num))
                    except (ValueError, TypeError):
                        pass

        # If LLM explicitly used citation_ids, only surface those articles.
        # This prevents retrieval noise (e.g. Điều 49 showing alongside Điều 38)
        # from appearing as citation chips the user can't explain.
        llm_cited: set[int] = set()
        if structured:
            for sec in structured.get("sections", []):
                for cid in sec.get("citation_ids", []):
                    try:
                        llm_cited.add(int(cid))
                    except (ValueError, TypeError):
                        pass

        out = []
        for i, r in enumerate(reranked):
            # If LLM made citations, only include articles it actually cited
            if llm_cited and r.so_dieu not in llm_cited:
                continue
            nd = r.noi_dung
            out.append({
                "index":            len(out) + 1,
                "so_dieu":          r.so_dieu,
                "ten_dieu":         r.ten_dieu,
                "chuong_so":        r.chuong_so,
                "ten_chuong":       r.ten_chuong,
                "van_ban":          "BLLĐ 10/2012/QH13",
                "relevance_score":  round(float(r.hybrid_score), 4),
                "noi_dung_snippet": nd[:400] + "..." if len(nd) > 400 else nd,
                "so_khoan":         khoan_map.get(r.so_dieu, 0),
            })
        return out


# ── Module-level dedup helper ─────────────────────────────────────────────────

def _dedup_by_hybrid(results: list) -> list:
    """
    Deduplicate RerankResults by so_dieu, keeping the entry with the
    highest hybrid_score. Sort descending by hybrid_score.
    """
    seen: dict[int, object] = {}
    for r in results:
        if r.so_dieu not in seen or r.hybrid_score > seen[r.so_dieu].hybrid_score:
            seen[r.so_dieu] = r
    return sorted(seen.values(), key=lambda x: x.hybrid_score, reverse=True)
