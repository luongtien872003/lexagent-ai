"""
Conversation router.

FIX in this version:
  Fix 3 — _get_conversation_history was reading msg.content for assistant turns.
           msg.content stores the raw LLM output: {"summary":"...", "sections":[...]}.
           Passing 300 chars of raw JSON as conversation history fed garbage to the
           next LLM call. Now extracts the structured.summary string for assistant
           turns, falling back to msg.content only if summary is unavailable.
"""
import json
import uuid
import time
import asyncio

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse

from backend.app.schemas import (
    CreateConversationRequest, SendMessageRequest,
    ConversationResponse, MessageResponse, MessageMetadata,
    Citation, StructuredAnswer, StructuredSection,
    SSEStatusEvent, SSETokenEvent, SSESectionsEvent,
    SSEDoneEvent, SSEErrorEvent,
)
from backend.services.conversation_service import Message, Conversation

router = APIRouter(tags=["conversations"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_structured(raw: dict | None) -> StructuredAnswer | None:
    if not raw:
        return None
    try:
        return StructuredAnswer(
            summary  = raw.get("summary", ""),
            sections = [StructuredSection(**s) for s in raw.get("sections", [])],
        )
    except Exception:
        return None


def _build_metadata(result: dict, elapsed: float) -> MessageMetadata:
    return MessageMetadata(
        intent         = result.get("intent", ""),
        pipeline       = result.get("pipeline", "standard"),
        elapsed_sec    = round(elapsed, 1),
        retrieval_top5 = result.get("retrieval_top5", []),
        reranked_top3  = result.get("reranked_top3", []),
        sub_queries    = result.get("sub_queries", []),
        agentic_rounds = result.get("agentic_rounds", 0),
    )


def _get_conversation_history(conv_svc, conv_id: str, max_turns: int = 4) -> list[dict]:
    """
    Build conversation history for LLM context.

    FIX: For assistant turns, read the structured.summary from metadata instead
    of msg.content (which holds raw LLM JSON). A readable summary like
    "Người lao động có quyền đơn phương chấm dứt hợp đồng..." is far better
    context than '{"summary": "Người lao động...', "sections": [{"title":...'.
    """
    conv = conv_svc.get(conv_id)
    if not conv or not conv.messages:
        return []

    history = []
    for msg in conv.messages[-(max_turns):]:
        if msg.role == "user":
            content = (msg.content or "")[:300]
        else:
            # Try to extract summary from stored structured data
            summary = ""
            if msg.metadata:
                stored = msg.metadata.get("structured")
                if stored and isinstance(stored, dict):
                    summary = stored.get("summary", "")
            # Fallback: first 300 chars of content (may be JSON, but better than nothing)
            content = (summary or msg.content or "")[:300]

        if content:
            history.append({"role": msg.role, "content": content})

    return history


# ── Create / get conversation ─────────────────────────────────────────────────

@router.post("/api/conversations", response_model=ConversationResponse)
async def create_conversation(body: CreateConversationRequest, request: Request):
    conv_svc = request.app.state.conversations
    conv     = conv_svc.create(title=body.title, mode=body.mode)
    return ConversationResponse(
        id=conv.id, title=conv.title, mode=conv.mode,
        created_at=conv.created_at, messages=[],
    )


@router.get("/api/conversations/{conv_id}", response_model=ConversationResponse)
async def get_conversation(conv_id: str, request: Request):
    conv_svc = request.app.state.conversations
    conv     = conv_svc.get(conv_id)
    if not conv:
        raise HTTPException(404, f"Conversation '{conv_id}' not found")

    messages = []
    for m in conv.messages:
        structured = _build_structured(m.metadata.get("structured") if m.metadata else None)
        messages.append(MessageResponse(
            id         = m.id,
            role       = m.role,
            content    = m.content,
            structured = structured,
            citations  = [Citation(**c) for c in m.citations],
            metadata   = MessageMetadata(**{
                k: v for k, v in (m.metadata or {}).items()
                if k in MessageMetadata.model_fields
            }),
            created_at = m.created_at,
        ))

    return ConversationResponse(
        id=conv.id, title=conv.title, mode=conv.mode,
        created_at=conv.created_at, messages=messages,
    )


# ── Send message ──────────────────────────────────────────────────────────────

@router.post("/api/conversations/{conv_id}/messages")
async def send_message(conv_id: str, body: SendMessageRequest, request: Request):
    conv_svc = request.app.state.conversations
    pipeline = request.app.state.pipeline

    conv = conv_svc.get(conv_id)
    if not conv:
        conv = Conversation(id=conv_id, title="Cuộc hội thoại mới", mode="standard")
        conv_svc._store[conv_id] = conv

    if not pipeline.ready:
        raise HTTPException(503, "Pipeline đang khởi động. Vui lòng đợi.")

    # Snapshot history BEFORE adding the new user message
    conv_history = _get_conversation_history(conv_svc, conv_id, max_turns=4)

    conv_svc.add_message(conv_id, Message(
        id=f"msg_{uuid.uuid4().hex[:8]}", role="user", content=body.content,
    ))

    if body.stream:
        return StreamingResponse(
            _stream_response(conv_id, body.content, body.mode, body.model_tier, pipeline, conv_svc, conv_history),
            media_type="text/event-stream; charset=utf-8",
            headers={
                "Cache-Control": "no-cache", "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    return await _sync_response(conv_id, body.content, body.mode, body.model_tier, pipeline, conv_svc, conv_history)


# ── Non-streaming ─────────────────────────────────────────────────────────────

async def _sync_response(conv_id, question, mode, model_tier, pipeline, conv_svc, conv_history):
    t0 = time.time()
    try:
        result     = await pipeline.query(question, mode=mode, model_tier=model_tier, conversation_history=conv_history)
        elapsed    = time.time() - t0
        msg_id     = f"msg_{uuid.uuid4().hex[:8]}"
        citations  = [Citation(**c) for c in result["citations"]]
        metadata   = _build_metadata(result, elapsed)
        structured = _build_structured(result.get("structured"))

        meta_dict = metadata.model_dump()
        if result.get("structured"):
            meta_dict["structured"] = result["structured"]

        conv_svc.add_message(conv_id, Message(
            id=msg_id, role="assistant",
            content=result.get("answer", ""),
            citations=result["citations"],
            metadata=meta_dict,
        ))

        return MessageResponse(
            id=msg_id, role="assistant",
            content=result.get("answer", ""),
            structured=structured, citations=citations,
            metadata=metadata, created_at="",
        )
    except Exception as e:
        raise HTTPException(500, f"Pipeline error: {str(e)}")


# ── SSE streaming ─────────────────────────────────────────────────────────────

def _sse(data: dict, event: str) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _stream_response(conv_id, question, mode, model_tier, pipeline, conv_svc, conv_history):
    t0 = time.time()
    q: asyncio.Queue = asyncio.Queue()

    async def on_status(step: str, detail: str, meta: str = "", new_step: bool = True):
        await q.put(("status", SSEStatusEvent(step=step, detail=detail, meta=meta, new_step=new_step).model_dump()))

    async def on_token(content: str):
        await q.put(("token", SSETokenEvent(content=content).model_dump()))

    async def on_sections(sections: list):
        await q.put(("sections", SSESectionsEvent(sections=sections).model_dump()))

    async def run():
        try:
            result = await pipeline.query_stream(
                question, mode=mode, model_tier=model_tier,
                on_status=on_status, on_token=on_token, on_sections=on_sections,
                conversation_history=conv_history,
            )
            await q.put(("result", result))
        except Exception as e:
            await q.put(("error", str(e)))

    task = asyncio.create_task(run())

    while True:
        try:
            etype, data = await asyncio.wait_for(q.get(), timeout=120.0)
        except asyncio.TimeoutError:
            yield _sse(SSEErrorEvent(detail="Pipeline timeout").model_dump(), "error")
            break

        if etype in ("status", "token", "sections"):
            yield _sse(data, etype)
        elif etype == "error":
            yield _sse(SSEErrorEvent(detail=data).model_dump(), "error")
            break
        elif etype == "result":
            elapsed    = time.time() - t0
            result     = data
            msg_id     = f"msg_{uuid.uuid4().hex[:8]}"
            citations  = [Citation(**c) for c in result["citations"]]
            metadata   = _build_metadata(result, elapsed)
            structured = _build_structured(result.get("structured"))

            meta_dict = metadata.model_dump()
            if result.get("structured"):
                meta_dict["structured"] = result["structured"]

            conv_svc.add_message(conv_id, Message(
                id=msg_id, role="assistant",
                content=result.get("answer", ""),
                citations=result["citations"],
                metadata=meta_dict,
            ))

            yield _sse(SSEDoneEvent(message=MessageResponse(
                id=msg_id, role="assistant",
                content=result.get("answer", ""),
                structured=structured, citations=citations,
                metadata=metadata, created_at="",
            )).model_dump(), "done")
            break

    if not task.done():
        task.cancel()
